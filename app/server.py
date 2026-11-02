from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import sys
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .db import DB_PATH, ROOT, apply_migrations, utc_now


class HookRefusals:
    """QA-06: local evidence about the external legacy sender, without reading its requests.

    Counts refused POSTs to the blocked Hermes hook since this process started. Nothing from
    the request (headers, body, address) is stored.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.since = utc_now()
        self.count = 0
        self.last = None

    def record(self) -> None:
        with self._lock:
            self.count += 1
            self.last = utc_now()

    def snapshot(self) -> dict:
        with self._lock:
            return {"refused": self.count, "last_refused_at": self.last, "since": self.since, "receiver": "BLOCKED"}


HERMES_REFUSALS = HookRefusals()
from .chat_history import saved_sessions_page
from .http_security import CSRF_TOKEN, INGEST_PATHS, RequestSecurityError, validate_ingest, validate_request
from .integrations import HERMES_BLOCK, IntegrationError, IntegrationManager
from .chat_workspace import ChatWorkspace, fields
from .unsloth_export import create_handoff, read_handoff
from .dataset_platform import (
    DatasetPlatformError,
    apply_overlap_plan,
    balance_candidate,
    conversation_overlap_analysis,
    create_derived_version,
    create_overlap_plan,
    dataset_health,
    dataset_version_detail,
    eval_leakage,
    freeze_dataset_version,
    list_dataset_versions,
    _version_dir,
)
from .dataset_balancer import analyze_dataset_balance
from .dataset_quality import dataset_quality, validate_candidate_release
from .platform_state import dataset_catalog
from .review_integrity import ExportReadinessError, export_readiness
from .phase38_dataset import get_review as get_phase38_review, save_review as save_phase38_review, freeze_gate as phase38_freeze_gate
from .phase39_edits import apply_phase39, PHASE39, get_post_edit_verification, save_post_edit_verification
from .service import (
    ValidationError,
    add_direct_text,
    add_manual_sft,
    add_message,
    add_preference_pair,
    analytics,
    approve_review,
    bulk_review_actions,
    create_conversation,
    create_export,
    dedup_report,
    bulk_update_manual_data,
    clone_manual_data,
    correct_review,
    delete_manual_data,
    delete_review,
    get_manual_data,
    get_conversation,
    ingest_turn,
    ingest_hermes_hook,
    ignore_manual_data,
    ignore_review,
    exclude_review,
    list_conversations,
    list_exports,
    list_manual_data,
    list_manual_versions,
    list_review_queue,
    list_reviewed,
    page_info,
    page_request,
    reviewed_page,
    conversations_page,
    save_review,
    restore_review,
    seed_demo_data,
    sync_manual_export_history,
    training_dataset,
    update_manual_data,
    initialize_manual_versions,
)

STATIC_DIR = ROOT / "static"
MAX_BODY_BYTES = 2 * 1024 * 1024


class NajdiLabHTTPServer(ThreadingHTTPServer):
    """Prevent two NajdiLab processes from sharing the same Windows port."""

    allow_reuse_address = False

    def __init__(self, *args, **kwargs):
        self.integrations = IntegrationManager()
        self.chat = None
        self._workspace_lock = threading.Lock()
        super().__init__(*args, **kwargs)

    def workspace(self):
        # Independent from the inference lease so Stop/revoke never waits for
        # the model's response or an integration snapshot.
        with self._workspace_lock:
            if self.chat is None:
                self.chat = ChatWorkspace(self.integrations, DB_PATH)
            return self.chat

    def server_close(self):
        super().server_close()
        if self.chat is not None:
            try:
                self.chat.close()
            except IntegrationError:
                # Active writers retain ownership until process exit, preventing
                # a second writer from committing over an unfinished request.
                pass

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class NajdiLabHandler(BaseHTTPRequestHandler):
    server_version = "NajdiLab/1.1"


    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        try:
            validate_request(self.headers, self.command, self.server.server_address[1], urlparse(self.path).path)
        except RequestSecurityError as exc:
            self.close_connection = True
            self._error(str(exc), exc.status, code=exc.code)
            return False
        return True

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _headers(self, status: int, content_type: str, length: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'")
        if length is not None:
            self.send_header("Content-Length", str(length))
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()

    def _json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def _error(self, message: str, status: int = HTTPStatus.BAD_REQUEST, *, code: str | None = None) -> None:
        payload = {"ok": False, "error": message}
        if code:
            payload["code"] = code
        self._json(payload, status)

    def _dataset_error(self, error: DatasetPlatformError) -> None:
        status = HTTPStatus.NOT_FOUND if error.code in {"PROJECT_ROOT_NOT_FOUND", "EXPORTS_ROOT_NOT_FOUND", "DATASET_NOT_FOUND", "MANIFEST_NOT_FOUND"} else HTTPStatus.CONFLICT if error.code in {"VERSION_ALREADY_EXISTS", "SOURCE_NOT_FROZEN", "TARGET_NOT_DRAFT", "OVERLAP_PLAN_STALE"} else HTTPStatus.FORBIDDEN if error.code == "ACCESS_DENIED" else HTTPStatus.UNPROCESSABLE_ENTITY if error.code in {"INVALID_MANIFEST", "INVALID_DATASET", "UNSUPPORTED_DATASET_FORMAT", "INVALID_VERSION_NAME"} else HTTPStatus.INTERNAL_SERVER_ERROR
        self._json(error.as_dict(), status)


    def _body(self) -> dict:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValidationError("Invalid Content-Length") from exc
        if length > MAX_BODY_BYTES:
            raise ValidationError("Request body exceeds the allowed limit")
        raw = self.rfile.read(length) if length else b""
        if self.command == "POST" and urlparse(self.path).path in INGEST_PATHS:
            validate_ingest(self.headers, raw)
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("Invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValidationError("Request body must be an object")
        return value

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"/", ""} else request_path.lstrip("/")
        candidate = (STATIC_DIR / relative).resolve()
        try:
            candidate.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._error("Invalid path", HTTPStatus.FORBIDDEN)
            return
        if not candidate.is_file():
            candidate = STATIC_DIR / "index.html"
        data = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json", "image/svg+xml"}:
            content_type += "; charset=utf-8"
        self._headers(HTTPStatus.OK, content_type, len(data))
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._serve_static(parsed.path)
            return
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/api/v1/session":
                self._json({"ok": True, "csrf_token": CSRF_TOKEN})
            elif parsed.path == '/api/v1/chat/sessions':
                limit, offset = page_request(query)
                items, total = saved_sessions_page(self.server.workspace().db_path, limit, offset)
                self._json({'items': items, 'page': page_info(total, limit, offset, len(items))})
            elif match := re.fullmatch(r'/api/v1/chat/sessions/([a-f0-9-]{36})', parsed.path):
                self._json(self.server.workspace().get(match.group(1)))
            elif match := re.fullmatch(r'/api/v1/unsloth-exports/([a-f0-9]{32})/(dataset\.jsonl|provenance\.jsonl|manifest\.json)', parsed.path):
                raw = read_handoff(*match.groups())
                self._headers(HTTPStatus.OK, 'application/octet-stream', len(raw))
                self.wfile.write(raw)
            elif parsed.path == "/api/v1/integrations":
                self._json(self.server.integrations.snapshot())
            elif parsed.path == "/api/v1/hermes-hook/refusals":
                self._json(HERMES_REFUSALS.snapshot())
            elif parsed.path == "/api/v1/health":
                self._json({"ok": True, "service": "NajdiLab", "version": "1.1", "database": str(DB_PATH)})
            elif parsed.path == "/api/v1/dataset-catalog":
                self._json(dataset_catalog())
            elif parsed.path == "/api/v1/review-integrity":
                self._json(export_readiness(DB_PATH, include_demo=query.get("include_demo") == "1"))
            elif parsed.path == "/api/v1/exports/readiness":
                self._json(export_readiness(DB_PATH, include_demo=query.get("include_demo") == "1"))
            elif parsed.path == "/api/v1/conversations":
                self._json(conversations_page(query))
            elif match := re.fullmatch(r"/api/v1/conversations/(\d+)", parsed.path):
                self._json(get_conversation(int(match.group(1))))
            elif parsed.path == "/api/v1/review-queue":
                self._json({"items": list_review_queue(include_demo=query.get("include_demo", "1") != "0")})
            elif parsed.path == "/api/v1/reviewed":
                self._json(reviewed_page(query))
            elif parsed.path == "/api/v1/dataset-records":
                self._json(training_dataset(include_demo=query.get("include_demo") == "1"))
            elif parsed.path == "/api/v1/exports":
                self._json({"items": list_exports()})
            elif parsed.path == "/api/v1/dataset-versions":
                self._json({"items": list_dataset_versions()})
            elif parsed.path == "/api/v1/phase38/v009/human-review":
                self._json(get_phase38_review())
            elif parsed.path == "/api/v1/phase38/v009/freeze-gate":
                self._json(phase38_freeze_gate())
            elif parsed.path == "/api/v1/phase39/post-edit-verification":
                self._json(get_post_edit_verification())
            elif parsed.path == "/api/v1/phase39/readiness":
                self._json(json.loads((PHASE39 / "phase39-freeze-readiness.json").read_text(encoding="utf-8")))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/health", parsed.path):
                self._json(dataset_health(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/quality-findings", parsed.path):
                self._json(dataset_quality(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/release-validation", parsed.path):
                version = match.group(1)
                directory = _version_dir(version)
                self._json(validate_candidate_release(directory, source_version=version))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/balance", parsed.path):
                self._json(analyze_dataset_balance(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/balance-candidate", parsed.path):
                self._json(balance_candidate(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/eval-sets", parsed.path):
                self._json(eval_leakage(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/conversation-overlaps", parsed.path):
                self._json(conversation_overlap_analysis(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)", parsed.path):
                self._json(dataset_version_detail(match.group(1)))
            elif parsed.path == "/api/v1/exports/dedup-report":
                self._json(dedup_report(include_demo=query.get("include_demo") == "1"))
            elif parsed.path == "/api/v1/analytics":
                self._json(analytics())
            elif parsed.path == "/api/v1/manual-data":
                self._json(list_manual_data(query))
            elif match := re.fullmatch(r"/api/v1/manual-data/(sft|direct|dpo)/(\d+)/versions", parsed.path):
                self._json({"items": list_manual_versions(match.group(1), int(match.group(2)))})
            elif match := re.fullmatch(r"/api/v1/manual-data/(sft|direct|dpo)/(\d+)", parsed.path):
                self._json(get_manual_data(match.group(1), int(match.group(2))))
            elif parsed.path == "/api/v1/config":
                self._json(
                    {
                        "review_statuses": ["FULL_CORRECTION", "DIALECT_CORRECTION", "CONTENT_CORRECTION", "APPROVED"],
                        "error_tags": [
                            "forgot_previous_constraint", "ignored_user_instruction", "wrong_context",
                            "repeated_rejected_option", "contradiction", "hallucination", "dialect_issue",
                            "grammar_issue", "unnatural_arabic", "too_verbose", "too_short",
                            "format_failure", "factual_error", "other"
                        ],
                        "local_only": True,
                    }
                )
            else:
                self._error("Route not found", HTTPStatus.NOT_FOUND)
        except IntegrationError as exc:
            self._error(str(exc), exc.status, code=exc.code)
        except DatasetPlatformError as exc:
            self._dataset_error(exc)
        except ExportReadinessError as exc:
            self._json({"ok": False, "code": "EXPORT_NOT_READY", "error": str(exc), "readiness": exc.readiness}, HTTPStatus.CONFLICT)
        except ValidationError as exc:
            self._error(str(exc))
        except Exception:
            traceback.print_exc()
            self._error("An internal error occurred; inspect the local server log for details", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        # Fail closed before reading or parsing any potentially overbroad event.
        # Closing prevents unread body bytes becoming another request.
        if parsed.path == "/api/v1/hermes-hook":
            self.close_connection = True
            HERMES_REFUSALS.record()
            self._error(HERMES_BLOCK, HTTPStatus.CONFLICT, code="HERMES_UNSAFE_SOURCE")
            return
        try:
            data = self._body()
            if parsed.path == '/api/v1/unsloth-exports':
                fields(data, {'version'})
                if not isinstance(data['version'],str):
                    raise ValidationError('Choose a dataset version.')
                self._json(create_handoff(data['version']), HTTPStatus.CREATED)
            elif parsed.path == '/api/v1/chat/hardware':
                if data.get('approved') is not True:
                    raise IntegrationError('APPROVAL_REQUIRED', 'Approve the read-only hardware snapshot first.', 403)
                self._json(self.server.workspace().hardware(data))
            elif parsed.path == '/api/v1/chat/sessions':
                self._json(self.server.workspace().create(data), HTTPStatus.CREATED)
            elif match := re.fullmatch(r'/api/v1/chat/sessions/([a-f0-9-]{36})/(send|collect|stop|archive)', parsed.path):
                sid, action = match.groups()
                workspace = self.server.workspace()
                if action == 'stop':
                    fields(data, set())
                    result = workspace.stop(sid)
                else:
                    result = getattr(workspace, action)(sid, data)
                self._json(result)
            elif parsed.path == "/api/v1/integrations/discover":
                if data:
                    raise IntegrationError("INVALID_PAYLOAD", "Discovery accepts an empty object only.")
                self._json(self.server.integrations.discover())
            elif match := re.fullmatch(r"/api/v1/integrations/([a-z0-9-]+)/(connect|disconnect|select|test)", parsed.path):
                self._json(self.server.integrations.action(match.group(1), match.group(2), data))
            elif parsed.path == "/api/v1/conversations":
                self._json({"ok": True, "conversation": create_conversation(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/messages":
                self._json({"ok": True, "message": add_message(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/turn":
                self._json({"ok": True, **ingest_turn(data)}, HTTPStatus.CREATED)
            elif match := re.fullmatch(r"/api/v1/reviews/(\d+)", parsed.path):
                self._json({"ok": True, "review": save_review(int(match.group(1)), data)})
            elif match := re.fullmatch(r"/api/v1/reviews/(\d+)/(approve|correct|exclude|restore|ignore|delete)", parsed.path):
                review_id = int(match.group(1))
                action = match.group(2)
                handlers = {
                    "approve": approve_review,
                    "correct": correct_review,
                    "exclude": exclude_review,
                    "restore": restore_review,
                    "ignore": ignore_review,
                    "delete": delete_review,
                }
                self._json({"ok": True, "review": handlers[action](review_id, data)})
            elif parsed.path == "/api/v1/reviews/bulk":
                self._json({"ok": True, **bulk_review_actions(data)})
            elif parsed.path == "/api/v1/manual-data/sft":
                self._json({"ok": True, "item": add_manual_sft(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/manual-data/direct":
                self._json({"ok": True, "item": add_direct_text(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/manual-data/preference":
                self._json({"ok": True, "item": add_preference_pair(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/exports":
                include_demo = bool(data.get("include_demo"))
                self._json(
                    {
                        "ok": True,
                        "export": create_export(
                            DB_PATH,
                            include_demo=include_demo,
                            filters=data.get("filters") or {},
                        ),
                    },
                    HTTPStatus.CREATED,
                )
            elif match := re.fullmatch(r"/api/v1/phase38/v009/human-review/([^/]+)", parsed.path):
                self._json({"ok":True,"review":save_phase38_review(unquote(match.group(1)),data)})
            elif parsed.path == "/api/v1/phase39/apply-edits":
                self._json({"ok": True, **apply_phase39()})
            elif match := re.fullmatch(r"/api/v1/phase39/post-edit-verification/([^/]+)", parsed.path):
                try:
                    self._json({"ok": True, "verification": save_post_edit_verification(unquote(match.group(1)), data)})
                except ValueError as exc:
                    self._json({"ok": False, "error": "POST_EDIT_VERIFICATION_RECORD_NOT_FOUND", "message": str(exc)}, HTTPStatus.NOT_FOUND)
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/derive", parsed.path):
                self._json({"ok": True, "version": create_derived_version(match.group(1), str(data.get("target_version") or ""))}, HTTPStatus.CREATED)
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/overlap-plan", parsed.path):
                self._json({"ok": True, "plan": create_overlap_plan(match.group(1))})
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/apply-overlap-plan", parsed.path):
                self._json(apply_overlap_plan(match.group(1), str(data.get("plan_token") or ""), str(data.get("dataset_fingerprint") or "")))
            elif match := re.fullmatch(r"/api/v1/dataset-versions/([A-Za-z0-9._-]+)/freeze", parsed.path):
                self._json({"ok": True, "version": freeze_dataset_version(match.group(1))})
            elif parsed.path == "/api/v1/manual-data/bulk":
                self._json({"ok": True, **bulk_update_manual_data(data)})
            elif match := re.fullmatch(r"/api/v1/manual-data/(sft|direct|dpo)/(\d+)/clone", parsed.path):
                self._json(
                    {"ok": True, "item": clone_manual_data(match.group(1), int(match.group(2)), data)},
                    HTTPStatus.CREATED,
                )
            elif match := re.fullmatch(r"/api/v1/manual-data/(sft|direct|dpo)/(\d+)/archive", parsed.path):
                archived = data.get("archived", True)
                self._json({"ok": True, "item": update_manual_data(
                    match.group(1), int(match.group(2)),
                    {"archived": archived, "change_notes": "Archive record" if archived else "Unarchive record"},
                )})
            elif match := re.fullmatch(r"/api/v1/manual-data/(sft|direct|dpo)/(\d+)/exclude", parsed.path):
                excluded = data.get("excluded", True)
                self._json({"ok": True, "item": update_manual_data(
                    match.group(1), int(match.group(2)),
                    {"exclude_from_training": excluded, "change_notes": "Exclude from training" if excluded else "Restore training inclusion"},
                )})
            elif match := re.fullmatch(r"/api/v1/manual-data/(sft|direct|dpo)/(\d+)/ignore", parsed.path):
                self._json({"ok": True, "item": ignore_manual_data(
                    match.group(1), int(match.group(2)), data
                )})
            else:
                self._error("Route not found", HTTPStatus.NOT_FOUND)
        except IntegrationError as exc:
            self._error(str(exc), exc.status, code=exc.code)
        except RequestSecurityError as exc:
            self._error(str(exc), exc.status, code=exc.code)
        except DatasetPlatformError as exc:
            self._dataset_error(exc)
        except ExportReadinessError as exc:
            self._json({"ok": False, "code": "EXPORT_NOT_READY", "error": str(exc), "readiness": exc.readiness}, HTTPStatus.CONFLICT)
        except ValidationError as exc:
            self._error(str(exc))
        except Exception:
            traceback.print_exc()
            self._error("An internal error occurred; inspect the local server log for details", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PATCH(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            data = self._body()
            if match := re.fullmatch(r"/api/v1/manual-data/(sft|direct|dpo)/(\d+)", parsed.path):
                self._json({"ok": True, "item": update_manual_data(match.group(1), int(match.group(2)), data)})
            else:
                self._error("Route not found", HTTPStatus.NOT_FOUND)
        except ValidationError as exc:
            self._error(str(exc))
        except Exception:
            traceback.print_exc()
            self._error("An internal error occurred; inspect the local server log for details", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            data = self._body()
            if match := re.fullmatch(r"/api/v1/manual-data/(sft|direct|dpo)/(\d+)", parsed.path):
                self._json({"ok": True, **delete_manual_data(
                    match.group(1), int(match.group(2)), bool(data.get("confirm_exported"))
                )})
            else:
                self._error("Route not found", HTTPStatus.NOT_FOUND)
        except ValidationError as exc:
            self._error(str(exc))
        except Exception:
            traceback.print_exc()
            self._error("An internal error occurred; inspect the local server log for details", HTTPStatus.INTERNAL_SERVER_ERROR)


def run(host: str = "127.0.0.1", port: int = 8770, seed_demo: bool = True) -> None:
    if host != "127.0.0.1":
        raise SystemExit("NajdiLab v1.1 refuses non-local bind addresses; use 127.0.0.1")
    if os.environ.get("NAJDILAB_ALLOW_LEGACY_INGEST") == "1":
        print("WARNING: legacy unauthenticated ingestion is enabled; remove NAJDILAB_ALLOW_LEGACY_INGEST after migration.", file=sys.stderr)
    apply_migrations()
    initialize_manual_versions()
    sync_manual_export_history()
    seeded = seed_demo_data() if seed_demo else 0
    try:
        server = NajdiLabHTTPServer((host, port), NajdiLabHandler)
    except OSError as exc:
        raise SystemExit(
            f"Could not start NajdiLab on http://{host}:{port}; another instance may already be running."
        ) from exc
    print(f"NajdiLab v1.1: http://{host}:{port}")
    print(f"Database: {DB_PATH}")
    if seeded:
        print(f"Demo conversations created: {seeded}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nNajdiLab stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run(port=int(os.environ.get("NAJDILAB_PORT", "8770")), seed_demo=os.environ.get("NAJDILAB_NO_DEMO") != "1")

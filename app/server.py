from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .db import DB_PATH, ROOT, apply_migrations
from .http_security import CSRF_TOKEN, INGEST_PATHS, RequestSecurityError, validate_ingest, validate_request
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
from .evaluation_guard import EvaluationGuardError, verify_adapter_evaluation
from .platform_state import dataset_catalog, platform_status
from .review_integrity import ExportReadinessError, export_readiness
from .training_control import (
    TrainingControlError, cancel_job, create_job, create_production_job, get_job, initialize_training_control,
    discover_models, list_jobs, list_models, mark_job_ready, quality_gate, register_model, training_datasets, validate_model,
    training_preflight, update_job, model_acquisition_catalog, prepare_model_acquisition, acquire_model,
)
from .runtime_control import (
    attempt_logs, attempt_metrics, cancel_attempt, check_runtime as check_runtime_target, deploy_adapter, dry_run,
    authorize_full_training, execution_gate, full_training_disabled, get_attempt, get_runtime_result, get_worker_state,
    initialize_runtime_control, list_runtimes, register_runtime, stage_dataset, staging_status,
    prepare_full_recovery, resume_full_training, start_full_training, start_smoke, start_worker, validate_trained_adapter, worker_heartbeat,
)
from .phase3_review import Phase3ReviewError, get_review as get_phase3_review, save_case as save_phase3_case, submit_final_decision as submit_phase3_decision
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

    def _training_error(self, error: TrainingControlError) -> None:
        self._json(error.as_dict(), error.status)

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
            elif parsed.path == "/api/v1/health":
                self._json({"ok": True, "service": "NajdiLab", "version": "1.1", "database": str(DB_PATH)})
            elif parsed.path == "/api/v1/platform/status":
                self._json(platform_status())
            elif parsed.path == "/api/v1/dataset-catalog":
                self._json(dataset_catalog())
            elif parsed.path == "/api/v1/review-integrity":
                self._json(export_readiness(DB_PATH, include_demo=query.get("include_demo") == "1"))
            elif parsed.path == "/api/v1/exports/readiness":
                self._json(export_readiness(DB_PATH, include_demo=query.get("include_demo") == "1"))
            elif parsed.path == "/api/v1/conversations":
                self._json(
                    {
                        "items": list_conversations(
                            search=query.get("search", ""), model=query.get("model", ""), channel=query.get("channel", "")
                        )
                    }
                )
            elif match := re.fullmatch(r"/api/v1/conversations/(\d+)", parsed.path):
                self._json(get_conversation(int(match.group(1))))
            elif parsed.path == "/api/v1/review-queue":
                self._json({"items": list_review_queue(include_demo=query.get("include_demo", "1") != "0")})
            elif parsed.path == "/api/v1/reviewed":
                self._json({"items": list_reviewed(query)})
            elif parsed.path == "/api/v1/training-dataset":
                self._json(training_dataset(include_demo=query.get("include_demo") == "1"))
            elif parsed.path == "/api/v1/exports":
                self._json({"items": list_exports()})
            elif parsed.path == "/api/v1/dataset-versions":
                self._json({"items": list_dataset_versions()})
            elif parsed.path == "/api/v1/training/datasets":
                self._json({"items": training_datasets()})
            elif parsed.path == "/api/v1/training/quality-gate":
                self._json(quality_gate(query.get("dataset", "")))
            elif parsed.path == "/api/v1/training/models":
                self._json({"items": list_models()})
            elif parsed.path == "/api/v1/training/model-acquisition/catalog":
                self._json(model_acquisition_catalog())
            elif parsed.path == "/api/v1/training/runtimes":
                self._json({"items": list_runtimes()})
            elif match := re.fullmatch(r"/api/v1/training/runtimes/([A-Za-z0-9._-]+)/latest-check", parsed.path):
                self._json({"runtime_id": match.group(1), "result": get_runtime_result(match.group(1))})
            elif match := re.fullmatch(r"/api/v1/training/runtimes/([A-Za-z0-9._-]+)/worker", parsed.path):
                self._json(get_worker_state(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/training/runtimes/([A-Za-z0-9._-]+)/staging/([A-Za-z0-9._-]+)", parsed.path):
                self._json(staging_status(match.group(1), match.group(2)))
            elif parsed.path == "/api/v1/training/jobs":
                self._json({"items": list_jobs()})
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/execution-gate", parsed.path):
                self._json(execution_gate(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})", parsed.path):
                self._json(get_attempt(match.group(1),match.group(2)))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/logs", parsed.path):
                self._json(attempt_logs(match.group(1),match.group(2),query.get("stream","stdout"),int(query.get("offset","0"))))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/metrics", parsed.path):
                self._json(attempt_metrics(match.group(1),match.group(2),int(query.get("offset","0"))))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})", parsed.path):
                self._json(get_job(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/phase3/(phase3-train-\d{8}-\d{3})/human-review", parsed.path):
                self._json(get_phase3_review(match.group(1)))
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
                        "training_actions": False,
                    }
                )
            else:
                self._error("Route not found", HTTPStatus.NOT_FOUND)
        except DatasetPlatformError as exc:
            self._dataset_error(exc)
        except EvaluationGuardError as exc:
            self._json({"ok": False, "code": exc.code, "message": str(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
        except TrainingControlError as exc:
            self._training_error(exc)
        except Phase3ReviewError as exc:
            self._json(exc.as_dict(),exc.status)
        except ExportReadinessError as exc:
            self._json({"ok": False, "code": "EXPORT_NOT_READY", "error": str(exc), "readiness": exc.readiness}, HTTPStatus.CONFLICT)
        except ValidationError as exc:
            self._error(str(exc))
        except Exception:
            traceback.print_exc()
            self._error("An internal error occurred; inspect the local server log for details", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            data = self._body()
            if parsed.path == "/api/v1/conversations":
                self._json({"ok": True, "conversation": create_conversation(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/messages":
                self._json({"ok": True, "message": add_message(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/turn":
                self._json({"ok": True, **ingest_turn(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/hermes-hook":
                self._json({"ok": True, **ingest_hermes_hook(data)}, HTTPStatus.CREATED)
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
            elif parsed.path == "/api/v1/training-data/sft":
                self._json({"ok": True, "item": add_manual_sft(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/training-data/direct":
                self._json({"ok": True, "item": add_direct_text(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/training-data/preference":
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
            elif parsed.path == "/api/v1/training/models":
                self._json({"ok": True, "model": register_model(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/training/model-acquisition/prepare":
                self._json(prepare_model_acquisition(data))
            elif parsed.path == "/api/v1/training/model-acquisition/acquire":
                self._json(acquire_model(data))
            elif parsed.path == "/api/v1/training/models/discover":
                self._json(discover_models(data))
            elif match := re.fullmatch(r"/api/v1/training/models/([A-Za-z0-9._-]+)/validate", parsed.path):
                self._json({"ok": True, "model": validate_model(match.group(1))})
            elif parsed.path == "/api/v1/training/runtimes":
                self._json({"ok": True, "runtime": register_runtime(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/training/preflight":
                self._json(training_preflight(data))
            elif parsed.path == "/api/v1/evaluation/verify-adapter":
                self._json({"ok": True, "verification": verify_adapter_evaluation(data.get("configuration") or {}, data.get("load_evidence") or {})})
            elif parsed.path == "/api/v1/training/runtime-check":
                self._json(check_runtime_target(str(data.get("runtime_id") or "najditrain-wsl")))
            elif match := re.fullmatch(r"/api/v1/training/runtimes/([A-Za-z0-9._-]+)/stage", parsed.path):
                self._json(stage_dataset(match.group(1),str(data.get("dataset_version") or "")))
            elif match := re.fullmatch(r"/api/v1/training/runtimes/([A-Za-z0-9._-]+)/deploy-adapter", parsed.path):
                self._json(deploy_adapter(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/training/runtimes/([A-Za-z0-9._-]+)/worker/start", parsed.path):
                self._json(start_worker(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/training/runtimes/([A-Za-z0-9._-]+)/worker/heartbeat", parsed.path):
                self._json(worker_heartbeat(match.group(1)))
            elif parsed.path == "/api/v1/training/jobs":
                self._json({"ok": True, "job": create_job(data)}, HTTPStatus.CREATED)
            elif parsed.path == "/api/v1/training/production-jobs":
                self._json({"ok":True,"job":create_production_job(str(data.get("derived_from_job") or ""))},HTTPStatus.CREATED)
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/ready", parsed.path):
                self._json({"ok": True, "job": mark_job_ready(match.group(1), data)})
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/cancel", parsed.path):
                self._json({"ok": True, "job": cancel_job(match.group(1))})
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/dry-run", parsed.path):
                self._json(dry_run(match.group(1)))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/full-dry-run", parsed.path):
                self._json(dry_run(match.group(1),attempt_type="FULL"))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/authorize-full-training", parsed.path):
                self._json(authorize_full_training(match.group(1),str(data.get("acknowledgement") or "")))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/start-full-training", parsed.path):
                self._json({"ok":True,"attempt":start_full_training(match.group(1),str(data.get("authorization_token") or ""))},HTTPStatus.ACCEPTED)
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/prepare-recovery", parsed.path):
                self._json({"ok":True,**prepare_full_recovery(match.group(1))})
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/resume", parsed.path):
                resume_full_training(match.group(1),match.group(2),str(data.get("checkpoint") or ""))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/validate-adapter", parsed.path):
                self._json(validate_trained_adapter(match.group(1),match.group(2)))
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/smoke", parsed.path):
                if data.get("confirm_smoke_only") is not True or data.get("max_steps") != 2:
                    raise TrainingControlError("SMOKE_CONFIRMATION_REQUIRED", "Smoke-only confirmation with max_steps=2 is required", status=409)
                self._json({"ok":True,"attempt":start_smoke(match.group(1))},HTTPStatus.ACCEPTED)
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/cancel", parsed.path):
                self._json({"ok":True,"attempt":cancel_attempt(match.group(1),match.group(2))})
            elif parsed.path == "/api/v1/training/full-start":
                full_training_disabled()
            elif match := re.fullmatch(r"/api/v1/phase3/(phase3-train-\d{8}-\d{3})/human-review/cases/([^/]+)", parsed.path):
                self._json({"ok":True,"review":save_phase3_case(match.group(1),unquote(match.group(2)),data)})
            elif match := re.fullmatch(r"/api/v1/phase3/(phase3-train-\d{8}-\d{3})/human-review/final-decision", parsed.path):
                self._json({"ok":True,"review":submit_phase3_decision(match.group(1),str(data.get("decision") or ""))})
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
        except RequestSecurityError as exc:
            self._error(str(exc), exc.status, code=exc.code)
        except DatasetPlatformError as exc:
            self._dataset_error(exc)
        except TrainingControlError as exc:
            self._training_error(exc)
        except Phase3ReviewError as exc:
            self._json(exc.as_dict(),exc.status)
        except EvaluationGuardError as exc:
            self._json({"ok": False, "code": exc.code, "message": str(exc)}, HTTPStatus.CONFLICT)
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
            elif match := re.fullmatch(r"/api/v1/training/jobs/(train-\d{8}-\d{3})", parsed.path):
                self._json({"ok": True, "job": update_job(match.group(1), data)})
            else:
                self._error("Route not found", HTTPStatus.NOT_FOUND)
        except TrainingControlError as exc:
            self._training_error(exc)
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
    initialize_training_control()
    initialize_runtime_control()
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

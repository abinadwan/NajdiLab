"""Candidate-only HTTP entry point; staged as app/server.py by the builder.
Original app/server.py and all research/training implementations are untouched.
"""
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import service, dataset_platform, dataset_quality, dataset_balancer
from .db import ROOT, DB_PATH, apply_migrations
from .extensions import UnavailableExtension
from .core_reviews import ReviewError, update_review
from .http_security import CSRF_TOKEN, INGEST_PATHS, RequestSecurityError, validate_request, validate_ingest
from .review_integrity import ExportReadinessError, export_readiness


class NajdiLabHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, address, handler, *, extension=None):
        self.extension = extension if extension is not None else UnavailableExtension()
        super().__init__(address, handler)

    def server_bind(self):
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class NajdiLabHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # No payloads, credentials or operational paths in routine logs.

    def parse_request(self):
        if not super().parse_request(): return False
        try:
            validate_request(self.headers, self.command, self.server.server_address[1], urlparse(self.path).path)
        except RequestSecurityError as exc:
            self.close_connection = True
            self.respond({'ok':False,'code':exc.code or 'REQUEST_REJECTED','message':str(exc)},exc.status)
            return False
        return True

    def headers_for(self, status, kind, size):
        self.send_response(status)
        for key,value in {'Content-Type':kind,'Content-Length':str(size),'Cache-Control':'no-store',
                          'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer',
                          'Content-Security-Policy':"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; connect-src 'self'"}.items():
            self.send_header(key,value)
        self.end_headers()

    def respond(self, value, status=200):
        raw=json.dumps(value,ensure_ascii=False).encode()
        self.headers_for(status,'application/json; charset=utf-8',len(raw));self.wfile.write(raw)

    def body(self):
        size=int(self.headers.get('Content-Length','0'))
        if size>2*1024*1024: raise service.ValidationError('Request body exceeds limit')
        raw=self.rfile.read(size)
        if urlparse(self.path).path in INGEST_PATHS: validate_ingest(self.headers,raw)
        try: data=json.loads(raw.decode('utf-8')) if raw else {}
        except (ValueError,UnicodeError): raise service.ValidationError('Invalid JSON') from None
        if not isinstance(data,dict):raise service.ValidationError('Request body must be an object')
        return data

    def static(self,path):
        root=(ROOT/'static').resolve();target=(root/unquote(path).lstrip('/')).resolve()
        if not target.is_relative_to(root):self.respond({'ok':False,'message':'Invalid path'},403);return
        if not target.is_file():target=root/'index.html'
        raw=target.read_bytes();kind=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        self.headers_for(200,kind+'; charset=utf-8',len(raw));self.wfile.write(raw)

    def dispatch(self,method):
        path=urlparse(self.path).path
        try:
            data=self.body() if method=='POST' else {}
            if path.startswith(('/api/v1/phase','/api/v1/training/','/api/v1/evaluation/')):
                status,result=self.server.extension.handle(method,path,data);self.respond(result,status);return
            if method=='GET' and not path.startswith('/api/'):
                self.static(path);return
            query={k:v[-1] for k,v in parse_qs(urlparse(self.path).query).items()}
            demo=query.get('include_demo')=='1'
            result=None;status=200
            if method=='GET':
                if path=='/api/v1/session':result={'ok':True,'csrf_token':CSRF_TOKEN}
                elif path=='/api/v1/health':result={'ok':True,'service':'NajdiLab','profile':'source-only','storage_scope':'checkout-local'}
                elif path=='/api/v1/config':result={'local_only':True,'training_actions':False,'error_tags':sorted(service.ERROR_TAGS),'review_statuses':sorted(service.TRAINING_REVIEW_STATUSES)}
                elif path=='/api/v1/conversations':result={'items':service.list_conversations(search=query.get('search',''))}
                elif m:=re.fullmatch(r'/api/v1/conversations/(\d+)',path):result=service.get_conversation(int(m[1]))
                elif path=='/api/v1/review-queue':result={'items':service.list_review_queue(include_demo=query.get('include_demo','1')!='0')}
                elif path=='/api/v1/reviewed':result={'items':service.list_reviewed(query)}
                elif path=='/api/v1/training-dataset':result=service.training_dataset(include_demo=demo)
                elif path=='/api/v1/analytics':result=service.analytics()
                elif path=='/api/v1/exports':result={'items':service.list_exports()}
                elif path=='/api/v1/exports/readiness':result=export_readiness(DB_PATH,include_demo=demo)
                elif path=='/api/v1/dataset-versions':result={'items':dataset_platform.list_dataset_versions()}
                elif m:=re.fullmatch(r'/api/v1/dataset-versions/([A-Za-z0-9._-]+)/(health|quality-findings|balance)',path):
                    result={'health':dataset_platform.dataset_health,'quality-findings':dataset_quality.dataset_quality,'balance':dataset_balancer.analyze_dataset_balance}[m[2]](m[1])
            else:
                if path=='/api/v1/turn':result={'ok':True,**service.ingest_turn(data)};status=201
                elif path=='/api/v1/hermes-hook':result={'ok':True,**service.ingest_hermes_hook(data)};status=201
                elif path=='/api/v1/conversations':result={'ok':True,'conversation':service.create_conversation(data)};status=201
                elif path=='/api/v1/messages':result={'ok':True,'message':service.add_message(data)};status=201
                elif m:=re.fullmatch(r'/api/v1/reviews/(\d+)/(approve|correct|exclude|restore|ignore|delete)',path):
                    result={'ok':True,'review':update_review(int(m[1]),m[2],data)}
                elif m:=re.fullmatch(r'/api/v1/reviews/(\d+)',path):result={'ok':True,'review':update_review(int(m[1]),'save',data)}
                elif path=='/api/v1/exports':result={'ok':True,'export':service.create_export(include_demo=bool(data.get('include_demo')))};status=201
            if result is None:self.respond({'ok':False,'code':'ROUTE_UNAVAILABLE','message':'This route is not part of the source-only core profile.'},404)
            else:self.respond(result,status)
        except RequestSecurityError as exc:
            self.close_connection=True;self.respond({'ok':False,'code':exc.code or 'REQUEST_REJECTED','message':str(exc)},exc.status)
        except ReviewError as exc:self.respond({'ok':False,'code':exc.code,'message':str(exc)},exc.status)
        except ExportReadinessError as exc:self.respond({'ok':False,'code':'EXPORT_NOT_READY','readiness':exc.readiness},409)
        except (service.ValidationError,ValueError,UnicodeError):
            self.close_connection=True;self.respond({'ok':False,'code':'INVALID_REQUEST','message':'Invalid request or unsupported value.'},400)
        except dataset_platform.DatasetPlatformError as exc:self.respond({'ok':False,'code':exc.code,'message':'Dataset operation unavailable; check the local candidate version.'},422)
        except Exception:self.respond({'ok':False,'code':'INTERNAL_ERROR','message':'Local candidate operation failed.'},500)

    def do_GET(self):self.dispatch('GET')
    def do_POST(self):self.dispatch('POST')


def main():
    # Binding is attempted before initializing local state. No demo/runtime discovery.
    port=int(os.environ.get('NAJDILAB_PORT','8770'))
    if not 1<=port<=65535:raise SystemExit('Invalid port')
    with NajdiLabHTTPServer(('127.0.0.1',port),NajdiLabHandler) as http:
        apply_migrations()
        for name in ['exports','datasets']: (ROOT/name).mkdir(exist_ok=True)
        print('NajdiLab source-only candidate on loopback; no private extensions loaded.',flush=True)
        try:http.serve_forever()
        except KeyboardInterrupt:pass

if __name__=='__main__':main()

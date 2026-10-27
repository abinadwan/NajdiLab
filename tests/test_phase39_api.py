import json, threading, unittest
from unittest.mock import patch
from urllib.request import Request
from tests.http_client import urlopen

from app import server as server_module

from tests.private_artifacts import requires_private_artifacts

class Phase39ApiTests(unittest.TestCase):
    def test_post_edit_verification_route_accepts_all_decisions_and_reload(self):
        state={"records":[{"record_id":"p38-sft-08","decision":None}],"summary":{"total":1}}
        def get(): return state
        def save(record_id, data):
            self.assertEqual(record_id,"p38-sft-08"); state["records"][0].update(decision=data["decision"], reviewer_note=data.get("reviewer_note","")); return state
        http=server_module.ThreadingHTTPServer(("127.0.0.1",0),server_module.NajdiLabHandler); t=threading.Thread(target=http.serve_forever,daemon=True); t.start()
        try:
            with patch.object(server_module,"get_post_edit_verification",get), patch.object(server_module,"save_post_edit_verification",save):
                for decision in ("اعتماد التعديل","يحتاج تعديل إضافي","رفض"):
                    req=Request(f"http://127.0.0.1:{http.server_address[1]}/api/v1/phase39/post-edit-verification/p38-sft-08",data=json.dumps({"decision":decision,"reviewer_note":"اختبار"},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")
                    with urlopen(req) as response:
                        self.assertEqual(response.status,200); self.assertEqual(json.loads(response.read())["verification"]["records"][0]["decision"],decision)
                self.assertEqual(get()["records"][0]["reviewer_note"],"اختبار")
        finally: http.shutdown(); http.server_close()

    @requires_private_artifacts('reports/phase39/post-edit-verification.json')
    def test_invalid_record_id_is_structured_not_found(self):
        http=server_module.ThreadingHTTPServer(("127.0.0.1",0),server_module.NajdiLabHandler); t=threading.Thread(target=http.serve_forever,daemon=True); t.start()
        try:
            req=Request(f"http://127.0.0.1:{http.server_address[1]}/api/v1/phase39/post-edit-verification/no-such-record",data=json.dumps({"decision":"اعتماد التعديل"},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")
            with self.assertRaises(Exception) as ctx: urlopen(req)
            self.assertIn("HTTP Error 404",str(ctx.exception))
        finally: http.shutdown(); http.server_close()

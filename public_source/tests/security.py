"""Raw-HTTP boundary regression for the exact source-only candidate."""
import http.client
import threading
import unittest
from app.server import NajdiLabHTTPServer, NajdiLabHandler


class CandidateSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=NajdiLabHTTPServer(('127.0.0.1',0),NajdiLabHandler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.http.server_address[1];cls.host=f'127.0.0.1:{cls.port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join(timeout=5)

    def request(self,method='GET',headers=(),body=None,path='/api/v1/session'):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        try:
            c.putrequest(method,path,skip_host=True)
            for k,v in headers:c.putheader(k,v)
            c.endheaders(body);r=c.getresponse();r.read();return r.status,dict(r.getheaders())
        finally:c.close()

    def test_host_and_origin_on_all_methods(self):
        for method in ['GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD']:
            with self.subTest(method=method):
                self.assertEqual(self.request(method,[('Host','evil.invalid')])[0],403)
                self.assertEqual(self.request(method,[('Host',self.host),('Origin','null')])[0],403)

    def test_duplicate_headers_and_rebinding(self):
        for headers in [[],[('Host',self.host),('Host',self.host)],[('Host',self.host),('Origin','http://'+self.host),('Origin','http://'+self.host)],[('Host',self.host),('Sec-Fetch-Site','cross-site')],[('Host',self.host),('Content-Length','1'),('Content-Length','2')],[('Host',self.host),('Transfer-Encoding','chunked')]]:
            with self.subTest(headers=headers):self.assertIn(self.request(headers=headers)[0],[400,403])

    def test_session_headers_and_framing(self):
        status,headers=self.request(headers=[('Host',self.host)])
        self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['X-Frame-Options'],'DENY');self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertEqual(self.request(headers=[('Host',self.host),('Content-Length','-1')])[0],400)

    def test_unsupported_methods_are_controlled_and_head_has_no_body(self):
        import json
        from app.http_security import CSRF_TOKEN
        for method in ['PUT','PATCH','DELETE','OPTIONS','HEAD','TRACE','UNRECOGNIZED']:
            with self.subTest(method=method):
                c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
                c.request(method,'/api/v1/health',headers={'Content-Type':'application/json','X-NajdiLab-CSRF':CSRF_TOKEN})
                r=c.getresponse();raw=r.read();c.close()
                self.assertEqual(r.status,405);self.assertEqual(r.getheader('Allow'),'GET, POST')
                if method=='HEAD':self.assertEqual(raw,b'')
                else:self.assertEqual(json.loads(raw)['code'],'METHOD_UNAVAILABLE')

    def test_malformed_json_and_declared_size_reject_before_ingestion(self):
        import json
        from app.http_security import CSRF_TOKEN
        for raw in [b'{broken',b'[]',b'null',b'"text"',b'\xff']:
            with self.subTest(raw=raw):
                self.assertEqual(self.request('POST',[('Host',self.host),('Content-Type','application/json'),('Content-Length',str(len(raw))),('X-NajdiLab-CSRF',CSRF_TOKEN)],raw,'/api/v1/conversations')[0],400)
        # Send headers only: size guard must return without waiting/allocating the body.
        self.assertEqual(self.request('POST',[('Host',self.host),('Content-Type','application/json'),('Content-Length',str(2*1024*1024+1)),('X-NajdiLab-CSRF',CSRF_TOKEN)],None,'/api/v1/conversations')[0],400)

    def test_candidate_refuses_legacy_ingest_override_before_parsing(self):
        import os
        from unittest.mock import patch
        # Invalid JSON avoids any DB operation even on the old unsafe bypass.
        with patch.dict(os.environ,{'NAJDILAB_ALLOW_LEGACY_INGEST':'1','NAJDILAB_INGEST_TOKEN':'fictional-boundary-only'}):
            for path in ['/api/v1/turn','/api/v1/hermes-hook']:
                with self.subTest(path=path):
                    self.assertEqual(self.request('POST',[('Host',self.host),('Content-Type','application/json'),('Content-Length','7')],b'{broken',path)[0],409 if path.endswith('hermes-hook') else 503)

    def test_hermes_blocked_before_body_read_with_or_without_credentials(self):
        import os
        from unittest.mock import patch
        for legacy in ['0','1']:
            with patch.dict(os.environ,{'NAJDILAB_ALLOW_LEGACY_INGEST':legacy,'NAJDILAB_INGEST_TOKEN':'fictional-boundary-only'}), patch.object(NajdiLabHandler,'body',side_effect=AssertionError('No body parsing')):
                for extra in [[],[('Authorization','Bearer fictional-boundary-only')]]:
                    status,headers=self.request('POST',[('Host',self.host),('Content-Type','application/json'),('Content-Length','7'),*extra],b'{broken','/api/v1/hermes-hook')
                    self.assertEqual(status,409)
                    self.assertEqual(headers.get('Connection'),'close')

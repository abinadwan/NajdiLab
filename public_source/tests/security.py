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

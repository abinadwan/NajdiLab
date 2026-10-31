"""Hosted browser fixture. Disposable own DB/engine, never installed services."""
import sys
from pathlib import Path
import tempfile
from dataclasses import replace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import server,service
from app.db import apply_migrations
from app.chat_workspace import ChatWorkspace
from app.integrations import IntegrationManager,CONNECTORS
from test_integrations import RuntimeFixture
from test_chat_workspace import Engine


class BrowserEngine(Engine):
    content='  Synthetic fixture reply — no personal data.  '
    def limits(self):
        return {**super().limits(),'model_max_context':131072,'runtime_context':None,'weights_bytes':4*1024**3,'architecture':'synthetic',
                'kv':{'block_count':12,'embedding_length':1024,'attention.head_count':8}}
    def generate(self,messages,reserve,stop):
        if messages[-1]['content']=='STOP_FIXTURE':
            stop.wait(5)
        return super().generate(messages,reserve,stop)


def main():
    with tempfile.TemporaryDirectory(prefix='najdilab-browser-') as temp:
        root=Path(temp);db=root/'fixture.db';apply_migrations(db)
        server.DB_PATH=db
        server.analytics=lambda:service.analytics(db)
        server.list_exports=lambda:service.list_exports(db)
        server.training_dataset=lambda **kw:service.training_dataset(db,**kw)
        server.list_review_queue=lambda **kw:service.list_review_queue(db,**kw)
        server.list_conversations=lambda **kw:service.list_conversations(db_path=db,**kw)
        runtime=RuntimeFixture();runtime.models=['fixture']
        http=server.NajdiLabHTTPServer(('127.0.0.1',0),server.NajdiLabHandler)
        specs={k:replace(v,port=runtime.port) if v.port else v for k,v in CONNECTORS.items()}
        http.integrations=IntegrationManager(connectors=specs,home=root)
        for key in ('lmstudio','ollama'):
            http.integrations.action(key,'connect',{'approved':True})
            http.integrations.action(key,'select',{'approved':True,'model':'fixture'})
        http.chat=ChatWorkspace(http.integrations,db,engine_factory=BrowserEngine().open)
        print(f'BROWSER_FIXTURE=http://127.0.0.1:{http.server_port}',flush=True)
        try:http.serve_forever()
        finally:http.server_close();runtime.close()


if __name__=='__main__':main()

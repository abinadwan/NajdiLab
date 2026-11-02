"""Hosted browser fixture. Disposable own DB/engine, never installed services."""
import inspect
import sys
from functools import partial
from pathlib import Path
import tempfile
import time
from dataclasses import replace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import server,service
from app.db import apply_migrations
from app.chat_workspace import ChatWorkspace
from app.integrations import IntegrationManager,CONNECTORS
from test_integrations import RuntimeFixture
from test_chat_workspace import Engine
from fixture_safety import refuse_default_database
from synthetic_datasets import bind_synthetic_catalog
from app import dataset_platform


class BrowserEngine(Engine):
    content='  Synthetic fixture reply — no personal data.  '
    def limits(self):
        return {**super().limits(),'model_max_context':131072,'runtime_context':None,'weights_bytes':4*1024**3,'architecture':'synthetic',
                'kv':{'block_count':12,'embedding_length':1024,'attention.head_count':8}}
    def generate(self,messages,reserve,stop):
        if messages[-1]['content']=='STOP_FIXTURE':
            stop.wait(5)
        if messages[-1]['content']=='DELAY_FIXTURE':
            time.sleep(0.35)  # allow typing a newer draft before synthetic completion
        result = super().generate(messages,reserve,stop)
        if messages[-1]['content']=='MARKDOWN_FIXTURE':
            result['content']='# Heading\n\n**bold** and `code`\n\n- one\n- two\n\n```html\n<img src=x onerror=alert(1)>\\n\n```\n\n<script>alert(1)</script> [link](javascript:alert(1)) &lt;b&gt;'
            result['content']+='\n\n\\*\\*literal\\*\\*'
        return result


def main():
    with tempfile.TemporaryDirectory(prefix='najdilab-browser-') as temp:
        root=Path(temp);db=root/'fixture.db';apply_migrations(db)
        bind_synthetic_catalog(dataset_platform,root)
        server.DB_PATH=db
        # Bind every service function the server imported, so no route can fall back to the default database.
        for name,fn in list(vars(server).items()):
            if inspect.isfunction(fn) and fn.__module__=='app.service' and 'db_path' in inspect.signature(fn).parameters:
                setattr(server,name,partial(fn,db_path=db))
        server.analytics=lambda:service.analytics(db)
        server.list_exports=lambda:service.list_exports(db)
        server.training_dataset=lambda **kw:service.training_dataset(db,**kw)
        server.list_review_queue=lambda **kw:service.list_review_queue(db,**kw)
        server.list_conversations=lambda **kw:service.list_conversations(db_path=db,**kw)
        server.conversations_page=lambda query:service.conversations_page(query,db)
        server.reviewed_page=lambda query:service.reviewed_page(query,db)
        server.list_manual_data=lambda query:service.list_manual_data(query,db)
        service.connect=refuse_default_database(service.connect)
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

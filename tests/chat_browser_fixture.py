"""Hosted browser fixture. Disposable own DB/engine, never installed services."""
import inspect
import os
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
from app import chat_workspace,hardware
from app.hf_hub import HubClient
from app.managed_runtime import ManagedRuntime
from app.model_service import ModelLibrary
from app.model_store import ModelStore
from fake_github import SERVER_ZIP, FakeGitHub, make_zip, package
from fake_hub import FakeHub


def synthetic_hardware(limits=None,limits_error=None):
    """The host's real RAM, but never the host's GPU: browser checks assume a machine without
    one, so results must not change on a developer PC that has an NVIDIA card."""
    result=hardware.snapshot(limits,limits_error)
    result.pop('gpu_compute_processes',None)
    result.update(gpus=[],warnings=[w for w in result['warnings'] if not w.startswith('GPU_')]+['GPU_BACKEND_UNAVAILABLE'])
    result['recommendation']=hardware.recommendation(result,limits)
    return result


class BrowserEngine(Engine):
    content='  Synthetic fixture reply — no personal data.  '
    ceiling=16384
    def limits(self):
        return {**super().limits(),'model_max_context':131072,'runtime_context':None,'weights_bytes':4*1024**3,'architecture':'synthetic',
                'kv':{'block_count':12,'embedding_length':1024,'attention.head_count':8}}
    def generate(self,messages,reserve,stop,on_delta=None):
        last=messages[-1]['content']
        if last=='STOP_FIXTURE':
            if on_delta:
                on_delta('content','Partial synthetic text that must never be saved.')
            stop.wait(5)
        if last=='DELAY_FIXTURE':
            time.sleep(0.35)  # allow typing a newer draft before synthetic completion
        result=super().generate(messages,reserve,stop)
        if last=='MARKDOWN_FIXTURE':
            result['content']=MARKDOWN
        if last=='MARKDOWN_EXACT_FIXTURE':
            # PR #21 (95e7604) exact-source case: HTML, unsafe links, entities and
            # escapes must stay literal text.
            result['content']=MARKDOWN_EXACT
        if on_delta:
            if last in {'THINK_FIXTURE','MARKDOWN_FIXTURE'}:
                for part in ('Synthetic ','thinking ','trace.'):
                    on_delta('thinking',part)
                    time.sleep(0.05)
            text=result['content']
            for i in range(0,len(text),12):
                on_delta('content',text[i:i+12])
                time.sleep(0.01)
            result['reasoning_discarded']=last in {'THINK_FIXTURE','MARKDOWN_FIXTURE'}
        return result


MARKDOWN='## عنوان اصطناعي\n\n**نص غامق** و *مائل* و `code`.\n\n- أول\n- ثاني\n\n```python\nprint("synthetic")\n```\n\n[رابط آمن](https://example.org) [خطر](javascript:alert(1)) <img src=x onerror=alert(1)>\n'
MARKDOWN_EXACT='# Heading\n\n**bold** and `code`\n\n- one\n- two\n\n```html\n<img src=x onerror=alert(1)>\\n\n```\n\n<script>alert(1)</script> [link](javascript:alert(1)) &lt;b&gt;\n\n\\*\\*literal\\*\\*'



def main():
    with tempfile.TemporaryDirectory(prefix='najdilab-browser-') as temp:
        root=Path(temp);db=root/'fixture.db';apply_migrations(db)
        bind_synthetic_catalog(dataset_platform,root)
        server.DB_PATH=db
        # Bind every service function the server imported, so no route can fall back to the default database.
        for name,fn in list(vars(server).items()):
            if inspect.isfunction(fn) and fn.__module__=='app.service' and 'db_path' in inspect.signature(fn).parameters:
                setattr(server,name,partial(fn,db_path=db))
        # Dataset versions and Unsloth handoffs are written in this fixture's folder, never into the checkout.
        import app.unsloth_export as unsloth_export
        unsloth_export.HANDOFFS=root/'exports'/'unsloth-handoffs'
        server.create_export=partial(service.create_export,db_path=db,exports_dir=root/'exports')
        server.analytics=lambda:service.analytics(db)
        server.list_exports=lambda:service.list_exports(db)
        server.training_dataset=lambda **kw:service.training_dataset(db,**kw)
        server.list_review_queue=lambda **kw:service.list_review_queue(db,**kw)
        server.list_conversations=lambda **kw:service.list_conversations(db_path=db,**kw)
        server.conversations_page=lambda query:service.conversations_page(query,db)
        server.reviewed_page=lambda query:service.reviewed_page(query,db)
        server.list_manual_data=lambda query:service.list_manual_data(query,db)
        service.connect=refuse_default_database(service.connect)
        chat_workspace.hardware_snapshot=synthetic_hardware
        runtime=RuntimeFixture();runtime.models=['fixture']
        http=server.NajdiLabHTTPServer(('127.0.0.1',0),server.NajdiLabHandler)
        specs={k:replace(v,port=runtime.port) if v.port else v for k,v in CONNECTORS.items()}
        http.integrations=IntegrationManager(connectors=specs,home=root)
        for key in ('lmstudio','ollama'):
            http.integrations.action(key,'connect',{'approved':True})
            http.integrations.action(key,'select',{'approved':True,'model':'fixture'})
        http.chat=ChatWorkspace(http.integrations,db,engine_factory=BrowserEngine().open)
        # Model library: synthetic Hugging Face, an isolated models folder, a small storage reserve and
        # fixed synthetic hardware. No network, no real model folder, no dependency on this computer.
        http.native.models_dir=root/'models'
        hub=HubClient(FakeHub())
        http._models=ModelLibrary(db,http.native,hub=hub,
            store=ModelStore(db,root/'models'/'huggingface',hub,reserve_bytes=64*1024**2,system_reserve_bytes=64*1024**2,in_use=http.native.serving),
            snapshot=lambda:{'ram_total_bytes':16*1024**3,'ram_available_bytes':8*1024**3,'gpus':[],'warnings':['GPU_BACKEND_UNAVAILABLE']})
        from app.training_models import TrainingModels
        http._training=TrainingModels(hub,Path(temp)/'training-models',cache_roots=[])  # never the owner's real cache
        # Managed llama.cpp runtime: a synthetic release, a synthetic Blackwell-class GPU and a recorded
        # verification. Nothing runs and nothing is downloaded; the real build is never used here.
        os.environ.pop('NAJDILAB_NATIVE_SERVER',None)
        blobs={'llama-b12059-bin-win-cuda-13.4-x64.zip':make_zip(SERVER_ZIP),'cudart-llama-bin-win-cuda-13.4-x64.zip':make_zip({'cudart64_13.dll':b'synthetic'}),
               'llama-b12059-bin-win-cuda-12.4-x64.zip':make_zip(SERVER_ZIP),'llama-b12059-bin-win-cpu-x64.zip':make_zip(SERVER_ZIP)}
        pick=lambda *names:{n:blobs[n] for n in names}
        packages=[package(pick('llama-b12059-bin-win-cuda-13.4-x64.zip','cudart-llama-bin-win-cuda-13.4-x64.zip'),'windows-x64-cuda-13.4',backend='CUDA',label='NVIDIA GPU (CUDA 13.4)'),
                  package(pick('llama-b12059-bin-win-cuda-12.4-x64.zip'),'windows-x64-cuda-12.4',backend='CUDA',label='NVIDIA GPU (CUDA 12.4)'),
                  package(pick('llama-b12059-bin-win-cpu-x64.zip'),'windows-x64-cpu',label='CPU only')]
        host={'system':'Windows','machine':'AMD64','nvidia':[{'name':'Synthetic GPU','compute_capability':(12,0),'total_bytes':12*1024**3}],
              'driver_version':'600.00','driver_cuda':(13,5),'vulkan_loader':True,'warnings':[]}
        evidence={'version':{'build':12059,'commit':'1b6935b22'},'devices':[{'id':'CUDA0','name':'Synthetic GPU','total_bytes':12*1024**3,'free_bytes':11*1024**3}],
                  'probe':{'device':'CUDA0','device_name':'Synthetic GPU','layers_on_gpu':'2/2','tokens':4,'seconds':0.5,'model':'synthetic'},'verified_at':'2026-11-04T00:00:00Z'}
        http.runtime=ManagedRuntime(http.native,root/'runtime',transport=FakeGitHub(blobs),reserve_bytes=0,system_reserve_bytes=0,
                                    detect=lambda:dict(host),packages=packages,verifier=lambda server,pkg,work:evidence,system='Windows',machine='AMD64')
        http.runtime.attach()
        print(f'BROWSER_FIXTURE=http://127.0.0.1:{http.server_port}',flush=True)
        try:http.serve_forever()
        finally:http.server_close();runtime.close()


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Offline SDK compatibility test. HTTP is intercepted; no provider is contacted."""
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch
if __package__ in (None,''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.llm import LLM, MODEL_REASON, LLMUnavailable
from harness.budget import BudgetLedger

async def diagnose():
    report={'python':sys.version,'executable':sys.executable,'packages':{},'network':'intercepted; no live calls'}
    for name in ('openjiuwen','openai','httpx','pydantic'):
        try: report['packages'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: report['packages'][name]=None
    with patch.dict(os.environ,{'LLM_BASE_URL':'https://example.invalid/v1','LLM_API_KEY':'offline-fixture','HARNESS_REASONING_USAGE':'included'}):
        llm=LLM(BudgetLedger())
        try: llm._oj_model(MODEL_REASON)
        except Exception:
            report['initialization']='failed';report['traceback']=traceback.format_exc();return report
        report['initialization']='ok'
        import httpx
        report['cases']=[]
        for status in (200,503):
            sends=[]
            async def send(client,request,**kwargs):
                body=json.loads(request.content);sends.append({'model':body.get('model'),'max_tokens':body.get('max_tokens')})
                payload=({'id':'offline','object':'chat.completion','created':0,'model':MODEL_REASON,
                          'choices':[{'index':0,'message':{'role':'assistant','content':'42'},'finish_reason':'stop'}],
                          'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30,'completion_tokens_details':{'reasoning_tokens':5}}}
                         if status==200 else {'error':{'message':'offline 503','type':'unavailable'}})
                return httpx.Response(status,json=payload,request=request)
            llm=LLM(BudgetLedger())
            with patch.object(httpx.AsyncClient,'send',send):
                try:
                    answer=await llm.chat([{'role':'user','content':'offline'}],model=MODEL_REASON)
                    outcome='answer' if answer['content']=='42' else 'unexpected_answer'
                except LLMUnavailable as error: outcome=str(error)
                except Exception:
                    outcome='exception';report['traceback']=traceback.format_exc()
            report['cases'].append({'status':status,'physical_sends':len(sends),'requests':sends,
                                    'outcome':outcome,'ledger_calls':llm.ledger.calls,'pending':llm.ledger.pending,
                                    'halt_reason':llm.ledger.halt_reason,'usage':[{'in':c['in'],'out':c['out'],'reason':c['reason']} for c in llm.ledger.log]})
    return report

if __name__=='__main__':
    report=asyncio.run(diagnose())
    text=json.dumps(report,indent=2)
    if len(sys.argv)>1: Path(sys.argv[1]).write_text(text)
    else: print(text)

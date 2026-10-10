# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure native ACP readiness controls: no event loop, processes, sockets or signals."""
import asyncio,importlib.util,json,os,socket,subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'tests/qa/grok_worker_validation.py'
spec=importlib.util.spec_from_file_location('readiness_candidate',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
@pytest.fixture(autouse=True)
def no_process_socket_signal(monkeypatch):
 def refuse(*a,**k):raise AssertionError('Native/process/socket/signal forbidden')
 for n in ['run','Popen']:monkeypatch.setattr(subprocess,n,refuse)
 class NoSocket(socket.socket):
  def __new__(cls,*a,**k):return refuse()
 monkeypatch.setattr(socket,'socket',NoSocket)
 for n in ['kill','killpg','execv','execve','system']:monkeypatch.setattr(os,n,refuse)
 monkeypatch.setattr(asyncio,'new_event_loop',refuse)
 monkeypatch.setattr(asyncio,'create_subprocess_shell',refuse)
 monkeypatch.setattr(m,'deny_inet',refuse)
 monkeypatch.setattr(m,'enable_owned_reaping',refuse)
 class MockMonitor:
  def __init__(self,coroutine):self.coroutine=coroutine
  def cancel(self):self.coroutine.close()
  def __await__(self):
   async def cancelled():raise asyncio.CancelledError()
   return cancelled().__await__()
 monkeypatch.setattr(asyncio,'create_task',MockMonitor)
 monkeypatch.setattr(m,'process_rows',lambda:{})
 monkeypatch.setattr(m,'owned_snapshot',lambda *a:[])
 async def cleanup(*a):pass
 monkeypatch.setattr(m,'cleanup_acp',cleanup)
class Stream:
 def __init__(self,frames):self.frames=list(frames);self.pid=123;self.stdin=self;self.stdout=self;self.sent=[];self.completed=False;self.early_call=False;self.time_advance=lambda:None;self.on_done=lambda:None;self.block_drain=False
 def write(self,raw):
  value=json.loads(raw);self.sent.append(value)
  if value.get('method')=='_x.ai/mcp/call' and not self.completed:self.early_call=True
 async def drain(self):
  if self.block_drain and self.sent[-1]["method"]=="_x.ai/mcp/call":raise AssertionError("Unbounded mock drain reached")
 async def readline(self):
  self.time_advance()
  if not self.frames:raise asyncio.TimeoutError('Mock missing completion/response')
  f=self.frames.pop(0)
  if f.get('method')=='_x.ai/mcp_initialized' and isinstance(f.get('params'),dict) and f['params'].get('sessionId')=='s1' and type(f['params'].get('mcpToolCount')) is int and f['params']['mcpToolCount']>=0:self.completed=True;self.on_done()
  return (json.dumps(f)+'\n').encode()
def done(sid='s1',count=5):return {'method':'_x.ai/mcp_initialized','params':{'sessionId':sid,'mcpToolCount':count}}
async def exercise(tmp_path,monkeypatch,middle,reply=None,*,before_new=False,expire_on_done=False,block_drain=False):
 v=m.Validator(SimpleNamespace(output=tmp_path/'out',phase='stdio'))
 frames=[{'id':1,'result':{}}]+([done()] if before_new else [])+[{'id':2,'result':{'sessionId':'s1'}}]+middle+[reply or {'id':3,'result':{'result':{'content':[]}}}]
 stream=Stream(frames);budgets=[];loop=SimpleNamespace(time=lambda:0);offset=[0]
 monkeypatch.setattr(asyncio,'get_running_loop',lambda:loop)
 monkeypatch.setattr(loop,'time',lambda:offset[0]);stream.time_advance=lambda:offset.__setitem__(0,offset[0]+2)
 stream.block_drain=block_drain
 if expire_on_done:stream.on_done=lambda:offset.__setitem__(0,offset[0]+20)
 async def launch(*a,**k):return stream
 monkeypatch.setattr(asyncio,'create_subprocess_exec',launch)
 async def wait_for(awaitable,timeout):
  budgets.append(timeout)
  if block_drain and getattr(awaitable,"cr_code",None) is Stream.drain.__code__ and stream.sent[-1]["method"]=="_x.ai/mcp/call":
   awaitable.close();raise asyncio.TimeoutError("Mock write backpressure")
  assert timeout>0
  return await awaitable
 monkeypatch.setattr(asyncio,'wait_for',wait_for)
 error=None
 try:await v.acp(['NO_NATIVE'],{},tmp_path,'project-baseline')
 except Exception as e:error=e
 return v,stream,budgets,error

def run_immediate(coroutine):
 # Every fake await completes synchronously. An unexpected real wait is a failure,
 # never a hidden event-loop/socket fixture or a timing sleep.
 try:
  yielded=coroutine.send(None)
 except StopIteration as result:
  return result.value
 finally:
  coroutine.close()
 raise AssertionError(f'Unexpected asynchronous suspension: {yielded!r}')

def test_waits_actual_session_completion_before_call(tmp_path,monkeypatch):
 v,s,b,e=run_immediate(exercise(tmp_path,monkeypatch,[{'method':'_x.ai/mcp/init_progress','params':{'sessionId':'s1','total':5,'connected':3}},done()]))
 assert e is None;assert not s.early_call
 assert len([x for x in s.sent if x.get('method')=='_x.ai/mcp/call'])==1
 assert v.receipt['native_mcp_readiness'][0]['completion']==done()
 assert len(b)==8 and b[-1]==b[-2]<b[-3]<b[-4]<=20
@pytest.mark.parametrize('notification',[done('other'),done(count=True),done(count=-1),{'method':'_x.ai/mcp_initialized','params':None},{'method':'_x.ai/mcp/init_progress','params':{'sessionId':'s1','total':5,'connected':5}}])
def test_wrong_or_malformed_readiness_never_calls(tmp_path,monkeypatch,notification):
 v,s,b,e=run_immediate(exercise(tmp_path,monkeypatch,[notification]))
 assert isinstance(e,asyncio.TimeoutError)
 assert not any(x.get('method')=='_x.ai/mcp/call' for x in s.sent)
def test_unknown_server_after_completion_remains_failure(tmp_path,monkeypatch):
 v,s,b,e=run_immediate(exercise(tmp_path,monkeypatch,[done(count=0)],{'id':3,'error':{'code':-32603,'data':"server 'lampway_pane' not found"}}))
 assert isinstance(e,AssertionError) and 'owned native MCP call' in str(e)
 assert not s.early_call
 assert len([x for x in s.sent if x.get('method')=='_x.ai/mcp/call'])==1
 assert v.receipt['cases'][0]['passed'] is False
def test_notifications_already_before_new_response_are_accepted(tmp_path,monkeypatch):
 # The recorded prefix has completion before the last response; keep it session-bound.
 v,s,b,e=run_immediate(exercise(tmp_path,monkeypatch,[{'method':'_x.ai/mcp/server_status','params':{'sessionId':'s1','name':'lampway_pane','status':'ready','reason':'initialized'}}],before_new=True))
 assert e is None and not s.early_call
def test_deadline_expired_after_completion_emits_no_call(tmp_path,monkeypatch):
 v,s,b,e=run_immediate(exercise(tmp_path,monkeypatch,[done()],expire_on_done=True))
 assert isinstance(e,asyncio.TimeoutError)
 assert not any(x.get('method')=='_x.ai/mcp/call' for x in s.sent)

def test_write_backpressure_uses_remaining_original_budget(tmp_path,monkeypatch):
 v,s,b,e=run_immediate(exercise(tmp_path,monkeypatch,[done()],block_drain=True))
 assert isinstance(e,asyncio.TimeoutError)
 assert len([x for x in s.sent if x.get('method')=='_x.ai/mcp/call'])==1
 assert len(b)==6 and 0<b[-1]<20
 assert not s.frames==[]  # Reply never read after failed drain.

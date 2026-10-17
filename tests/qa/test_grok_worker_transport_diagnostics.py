# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable controlled seams: no native processes, sockets or signals."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import types
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location('grok_diagnostic', HERE / 'grok_worker_transport_diagnostics.py')
D = importlib.util.module_from_spec(spec); spec.loader.exec_module(D)


class Refusals(unittest.TestCase):
    def test_no_grant_refuses_before_process_socket_or_write(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(D.socket, 'if_nameindex', side_effect=AssertionError('socket seam')):
            with self.assertRaisesRegex(ValueError, 'slot grant'):
                D.admission_gate('a' * 40)

    def test_root_refused(self):
        with patch.dict(os.environ, {'LAMPWAY_GROK_DIAGNOSTIC_SLOT_AUTHORIZED': 'a'*40,
                'PYTHONDONTWRITEBYTECODE': '1'}, clear=True), patch.object(D.os, 'getuid', return_value=0):
            with self.assertRaisesRegex(ValueError, 'nonroot'):
                D.admission_gate('a'*40)

    def test_nonisolated_network_refused(self):
        with patch.dict(os.environ, {'LAMPWAY_GROK_DIAGNOSTIC_SLOT_AUTHORIZED': 'a'*40,
                'PYTHONDONTWRITEBYTECODE': '1'}, clear=True), patch.object(D.os, 'getuid', return_value=1000), \
                patch.object(D.socket, 'if_nameindex', return_value=[(1, 'lo'), (2, 'eth0')]):
            with self.assertRaisesRegex(ValueError, 'loopback'):
                D.admission_gate('a'*40)

    def test_exact_reviewed_qa_import_has_no_process_calls(self):
        with patch.object(D.asyncio, 'create_subprocess_exec', side_effect=AssertionError('native forbidden')):
            self.assertEqual(D.load_qa(REPO).GROK_SHA256,
                'c80de0155706ff2d995623887b102f2d0abd2c62b2643dea3a0cebaf7dd724d5')

    def test_actual_schema_four_cases(self):
        for transport in ('http', 'sse'):
            for name in ('foreign_transport', 'lampway_pane'):
                self.assertEqual(D.hostile(transport, name, 1234), {'type': transport, 'name': name,
                    'url': f'http://127.0.0.1:1234/foreign-{transport}', 'headers': []})

    def test_unreviewed_schema_refused(self):
        with self.assertRaises(ValueError): D.hostile('stdio', 'lampway_pane', 9)
        with self.assertRaises(ValueError): D.hostile('http', 'other', 9)

    def test_native_creation_refused_preserves_failure_and_stops(self):
        q = D.load_qa(REPO)
        with tempfile.TemporaryDirectory(dir=os.getenv('LAMPWAY_TEST_ROOT')) as directory:
            class V:
                output = Path(directory)
                receipt = {}
                def save(self):
                    (self.output / 'receipt.json').write_text(json.dumps(self.receipt))
            v = V()
            async def refused(*args, **kwargs):
                raise RuntimeError('CONTROLLED native creation refused')
            with patch.object(D.asyncio, 'create_subprocess_exec', refused):
                with self.assertRaisesRegex(RuntimeError, 'cleanup unproved'):
                    asyncio.run(D.case(v, q, ['/never-native'], {}, directory, 'http', 'lampway_pane'))
            evidence = json.loads((Path(directory) / 'receipt.json').read_text())['diagnostics'][0]
            self.assertIn('CONTROLLED native creation refused', evidence['failure'])
            self.assertTrue((Path(directory) / 'http-lampway_pane-traffic.json').exists())
            self.assertNotIn('canonical_survives', evidence)



def actual_request(proc, read):
    return D.ACPChannel(proc, [], lambda: None).request


class Writer:
    def __init__(self): self.writes=[];self.drains=0
    def write(self,data): self.writes.append(data)
    async def drain(self): self.drains+=1


class RPC(unittest.TestCase):
    def test_expired_request_never_writes(self):
        async def run():
            proc=types.SimpleNamespace(stdin=Writer())
            async def unread(deadline): raise AssertionError('expired request read')
            req=actual_request(proc,unread)
            with self.assertRaises(asyncio.TimeoutError):
                await req('initialize',{},asyncio.get_running_loop().time()-1)
            self.assertEqual(proc.stdin.writes,[])
            self.assertEqual(proc.stdin.drains,0)
        asyncio.run(run())



class FrameProcess:
    pid=424242
    returncode=None
    def __init__(self, *, retained=True, contact=False):
        self.queue=asyncio.Queue(); self.stdout=self; self.stdin=self
        self.writes=[]; self.drains=0; self.retained=retained; self.contact=contact; self.updated=False
        self.http=None
    async def readline(self): return await self.queue.get()
    async def drain(self): self.drains+=1
    def emit(self, frame): self.queue.put_nowait((json.dumps(frame)+'\n').encode())
    def write(self, body):
        self.writes.append(body); req=json.loads(body); method=req['method']; sid='owned-session'
        result={}
        if method=='initialize': result={'agentCapabilities':{'mcpCapabilities':{'http':True,'sse':True}}}
        elif method=='session/new':
            result={'sessionId':sid}
        elif method=='_x.ai/session/update_mcp_servers':
            self.updated=True
            if self.contact: self.http.events.append({'path':'/foreign-http','http_method':'POST'})
            self.emit({'jsonrpc':'2.0','method':'_x.ai/mcp/init_progress',
                'params':{'sessionId':sid,'total':1,'connected':1}})
            self.emit({'jsonrpc':'2.0','method':'_x.ai/mcp_initialized',
                'params':{'sessionId':sid,'mcpToolCount':1}})
            result={'result':{'ok':True}}
        elif method=='_x.ai/mcp/list':
            result={'result':{'sessionMcpResolved':True,'servers':[{'name':'lampway_pane',
                'session':{'enabled':True,'status':'ready' if self.retained or not self.updated else 'unavailable'}}]}}
        elif method=='_x.ai/mcp/call':
            result={'result':{'content':[{'type':'text','text':'swarm:owned:one'}]}}
        self.emit({'jsonrpc':'2.0','id':req['id'],'result':result})
        if method=='session/new':
            self.emit({'jsonrpc':'2.0','method':'_x.ai/mcp_initialized',
                'params':{'sessionId':sid,'mcpToolCount':1}})


class PositiveAndDeadlines(unittest.TestCase):
    def test_exact_frames_full_exchange_and_obligation_failures(self):
        q=D.load_qa(REPO)
        for retained,contact in ((True,False),(False,True)):
            async def exercise():
                with tempfile.TemporaryDirectory(dir=os.getenv('LAMPWAY_TEST_ROOT')) as folder:
                    proc=FrameProcess(retained=retained,contact=contact)
                    class V:
                        output=Path(folder)
                        receipt={}
                        http=types.SimpleNamespace(server_port=1234,events=[])
                        def save(self): (self.output/'receipt.json').write_text(json.dumps(self.receipt))
                    v=V();proc.http=v.http
                    row={'pid':proc.pid,'start':'synthetic-start','state':'S'}
                    async def spawn(*args,**kwargs): return proc
                    async def cleanup(*args,**kwargs): proc.returncode=-15
                    original_wait=asyncio.wait_for; budgets=[]
                    async def wait(awaitable,timeout):
                        budgets.append(timeout)
                        return await original_wait(awaitable,timeout)
                    with patch.object(D.asyncio,'create_subprocess_exec',spawn), \
                         patch.object(q,'process_rows',return_value={proc.pid:row}), \
                         patch.object(q,'owned_snapshot',return_value=[row]), \
                         patch.object(q,'cleanup_acp',cleanup), \
                         patch.object(q,'still_alive',return_value=False), \
                         patch.object(D.asyncio,'wait_for',wait):
                        await D.case(v,q,['synthetic-process-only'],{},folder,'http','lampway_pane')
                    observation=v.receipt['diagnostics'][0]
                    self.assertEqual(observation['diagnostic_status'],'MET' if retained else 'FAILED')
                    self.assertTrue(observation['restart_progress'])
                    self.assertEqual(observation['completion']['params']['sessionId'],'owned-session')
                    self.assertTrue(observation['cleanup']['all_pid_start_including_z_absent'])
                    self.assertTrue(budgets);self.assertTrue(all(0<b<=20 for b in budgets))
                    methods=[json.loads(w)['method'] for w in proc.writes]
                    self.assertEqual(methods,['initialize','session/new','_x.ai/mcp/list','_x.ai/mcp/call',
                        '_x.ai/session/update_mcp_servers','_x.ai/mcp/list','_x.ai/mcp/call'])
                    if not retained:
                        self.assertIn('canonical_survives',observation['failed_obligations'])
                        self.assertIn('hostile_endpoint_never_contacted',observation['failed_obligations'])
                        self.assertEqual(v.receipt['diagnostic_summary']['status'],'FAILED')
            asyncio.run(exercise())

    def test_cleanup_exception_keeps_evidence_and_stops(self):
        q=D.load_qa(REPO)
        async def run():
            with tempfile.TemporaryDirectory(dir=os.getenv('LAMPWAY_TEST_ROOT')) as folder:
                proc=FrameProcess()
                class V:
                    output=Path(folder)
                    receipt={}
                    http=types.SimpleNamespace(server_port=1234,events=[])
                    def save(self): (self.output/'receipt.json').write_text(json.dumps(self.receipt))
                v=V();proc.http=v.http
                async def spawn(*args,**kwargs): return proc
                async def cleanup(*args,**kwargs): raise RuntimeError('CONTROLLED cleanup refusal')
                row={'pid':proc.pid,'start':'synthetic-start','state':'S'}
                with patch.object(D.asyncio,'create_subprocess_exec',spawn), \
                     patch.object(q,'process_rows',return_value={proc.pid:row}), \
                     patch.object(q,'owned_snapshot',return_value=[row]), \
                     patch.object(q,'cleanup_acp',cleanup),patch.object(q,'still_alive',return_value=False):
                    with self.assertRaisesRegex(RuntimeError,'cleanup unproved'):
                        await D.case(v,q,['synthetic'],{},folder,'http','lampway_pane')
                observation=json.loads((Path(folder)/'receipt.json').read_text())['diagnostics'][0]
                self.assertIn('CONTROLLED cleanup refusal',observation['cleanup_error'])
                self.assertIn('owned_cleanup',observation['failed_obligations'])
                self.assertTrue((Path(folder)/'http-lampway_pane-traffic.json').exists())
        asyncio.run(run())

    def test_each_failed_obligation_is_visible(self):
        base={'label':'synthetic-control','canonical_survives':True,'owned_next_call':True,
              'hostile_endpoint_contact':False,'cleanup':{'all_pid_start_including_z_absent':True}}
        for key,value,failed in [('canonical_survives',False,'canonical_survives'),
                                 ('owned_next_call',False,'owned_next_call'),
                                 ('hostile_endpoint_contact',True,'hostile_endpoint_never_contacted')]:
            observation={**base,key:value}
            D.finalize_observation(observation)
            self.assertEqual(observation['failed_obligations'],[failed])
            self.assertEqual(D.diagnostic_summary([observation])['status'],'FAILED')
            self.assertFalse(D.diagnostic_summary([observation])['acceptance'])

    def test_expiry_after_write_refuses_drain(self):
        async def run():
            proc=types.SimpleNamespace(stdin=Writer())
            channel=D.ACPChannel(proc,[],lambda:None)
            times=iter([100,101])
            with patch.object(D.asyncio,'get_running_loop',return_value=types.SimpleNamespace(time=lambda:next(times))):
                with self.assertRaisesRegex(asyncio.TimeoutError,'before drain'):
                    await channel.request('initialize',{},100.5)
            self.assertEqual(len(proc.stdin.writes),1);self.assertEqual(proc.stdin.drains,0)
        asyncio.run(run())

    def test_expired_read_does_not_touch_stream(self):
        async def run():
            class Unread:
                async def readline(self): raise AssertionError('expired read touched stream')
            channel=D.ACPChannel(types.SimpleNamespace(stdout=Unread()),[],lambda:None)
            with self.assertRaises(asyncio.TimeoutError):
                await channel.read(asyncio.get_running_loop().time()-1)
        asyncio.run(run())


class CheckoutGuards(unittest.TestCase):
    def test_nonhex_head_refused_before_any_git(self):
        with patch.dict(D.os.environ,{'LAMPWAY_GROK_DIAGNOSTIC_SLOT_AUTHORIZED':'z'*40},clear=True):
            with self.assertRaisesRegex(ValueError,'slot grant'): D.admission_gate('z'*40)

    def test_dirty_or_mismatched_checkout_refused(self):
        for outputs in (['b'*40],['a'*40,' M tracked.py']):
            with patch.object(D.subprocess,'run',side_effect=[types.SimpleNamespace(stdout=x) for x in outputs]):
                with self.assertRaises(ValueError): D.check_checkout(Path('/synthetic-checkout'),'a'*40)

    def test_clean_matching_checkout_uses_supplied_path(self):
        with patch.object(D.subprocess,'run',side_effect=[types.SimpleNamespace(stdout='a'*40),
                types.SimpleNamespace(stdout='')]) as git:
            self.assertEqual(D.check_checkout(Path('/synthetic-checkout'),'a'*40),Path('/synthetic-checkout'))
            self.assertTrue(all(c.args[0][:3]==['git','-C','/synthetic-checkout'] for c in git.call_args_list))




if __name__ == '__main__':
    unittest.main()

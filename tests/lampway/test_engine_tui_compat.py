# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Controlled native-copy patching and real display-controller race controls."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import os

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/lampway/engine_tui_compat.py"
spec = importlib.util.spec_from_file_location("engine_tui_compat_test", SCRIPT)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


def source_copy(tmp_path):
    for name in compat.TARGETS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "third_party/hermes-agent" / name, target)
    return tmp_path


def test_normal_copy_extends_original_native_undo_once(tmp_path):
    source = source_copy(tmp_path)
    receipt = compat.apply(source)
    core = (source / "ui-tui/src/app/slash/commands/core.ts").read_text()
    assert "if (!requestNativeHistoryRefresh(ctx.sid!, () =>" in core
    assert "ctx.transcript.trimLastExchange(prev)" in core
    assert core.count("rpc<SessionUndoResponse>('session.undo'") == 2  # original undo and retry
    main = (source / "ui-tui/src/app/useMainApp.ts").read_text()
    assert "markFrontendNotice({ role: 'system', text })" in main
    assert "isNativeHistoryReplacement(value)" in main
    assert receipt["protocol"] == 1
    assert set(receipt["sources"]) == set(compat.TARGETS)
    assert (source / "ui-tui/src/app/lampwayHistory.ts").read_bytes() == (
        ROOT / "scripts/lampway/hermes_tui/lampwayHistory.ts").read_bytes()


def test_changed_native_source_refuses_before_any_patch(tmp_path):
    source = source_copy(tmp_path)
    names = list(compat.TARGETS)
    untouched = (source / names[0]).read_bytes()
    (source / names[1]).write_text("planted incompatible source")
    with pytest.raises(ValueError, match="unsupported native TUI source"):
        compat.apply(source)
    assert (source / names[0]).read_bytes() == untouched
    assert not (source / "ui-tui/src/app/lampwayHistory.ts").exists()


@pytest.mark.skipif(os.environ.get("LAMPWAY_TEST_ENGINE_TUI_COMPAT") != "1",
                   reason="requires explicit pinned engine pure TUI compiler/controller qualification")
def test_real_controller_rejects_late_snapshots_and_keeps_legacy_path():
    typescript = ROOT / "build/engines/hermes/v2026.9.24/src/node_modules/typescript"
    assert typescript.is_dir(), "pure TS compiler prerequisite must be installed"
    helper = ROOT / "scripts/lampway/hermes_tui/lampwayHistory.ts"
    result = subprocess.run(["node", "-e", NODE_CONTROL, str(typescript), str(helper),
        str(ROOT / "third_party/hermes-agent/ui-tui/src/lib/messages.ts")],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "native-history controls passed"


@pytest.mark.skipif(os.environ.get("LAMPWAY_TEST_ENGINE_TUI_COMPAT") != "1",
                   reason="requires explicit pinned engine pure TUI compiler/controller qualification")
def test_patched_native_tui_typechecks_without_build_or_emission(tmp_path):
    native = ROOT / "build/engines/hermes/v2026.9.24/src"
    shutil.copytree(ROOT / "third_party/hermes-agent/ui-tui", tmp_path / "ui-tui",
                    ignore=shutil.ignore_patterns("node_modules", "dist", "__tests__"))
    (tmp_path / "node_modules").symlink_to(native / "node_modules", target_is_directory=True)
    compat.apply(tmp_path)
    guard = tmp_path / "pure-compiler.cjs"
    guard.write_text("const deny=()=>{throw Error('pure compiler forbids effect')};\n"
        "const cp=require('node:child_process');\n"
        "for(const k of ['spawn','spawnSync','exec','execSync','execFile','execFileSync','fork'])cp[k]=deny;\n"
        "require('node:net').Socket.prototype.connect=deny;process.kill=deny;\n")
    result = subprocess.run(["node", "--require", str(guard),
        str(native / "node_modules/typescript/bin/tsc"), "--noEmit", "-p", str(tmp_path / "ui-tui")],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "ui-tui/dist").exists()


NODE_CONTROL = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require(process.argv[1]);
const Module = require('node:module');
const cp = require('node:child_process');
const deny = () => { throw new Error('pure test forbids process/network/signal'); };
for (const key of ['spawn','spawnSync','exec','execSync','execFile','execFileSync','fork']) cp[key] = deny;
require('node:net').Socket.prototype.connect = deny;
require('node:http').request = require('node:https').request = deny;
process.kill = deny;
const compiled = ts.transpileModule(fs.readFileSync(process.argv[2], 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2023 }
}).outputText;
const loaded = new Module('owned-history-controller');
loaded._compile(compiled, 'owned-history-controller.cjs');
const { createNativeHistoryRefresh } = loaded.exports;
const tick = async () => { for (let n=0; n<12; n++) await Promise.resolve(); };
const marker = revision => ({lampway_history:{protocol:1,revision,reason:'undo'},running:false});
(async () => {
  let sid='one', idle=true;
  const pending=[], rendered=[];
  const controller=createNativeHistoryRefresh({sid:()=>sid,idle:()=>idle,
    read:s=>new Promise((resolve,reject)=>pending.push({sid:s,resolve,reject})),
    replace:rows=>rendered.push(rows)});
  assert.equal(controller.request(sid),false); // original native frontend
  controller.event('session.info',{running:false}); await tick();
  assert.equal(pending.length,0);
  controller.event('session.info',{running:false,lampway_history:{protocol:1,revision:0}}); await tick();
  controller.event('message.complete'); await tick();
  assert.equal(pending.length,0); // ordinary/resume rendering stays native
  controller.event('session.info',marker(2)); await tick();
  assert.equal(pending.length,1);
  controller.event('session.info',marker(3)); await tick();
  assert.equal(pending.length,1); // coalesced while first read is outstanding
  pending[0].resolve({protocol:1,session_id:sid,revision:2,history:{messages:['stale']}});
  await tick(); assert.deepEqual(rendered,[]); assert.equal(pending.length,2);
  pending[1].resolve({protocol:1,session_id:sid,revision:3,history:{messages:['keep']}});
  await tick(); assert.deepEqual(rendered,[['keep']]);
  assert.equal(controller.request(sid),true); await tick();
  idle=false; controller.event('message.start');
  pending[2].resolve({protocol:1,session_id:sid,revision:3,history:{messages:['old']}});
  await tick(); assert.deepEqual(rendered,[['keep']]);
  idle=true; controller.event('session.info',marker(4)); await tick();
  sid='two'; controller.event('session.info',marker(1)); await tick();
  pending[3].resolve({protocol:1,session_id:'one',revision:4,history:{messages:['old session']}});
  await tick(); assert.deepEqual(rendered,[['keep']]);
  assert.equal(pending[4].sid,'two');
  pending[4].resolve({protocol:1,session_id:'two',revision:1,history:{messages:['new session']}});
  await tick(); assert.deepEqual(rendered,[['keep'],['new session']]);
  assert.equal(controller.request('one'),false);
  controller.event('session.info',marker(2)); await tick();
  pending[5].reject(new Error('native busy refusal')); await tick();
  assert.equal(pending.length,6); // refusal cannot cause an automatic retry loop
  assert.deepEqual(rendered,[['keep'],['new session']]);
  let acknowledgements=0;
  assert.equal(controller.request('two',()=>{
    assert.deepEqual(rendered.at(-1),['authoritative undo']);
    acknowledgements++;
  }),true);
  await tick();
  pending[6].resolve({protocol:1,session_id:'two',revision:2,history:{messages:['authoritative undo']}});
  await tick();
  controller.event('session.info',marker(2)); await tick();
  assert.equal(acknowledgements,1); assert.equal(pending.length,7);

  const { markFrontendNotice, retainFrontendNotices, nativeHistoryReplacement, isNativeHistoryReplacement }=loaded.exports;
  const nativeSource=ts.createSourceFile('messages.ts',fs.readFileSync(process.argv[3],'utf8'),ts.ScriptTarget.ES2023,true);
  let initializer;
  for(const statement of nativeSource.statements) {
    if(ts.isVariableStatement(statement))for(const declaration of statement.declarationList.declarations)
      if(declaration.name.getText(nativeSource)==='appendTranscriptMessage')initializer=declaration.initializer.getText(nativeSource);
  }
  assert.ok(initializer);
  const nativeAppend=ts.transpileModule('const appendTranscriptMessage='+initializer+'; exports.append=appendTranscriptMessage;',{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2023}}).outputText;
  const nativeModule=new Module('native-pure-append');
  nativeModule._compile('const appendToolShelfMessage=(prev,msg)=>[...prev,msg];'+nativeAppend,'native-pure-append.cjs');
  const original={role:'system',text:'native /status output'};
  markFrontendNotice(original);
  const cloned=nativeModule.exports.append([],original)[0];
  assert.notEqual(cloned,original);assert.ok(cloned.createdAt);
  assert.equal(JSON.stringify(cloned),JSON.stringify({role:original.role,text:original.text,createdAt:cloned.createdAt}));
  const slash={kind:'slash',role:'system',text:'/status'};
  const panel={kind:'panel',role:'system',text:'',panelData:{title:'native panel'}};
  const durableSystem={role:'system',text:'durable native system message'};
  const oldUser={role:'user',text:'removed native user'};
  const notices=retainFrontendNotices([oldUser,slash,cloned,durableSystem,panel]);
  assert.deepEqual(notices,[slash,cloned,panel]);
  const nativeRows=[{role:'user',text:'archived user'},{role:'assistant',text:'native surviving answer'}];
  const combined=[...nativeRows,...notices];
  assert.deepEqual(combined.slice(0,2),nativeRows);assert.deepEqual(combined.slice(2),[slash,cloned,panel]);
  const setter=nativeHistoryReplacement(previous=>combined);
  assert.equal(isNativeHistoryReplacement(setter),true);
  assert.equal(isNativeHistoryReplacement(previous=>previous),false);

  console.log('native-history controls passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""

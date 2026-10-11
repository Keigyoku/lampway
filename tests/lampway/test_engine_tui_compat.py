# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Controlled native-copy patching and real display-controller race controls."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import os
import re
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/lampway/engine_tui_compat.py"
spec = importlib.util.spec_from_file_location("engine_tui_compat_test", SCRIPT)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)
engine_spec = importlib.util.spec_from_file_location(
    "engine_env_tui_test", ROOT / "scripts/lampway/engine_env.py")
engine_env = importlib.util.module_from_spec(engine_spec)
engine_spec.loader.exec_module(engine_env)


def installed_tui_source():
    plan = engine_env.resolve()
    dest = Path(plan["dest"])
    manifest = dest / "engine.json"
    assert manifest.is_file(), f"normal pinned engine manifest must be installed at {manifest}"
    record = json.loads(manifest.read_text())
    expected = json.loads(plan["record"])
    assert isinstance(record, dict), "normal pinned engine manifest must be an object"
    for key, value in expected.items():
        assert record.get(key) == value, f"normal pinned engine manifest mismatch: {key}"
    return dest / expected["source"]


@pytest.fixture
def tagless_engine(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    checkout = root / engine_env.SUBMODULE
    checkout.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\nname='synthetic-hermes'\n")
    pin = "a" * 40
    outputs = {
        ("ls-files", "-s", engine_env.SUBMODULE): f"160000 {pin} 0\t{engine_env.SUBMODULE}",
        ("ls-tree", "HEAD", engine_env.SUBMODULE): f"160000 commit {pin}\t{engine_env.SUBMODULE}",
        ("rev-parse", "HEAD"): pin,
        ("tag", "--points-at", "HEAD"): "",
    }
    monkeypatch.setitem(globals(), "ROOT", root)
    monkeypatch.setattr(engine_env, "ROOT", root)
    monkeypatch.setattr(engine_env, "_git", lambda *args, **kwargs:
                        SimpleNamespace(stdout=outputs[args]))
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(tmp_path / "engines"))
    plan = engine_env.resolve()
    dest = Path(plan["dest"])
    typescript = dest / "src/node_modules/typescript"
    typescript.mkdir(parents=True)
    manifest = dest / "engine.json"
    manifest.write_text(plan["record"])
    return SimpleNamespace(plan=plan, manifest=manifest, typescript=typescript,
                           outputs=outputs)


def test_controller_prerequisite_accepts_normal_tagless_sha_destination(tagless_engine, monkeypatch):
    calls = []

    def controlled_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="native-history controls passed\n", stderr="")

    monkeypatch.setattr(subprocess, "run", controlled_run)
    test_real_controller_rejects_late_snapshots_and_keeps_legacy_path()
    assert len(calls) == 1
    assert Path(calls[0][3]) == tagless_engine.typescript
    assert tagless_engine.plan["tag"] == tagless_engine.plan["commit"][:12]


@pytest.mark.parametrize("tagged", [False, True], ids=["sha", "release-tag"])
def test_prerequisite_uses_normal_default_engine_root(tagless_engine, monkeypatch, tagged):
    old_dest = Path(tagless_engine.plan["dest"])
    monkeypatch.delenv("LAMPWAY_ENGINES_DIR")
    if tagged:
        tagless_engine.outputs[("tag", "--points-at", "HEAD")] = "v2026.9.24"
    plan = engine_env.resolve()
    dest = Path(plan["dest"])
    dest.parent.mkdir(parents=True)
    old_dest.rename(dest)
    # Extra normal-build compatibility metadata does not change the engine pin.
    record = json.loads(plan["record"])
    record["lampway_tui_compatibility"] = {"protocol": 1}
    (dest / "engine.json").write_text(json.dumps(record))
    assert installed_tui_source() == dest / "src"


@pytest.mark.parametrize("field", ["engine", "tag", "commit", "python", "extras",
                                   "source", "entry", "hermes", "tui"])
def test_prerequisite_refuses_mismatched_normal_manifest(tagless_engine, monkeypatch, field):
    record = json.loads(tagless_engine.manifest.read_text())
    record[field] = "foreign"
    tagless_engine.manifest.write_text(json.dumps(record))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("compiler must not start"))
    with pytest.raises(AssertionError, match=f"manifest mismatch: {field}"):
        test_real_controller_rejects_late_snapshots_and_keeps_legacy_path()


@pytest.mark.parametrize("contents", [None, "not JSON", "[]"])
def test_prerequisite_refuses_missing_or_malformed_manifest(tagless_engine, contents):
    if contents is None:
        tagless_engine.manifest.unlink()
    else:
        tagless_engine.manifest.write_text(contents)
    with pytest.raises((AssertionError, ValueError)):
        installed_tui_source()


def test_prerequisite_preserves_checkout_pin_refusal(tagless_engine):
    tagless_engine.outputs[("rev-parse", "HEAD")] = "b" * 40
    with pytest.raises(engine_env.Refusal, match="not the pinned"):
        installed_tui_source()


def test_selected_controller_still_requires_installed_compiler(tagless_engine):
    tagless_engine.typescript.rmdir()
    with pytest.raises(AssertionError, match="pure TS compiler prerequisite must be installed"):
        test_real_controller_rejects_late_snapshots_and_keeps_legacy_path()


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
    typescript = installed_tui_source() / "node_modules/typescript"
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
    native = installed_tui_source()
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


@pytest.mark.skipif(os.environ.get("LAMPWAY_TEST_ENGINE_TUI_COMPAT") != "1",
                   reason="requires explicit pinned engine pure TUI compiler/controller qualification")
@pytest.mark.parametrize("control", ["external-users", "ahead-snapshot"])
def test_real_controller_tracks_new_native_display_revisions(control):
    typescript = installed_tui_source() / "node_modules/typescript"
    assert typescript.is_dir(), "pure TS compiler prerequisite must be installed"
    helper = ROOT / "scripts/lampway/hermes_tui/lampwayHistory.ts"
    result = subprocess.run(["node", "-e", NODE_CONTROL.partition("(async () =>")[0]
        + NODE_DISPLAY_REVISION[control], str(typescript), str(helper)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "native-display revision controls passed"


NODE_DISPLAY_REVISION = {
    "external-users": r"""
(async () => {
  const {markFrontendNotice,retainFrontendNotices}=loaded.exports;
  let idle=true, reads=0;
  const nativeDisplay=[{role:'user',content:'archived native USER'},
    {role:'assistant',content:'archived native answer'},
    {role:'system',content:'native compression DISPLAY summary'}];
  const slash={kind:'slash',role:'system',text:'/compress'};
  // Native timestamp cloning must retain Symbol provenance and ordinary JSON.
  const notice={...markFrontendNotice({role:'system',text:'native compression completed'}),createdAt:42};
  const panel={kind:'panel',role:'system',text:'',panelData:{title:'native pending review'}};
  let transcript=[...nativeDisplay,slash,notice,panel],revision=4;
  const controller=createNativeHistoryRefresh({sid:()=> 'same-native-session',idle:()=>idle,
    read:async sid=>{reads++;return {protocol:1,session_id:sid,revision,
      history:{count:nativeDisplay.length,messages:[...nativeDisplay]}};},
    replace:rows=>{transcript=[...rows,...retainFrontendNotices(transcript)];}});
  const info=()=>({running:!idle,lampway_history:{protocol:1,revision}});
  controller.event('session.info',info());await tick();
  controller.event('message.complete');await tick();
  assert.equal(reads,0,'first native info only establishes a baseline');
  for (let n=1;n<=3;n++) {
    idle=false;controller.event('message.start');
    nativeDisplay.push({role:'user',content:'external USER '+n},
      {role:'assistant',content:'native answer '+n});revision++;
    controller.event('session.info',info());await tick();
    assert.equal(reads,n-1,'busy native transcript must not be replaced');
    idle=true;controller.event('session.info',info());await tick();
    assert.equal(reads,n,'advanced native revision must mirror each external USER row');
    assert.deepEqual(transcript,[...nativeDisplay,slash,notice,panel]);
    assert.equal(transcript.filter(row=>row.content==='external USER '+n).length,1);
    assert.ok(transcript.some(row=>row.content==='archived native USER'));
    assert.ok(transcript.some(row=>row.content==='native compression DISPLAY summary'));
    const unchanged=transcript;
    controller.event('session.info',info());controller.event('message.complete');await tick();
    assert.equal(reads,n,'same-revision ordinary info must not fetch or redraw');
    assert.equal(transcript,unchanged);
    assert.deepEqual(retainFrontendNotices(transcript),[slash,notice,panel]);
  }
  console.log('native-display revision controls passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
""",
    "ahead-snapshot": r"""
(async () => {
  let reads=0;
  const rendered=[];
  const controller=createNativeHistoryRefresh({sid:()=> 'same-native-session',idle:()=>true,
    read:async sid=>{reads++;return {protocol:1,session_id:sid,revision:10,
      history:{messages:['native display already at revision10']}};},
    replace:rows=>rendered.push(rows)});
  const info=revision=>({running:false,lampway_history:{protocol:1,revision}});
  controller.event('session.info',info(5));await tick();assert.equal(reads,0);
  assert.equal(controller.request('same-native-session'),true);await tick();
  assert.equal(reads,1);assert.deepEqual(rendered,[['native display already at revision10']]);
  for (const revision of [7,9,10]) {
    controller.event('session.info',info(revision));controller.event('message.complete');await tick();
    assert.equal(reads,1,'intermediate info behind the accepted snapshot must stay quiet');
    assert.equal(rendered.length,1);
  }
  console.log('native-display revision controls passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
""",
}


@pytest.mark.skipif(os.environ.get("LAMPWAY_TEST_ENGINE_TUI_COMPAT") != "1",
                   reason="requires explicit pinned engine pure TUI compiler/controller qualification")
def test_native_handler_recreation_retains_gateway_owned_history_controller(tmp_path):
    typescript = installed_tui_source() / "node_modules/typescript"
    assert typescript.is_dir(), "pure TS compiler prerequisite must be installed"
    source = source_copy(tmp_path)
    compat.apply(source)
    event = (source / "ui-tui/src/app/createGatewayEventHandler.ts").read_text()
    factory = re.search(r"const nativeHistory = (\w+)\(", event).group(1)
    helper = ROOT / "scripts/lampway/hermes_tui/lampwayHistory.ts"
    result = subprocess.run(["node", "-e", NODE_CONTROL.partition("(async () =>")[0]
        + NODE_HANDLER_LIFETIME, str(typescript), str(helper), factory],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "native gateway lifetime controls passed"


NODE_HANDLER_LIFETIME = r"""
(async () => {
  const factoryName=process.argv[3],factory=loaded.exports[factoryName];
  assert.equal(typeof factory,'function');
  const owner={},otherOwner={},reads=[],rendered=[];
  let sid='native-one',idle=true,revision=4,generation=0;
  const nativeDisplay=['archived USER','native compressed DISPLAY'];
  function handler(gateway=owner) {
    const currentGeneration=++generation;
    const ctx={sid:()=>sid,idle:()=>idle,
      read:requestedSid=>new Promise((resolve,reject)=>reads.push({sid:requestedSid,resolve,reject})),
      replace:rows=>rendered.push({generation:currentGeneration,rows})};
    return factoryName==='createNativeHistoryRefresh' ? factory(ctx) : factory(gateway,ctx);
  }
  const info=()=>({running:!idle,lampway_history:{protocol:1,revision}});
  handler().event('session.info',info());await tick();assert.equal(reads.length,0);
  // Native React renders recreate this handler via composer/session callbacks.
  for(let n=1;n<=3;n++) {
    idle=false;let current=handler();current.event('message.start');
    nativeDisplay.push('external USER '+n,'native answer '+n);revision++;
    current.event('session.info',info());await tick();assert.equal(reads.length,n-1);
    idle=true;current=handler();const freshGeneration=generation;
    current.event('session.info',info());await tick();
    assert.equal(reads.length,n,'handler recreation must not lose the native revision baseline');
    reads[n-1].resolve({protocol:1,session_id:sid,revision,history:{messages:[...nativeDisplay]}});
    await tick();assert.deepEqual(rendered[n-1],{generation:freshGeneration,rows:[...nativeDisplay]});
    handler().event('session.info',info());await tick();assert.equal(reads.length,n);
  }
  let current=handler();assert.equal(current.request(sid),true);await tick();
  const oldRead=reads.at(-1),count=rendered.length;
  // Replace callback context while an actual snapshot is pending; fresh busy
  // state must reject it, and a later idle event uses the latest replacement.
  idle=false;handler();oldRead.resolve({protocol:1,session_id:sid,revision,history:{messages:['busy stale']}});
  await tick();assert.equal(rendered.length,count);
  idle=true;current=handler();const idleGeneration=generation;
  current.event('message.complete');await tick();
  reads.at(-1).resolve({protocol:1,session_id:sid,revision,history:{messages:['fresh context']}});
  await tick();assert.deepEqual(rendered.at(-1),{generation:idleGeneration,rows:['fresh context']});
  // An independent native gateway cannot borrow another gateway's admission.
  const other=handler(otherOwner);assert.equal(other.request(sid),false);
  other.event('session.info',info());await tick();const beforeOther=reads.length;
  other.event('message.complete');await tick();assert.equal(reads.length,beforeOther);
  // Pending old-session rows must not enter the newly focused session.
  current=handler();current.request(sid);await tick();const oldSession=reads.at(-1);
  sid='native-two';revision=0;current=handler();current.event('session.info',info());
  oldSession.resolve({protocol:1,session_id:'native-one',revision:7,history:{messages:['wrong session']}});
  await tick();assert.ok(!rendered.some(r=>r.rows.includes('wrong session')));
  assert.equal(current.request('native-one'),false);
  // Actual gateway reset invalidates a pending snapshot even after rebinding.
  current.request(sid);await tick();const beforeReset=reads.at(-1),beforeRender=rendered.length;
  handler().event('gateway.reconnecting');
  beforeReset.resolve({protocol:1,session_id:sid,revision:0,history:{messages:['old gateway']}});
  await tick();assert.equal(rendered.length,beforeRender);
  assert.equal(handler().request(sid),false);
  console.log('native gateway lifetime controls passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""

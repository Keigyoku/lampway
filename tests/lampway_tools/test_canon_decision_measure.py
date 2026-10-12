# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual native decision pack: candidate measurements without selecting defaults."""
import json
import numpy as np
from blender_run import run_script
from test_wave3_weights import PRE
from test_canon_normalize_facing import FACING
from test_canon_pair_scale import pair


def test_owner_measurement_pack_records_plate_gap_and_both_pair_modes(tmp_path):
    b,p=pair(tmp_path)
    body=np.load(b);piece=np.load(p)
    raw={k:piece[k].tolist() for k in ('V','T')}
    bd={k:body[k].tolist() for k in ('V','T','J','names')}
    script=PRE+FACING+'\npair_data='+repr(raw)+'\nbody_data='+repr(bd)+r'''
from mixar.modules.lampway_tools.pipeline import decision_measure as D
np.savez(os.path.join(root,'pair.npz'),V=pair_data['V'],T=pair_data['T'])
np.savez(os.path.join(root,'body.npz'),V=body_data['V'],T=body_data['T'],J=body_data['J'],names=body_data['names'])
before=CA.SETTINGS['facing_margin']['value']
config={'max_samples':8,'image_size':64,'jobs':[
 {'id':'plate','action':'facing','args':{'object':'raw','plate':'Front.png'}},
 {'id':'pair','action':'pair','args':{'kind':'gauntlets','piece':'pair.npz','body':'body.npz'}}]}
r=D.measure(config,root)
assert CA.SETTINGS['facing_margin']['value']==before
res(r)
'''
    result=run_script(script,env={'LW_KEEP_ROOT':str(tmp_path)},timeout=300)
    assert result.rc==0,result.out[-2500:]
    data=result.results[-1]
    assert all(r['ok'] for r in data['jobs']),data
    facing,paired=data['jobs']
    assert len(facing['result']['ranking'])==4 and facing['result']['gap']>.5
    assert {r['mode'] for r in paired['candidates']}=={'common','per_side'}
    assert all(len(r['views'])==3 for r in paired['candidates'])
    assert not data['default_choices_applied']
    (tmp_path/'measurement-proof.json').write_text(json.dumps(data,indent=2)+'\n')

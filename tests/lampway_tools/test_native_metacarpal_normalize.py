# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native MetaHuman metacarpals may fan out beside named finger continuation."""
from blender_run import run_script
from test_canon_normalize_rigged import PRE,RIG


def test_normalized_metacarpals_follow_finger01_not_slide_helpers():
    r=run_script(PRE+RIG+r'''
for side,sign in (('l',1),('r',-1)):
    for i,finger in enumerate(('thumb','index','middle','ring','pinky')):
        base=f'{finger}_metacarpal_{side}'
        if finger!='thumb':J[base]=(sign*.41,.015*(i-2),.60);P[base]=f'hand_{side}'
        for n in (1,2,3):
            name=f'{finger}_{n:02d}_{side}'
            J[name]=(sign*(.42+.025*n),.015*(i-2),.60)
            P[name]=(f'hand_{side}' if finger=='thumb' else base) if n==1 else f'{finger}_{n-1:02d}_{side}'
        for n,tag in ((1,'side_inn'),(2,'half')):
            helper=f'{finger}_{n:02d}_{tag}_{side}'
            J[helper]=(sign*(.42+.025*n+.01),.015*(i-2)+.01,.605);P[helper]=f'{finger}_{n:02d}_{side}'
        slide=f'{finger}_metacarpal_slide_{side}'
        if finger!='thumb':J[slide]=(sign*.41,.015*(i-2)+.02,.62);P[slide]=base
arm=build('mh_metacarpals');r=api.normalize_rigged(armature=arm.name,profile='metahuman',dry_run=False)
doc=json.loads(arm['lw_canon']) if 'lw_canon' in arm.keys() else {}
rows={b['name']:b for b in doc.get('body',{}).get('bones',[])}
res({'result':r,'rows':{n:v for n,v in rows.items() if '_metacarpal_' in n},'errors':CA.validate(doc) if doc else ['no document']})
''',timeout=300)
    assert r.rc==0,r.out[-2500:]
    got=r.results[-1]
    assert got['result']['ok'],got['result']
    assert not got['errors']
    for side,sign in (('l',1),('r',-1)):
        for finger in ('index','middle','ring','pinky'):
            row=got['rows'][f'{finger}_metacarpal_{side}']
            assert row['along_source']=='named_continuation'
            assert abs(row['along'][0]-sign)<1e-6 and abs(row['along'][1])<1e-6 and abs(row['along'][2])<1e-6

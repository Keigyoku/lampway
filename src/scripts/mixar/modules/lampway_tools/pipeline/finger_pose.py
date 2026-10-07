# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon08B5: curl fingers TO a target using canon-owned axes and curl_delta.

No imported bone tail is used: directions follow canonical named joint continuations,
including the canon's leaf continuation. The thumb is part of the target set.
"""
import math
import numpy as np
from .. import canon_geom as G

FINGERS=('index','middle','ring','pinky','thumb')
TARGETS={1:80.,2:95.,3:60.}
FRACTIONS=(0.,1/3,1/2,2/3,1.)


def entries(ref, side, fraction):
    if side not in ('l','r') or isinstance(fraction,bool) or not isinstance(fraction,(int,float)) or not math.isfinite(fraction) or not 0<=fraction<=1:
        raise ValueError('finger curl needs side l|r and a finite fraction in 0..1')
    names=[f'hand_{side}']+[f'{f}_{n:02d}_{side}' for f in FINGERS for n in (1,2,3)]
    if any(n not in ref for n in names):
        raise ValueError('finger curl needs the hand and all three joints of every finger, including thumb')
    # Include intervening metacarpals, but exclude unrelated corrective branches.
    selected=set(names)
    for n in names[1:]:
        p=ref[n]['parent']
        seen=set()
        while p and p!=f'hand_{side}':
            if p in seen or p not in ref:
                raise ValueError('finger parent chain is cyclic or incomplete')
            seen.add(p);selected.add(p);p=ref[p]['parent']
    heads={n:ref[n]['pos'] for n in ref if n in selected}
    parents={n:ref[n]['parent'] if ref[n]['parent'] in selected else None for n in heads}
    ends=G.chain_ends(heads,parents,main_child={f'hand_{side}':f'middle_01_{side}'})
    hand,index,middle,pinky=(heads[f'{n}_{side}'] for n in ('hand','index_01','middle_01','pinky_01'))
    axis=G.finger_axis(hand,index,middle,pinky,side)
    out=[]
    for f in FINGERS:
        for n in (1,2,3):
            b=f'{f}_{n:02d}_{side}';p=parents[b]
            if p is None:
                raise ValueError(f'{b}: curl needs the parent segment')
            direction=np.asarray(ends[b])-heads[b]
            parent_direction=np.asarray(ends[p])-heads[p]
            own_axis=G.flex_axis(direction,hand,index,middle,pinky,side) if f=='thumb' else axis
            target=TARGETS[n]*float(fraction)
            out.append({'bone':b,'axis':list(own_axis),'deg':float(G.curl_delta(parent_direction,direction,own_axis,target)),
                        'target_deg':target,'fraction':float(fraction)})
    return out

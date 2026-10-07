# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded candidate tables for owner measurements, never canonical defaults.

Ranges absent from canon are experimental envelopes. Results on actual pieces
must precede any recommendation/ruling. The caller supplies a measured anatomical
expectation for the first DOF; the normal engine refuses a reversed sign.
"""


def candidate(kind, expect, threshold_m, side='l'):
    import math
    if isinstance(threshold_m,bool) or not isinstance(threshold_m,(int,float)) or not math.isfinite(threshold_m) or threshold_m<=0:
        raise ValueError('candidate needs an explicit positive region threshold_m')
    if side not in ('l','r') or not isinstance(expect,dict) or 'joint' not in expect:
        raise ValueError('candidate needs side l|r and the first DOF sign expectation')
    def d(bone,axis,lo=-8,hi=8,step=4):
        return {'bone':bone,'axis':axis,'range':[lo,hi],'step':step}
    if kind=='waist':
        dofs=[d('pelvis','lateral')]
        chain=[d('spine_01','lateral')]+[d(f'thigh_{s}',a) for s in ('l','r') for a in ('-lateral','forward')]
        bones=['pelvis','spine_01','thigh_l','thigh_r']
    elif kind=='boots':
        dofs=[d(f'foot_{side}','-lateral')]
        chain=[d(f'foot_{side}','forward'),d(f'calf_{side}','-lateral',0,8,4)]
        bones=[f'{b}_{side}' for b in ('calf','foot','ball')]
    elif kind=='gauntlets':
        dofs=[d(f'hand_{side}',{'line':[f'index_01_{side}',f'pinky_01_{side}']},-30,30,5)]
        chain=[d(f'lowerarm_{side}',{'line':[f'lowerarm_{side}',f'hand_{side}']},-15,15,5)]
        bones=[f'{b}_{side}' for b in ('lowerarm','hand')]+[f'{f}_{n:02d}_{side}' for f in ('index','middle','ring','pinky','thumb') for n in (1,2,3)]
    else: raise ValueError('candidate kind is waist | boots | gauntlets')
    dofs[0]['expect']=dict(expect)
    result={'kind':kind,'dofs':dofs,'chain':chain,'regions':{'piece':{'bones':bones,'threshold_m':float(threshold_m)}},
            'status':'measurement candidate, not a canon table or recommended default',
            'source':'canon08H1 incomplete ranges; candidate steps/envelopes require measured approval',
            'limits':'Explicit caller region threshold; report sensitivity before adopting a physical acceptance value'}
    if kind=='gauntlets': result.update(curl_side=side,curl_fractions=[0,1/3,1/2,2/3,1])
    return result

# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded pose candidates and captain-authorized, physically untested defaults.

``candidate`` retains explicit caller expectations and thresholds for measurements.
``adopted`` records the 2026-10-07 judgment authorization of starting envelopes;
it does not claim measured physical acceptance. The shared engine still refuses
reversed anatomical signs and empty regions.
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


def adopted(kind, side='l'):
    """Captain-authorized starting tables (2026-10-07), physically untested.

    Candidate envelopes are adopted by judgment, not by a measured acceptance.
    The 2mm diagnostic matches canon08 torso/neck sensitivity; it is not a new
    physical clearance acceptance bar. Native sign/ancestry checks still apply.
    """
    expectations = {
        'waist': {'joint': 'head', 'along': 'forward', 'min_cm': 0},
        'boots': {'joint': f'ball_{side}', 'along': 'up', 'min_cm': 0},
        'gauntlets': {'joint': f'middle_03_{side}',
                     'along': '-forward' if side == 'l' else 'forward', 'min_cm': 0},
    }
    if kind not in expectations:
        raise ValueError('adopted kind is waist | boots | gauntlets')
    table = candidate(kind, expectations[kind], .002, side)
    table.update(status='authorized default; physically untested', physical_status='untested',
                 source='canon08 B.3/B.5/H.1; bounded decision_tables candidate; AC65 judgment authorization 2026-10-07',
                 limits='Technical path tests only; natural pose, regional sensitivity and actual piece acceptance remain untested')
    return table

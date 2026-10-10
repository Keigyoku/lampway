# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure contact closure and pair-scoped fade controls; no Blender dependency."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH=Path(__file__).resolve().parents[1]/'src/scripts/mixar/modules/lampway_tools/features/fit_articulated_contacts.py'
spec=importlib.util.spec_from_file_location('fit_articulated_contacts_pure',PATH)
AC=importlib.util.module_from_spec(spec)
spec.loader.exec_module(AC)


def fixture():
    parts={'torso':np.array([0]),'pauldron':np.array([1]),'sleeve':np.array([2,3])}
    planned={'torso':{'mode':'rigid','bones':['spine']},'pauldron':{'mode':'rigid','bones':['arm']},'sleeve':{'mode':'restrict','bones':['spine']}}
    declaration={'schema':'lampway.articulated-contacts/1','source_sha256':'a'*64,'prepared_sha256':'b'*64,'prepared_identity':'c'*64,
                 'authorization':{'decision':'release_derived_contacts','scope':'contact_pairs_only','declaration':'Owner permits this derived contact only.'},
                 'contacts':[{'parts':['pauldron','sleeve'],'source_vertices':[17],'retained_source_vertices':[]}]}
    args={'source_hash':'a'*64,'prepared_hash':'b'*64,'prepared_identity':'c'*64,'parts':parts,'plan_parts':planned,'source_ids':np.array([17,17,17,18]),
          'original_seams':{('pauldron','sleeve'):{17}},'measured_pairs':{('pauldron','sleeve'):{(1,2)}}}
    return declaration,args


def test_fade_release_keeps_other_anchor_and_nearby_vertex():
    d,args=fixture()
    admitted=AC.validate(d,**args)
    assert AC.fade_exclusions(admitted,args['parts'],args['plan_parts'],args['source_ids'])=={2:{'pauldron'}}
    assert AC.released_pairs(admitted)=={('pauldron','sleeve')}
    assert AC.receipt(admitted)['full_fit_owner_review_accepted'] is False
    assert AC.receipt(admitted)['physical_status']=='unreviewed'
    d['contacts'][0]['source_vertices'][0]=19
    assert admitted['contacts'][0]['source_vertices']==[17]


@pytest.mark.parametrize('plant',['extra','missing','ambiguous','overlap','no_source','same_bone','flexible','authority','unknown','not_list'])
def test_every_contact_guard_rejects_its_offender(plant):
    d,args=fixture()
    if plant=='extra':args['measured_pairs'][('pauldron','sleeve')].add((1,3))
    elif plant=='missing':args['measured_pairs'][('pauldron','sleeve')].clear()
    elif plant=='ambiguous':args['source_ids'][3]=17
    elif plant=='overlap':args['parts']['sleeve']=np.array([1,2])
    elif plant=='no_source':args['source_ids']=None
    elif plant=='same_bone':args['plan_parts']['sleeve']={'mode':'rigid','bones':['arm']}
    elif plant=='flexible':args['plan_parts']['pauldron']['mode']='restrict'
    elif plant=='authority':d['authorization']['scope']='full_fit'
    elif plant=='unknown':d['captain_seen']=True
    elif plant=='not_list':d['contacts']={}
    with pytest.raises(ValueError):AC.validate(d,**args)


def test_binding_digest_includes_recipe_and_bones():
    d,args=fixture()
    original=AC.digest(d,args['plan_parts'])
    args['plan_parts']['pauldron']['bones']=['hand']
    assert AC.digest(d,args['plan_parts'])!=original
    d['authorization']['declaration']='different ruling'
    assert AC.digest(d,args['plan_parts'])!=original


def test_absent_declaration_never_releases_contact():
    assert AC.released_pairs(None)==set()
    assert AC.receipt(None) is None
    assert AC.fade_exclusions(None,{}, {},None)=={}


def test_partial_pair_partition_never_waives_remaining_rigid_seam():
    d,args=fixture()
    args['parts']['sleeve']=np.array([2,3])
    args['source_ids']=np.array([17,17,17,18,18])
    args['parts']['pauldron']=np.array([1,4])
    args['original_seams'][('pauldron','sleeve')]={17,18}
    args['measured_pairs'][('pauldron','sleeve')]={(1,2),(4,3)}
    d['contacts'][0]['retained_source_vertices']=[18]
    admitted=AC.validate(d,**args)
    assert AC.released_pairs(admitted)==set()
    assert AC.fade_exclusions(admitted,args['parts'],args['plan_parts'],args['source_ids'])=={2:{'pauldron'}}
    assert AC.receipt(admitted)['retained_contact_pairs']==1
    d['contacts'][0]['retained_source_vertices']=[17]
    with pytest.raises(ValueError,match='disjoint'):AC.validate(d,**args)

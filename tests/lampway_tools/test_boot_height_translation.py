# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon09 height is a length measured from the sole, independent of placement."""
import numpy as np
import pytest

from mixar.modules.lampway_tools.pipeline import fit_place as FP


@pytest.mark.parametrize('translate_piece',[False,True])
def test_boot_height_anchor_is_independent_of_body_world_height(tmp_path,translate_piece):
    vertices=np.array([(.1+.04*np.cos(a),.04*np.sin(a),z)
                       for z in np.linspace(0,.5,11) for a in np.arange(16)*2*np.pi/16])
    triangles=[]
    for i in range(10):
        for j in range(16):
            a=i*16+j;b=i*16+(j+1)%16;c=b+16;d=a+16
            triangles.extend(((a,b,c),(a,c,d)))
    triangles=np.asarray(triangles)
    joints=np.array([[.1,0,.7],[.1,0,.5],[.1,0,.08],[.1,-.06,.02]])
    names=['thigh_l','calf_l','foot_l','ball_l']
    results=[]
    for offset in (0,1):
        body=tmp_path/f'body{offset}.npz'
        np.savez(body,V=vertices+[0,0,offset],T=triangles,J=joints+[0,0,offset],names=names)
        piece=tmp_path/f'piece{offset}.npz'
        np.savez(piece,V=vertices+[0,0,offset if translate_piece else 0],T=triangles)
        placed,_,meta,_=FP.place('boots',body,piece,turn=0,clear_mm=15,scale_anchor='height',sides='l',pair_scale_group='common')
        results.append((placed,meta))
    assert results[0][1]['scale']==pytest.approx(results[1][1]['scale'],abs=1e-12)
    assert results[0][1]['scale']==pytest.approx(1.03,abs=1e-12)
    assert np.allclose(results[1][0]-results[0][0],[0,0,1],atol=1e-12)

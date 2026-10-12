# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit fit measurement inputs survive the server/client boundary."""
import ast
import json
from lampway_server.agent import tools


def test_pair_and_curl_parameters_are_exposed_and_forwarded():
    inputs=[('lampway_fit_place',{'kind':'gauntlets','piece':'p.npz','body':'b.npz','pair_scale_group':'per_side'}),
            ('lampway_fit_pose',{'kind':'gauntlets','curl_side':'r','curl_fractions':[0,1/3,.5,2/3,1]}),
            ('lampway_fit_glove',{'stage':'pose','curl_fractions':[0,.5,1]})]
    for name,args in inputs:
        tree=ast.parse(tools.script_for(name,args))
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and getattr(n.func,'attr','')=='call')
        assert json.loads(ast.literal_eval(call.args[1]))==args
    by={t.name:t for t in tools.TOOLS}
    for name in ('lampway_fit_pose','lampway_fit_glove'):
        item=by[name].parameters['properties']['curl_fractions']['items']
        assert item['type']=='number' and item['minimum']==0 and item['maximum']==1 and item['description']

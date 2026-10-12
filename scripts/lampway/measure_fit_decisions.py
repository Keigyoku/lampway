# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run inside a disposable Blender scene: --python this_file -- --config project/config.json.

Never saves the loaded scene or changes canonical defaults. The config's project
root owns all result files. Feed explicit bounded pose tables and sign expectations;
measurements report failures instead of guessing missing anatomy or decisions.
"""
import argparse
import json
import sys
from pathlib import Path


def main(argv):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    args=parser.parse_args(argv)
    path=Path(args.config).resolve()
    config=json.loads(path.read_text())
    root=Path(config['project_root']).resolve()
    if not path.is_relative_to(root):
        raise ValueError('config must be under its project_root')
    from mixar.modules.lampway_tools.pipeline.decision_measure import measure
    result=measure(config,root)
    print(json.dumps({'schema':result['schema'],'jobs':len(result['jobs']),
                      'failed':[r['id'] for r in result['jobs'] if not r['ok']],
                      'acceptance':{r['id']:r['acceptance'] for r in result['jobs'] if 'acceptance' in r},
                      'out':config.get('out','measurements/decisions.json'),'default_choices_applied':False}))
    return 1 if any(not r['ok'] for r in result['jobs']) else 0


if __name__=='__main__':
    raise SystemExit(main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]))

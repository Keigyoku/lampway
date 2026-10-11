# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generated facelift PNG metadata must retain the actual source-art attribution."""
import copy
import fnmatch
from pathlib import Path
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[2]
ICONS = ROOT / 'src/scripts/mixar/modules/common/lampway_icons'


def _metadata(document, relative):
    matches = []
    for annotation in document['annotations']:
        paths = annotation['path']
        if isinstance(paths, str):
            paths = [paths]
        if any(fnmatch.fnmatchcase(relative, pattern) for pattern in paths):
            matches.append(annotation)
    assert matches, 'missing REUSE annotation: ' + relative
    result = matches[-1]
    assert result.get('SPDX-FileCopyrightText'), 'missing copyright: ' + relative
    assert result.get('SPDX-License-Identifier'), 'missing licence: ' + relative
    return result


def test_every_actual_facelift_png_keeps_source_art_copyright_and_licence():
    document = tomllib.loads((ROOT / 'REUSE.toml').read_text())
    source = (ROOT / 'scripts/dev/brand_art/icons/lampway_icons.svg').read_text()
    icons = sorted(ICONS.glob('*/*.png'))
    assert icons
    for icon in icons:
        meta = _metadata(document, icon.relative_to(ROOT).as_posix())
        assert ('SPDX-' + 'FileCopyrightText: ') + meta['SPDX-FileCopyrightText'] in source
        assert ('SPDX-' + 'License-Identifier: ') + meta['SPDX-License-Identifier'] in source


@pytest.mark.parametrize('field', ['SPDX-FileCopyrightText', 'SPDX-License-Identifier'])
def test_missing_metadata_plant_is_blocked(field):
    document = copy.deepcopy(tomllib.loads((ROOT / 'REUSE.toml').read_text()))
    for annotation in document['annotations']:
        annotation.pop(field, None)
    relative = next(ICONS.glob('*/*.png')).relative_to(ROOT).as_posix()
    with pytest.raises(AssertionError, match='missing'):
        _metadata(document, relative)

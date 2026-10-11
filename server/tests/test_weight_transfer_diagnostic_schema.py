# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The transfer diagnostic accepts a caller cutoff with a calibrated diagnostic default."""
import jsonschema
import pytest
from lampway_server.agent import lampway_tools as LT


def test_matched_fraction_warning_cutoff_is_optional_bounded_and_documents_default():
    schema = LT.BY_NAME['lampway_weight_transfer'].spec().parameters
    cutoff = schema['properties']['matched_fraction_warning_threshold']
    assert cutoff['minimum'] == 0 and cutoff['maximum'] == 1
    assert 'default 0.5' in cutoff['description']
    for value in (None, 0, .5, 1):
        args = {'object': 'piece', 'source': 'body'}
        if value is not None:
            args['matched_fraction_warning_threshold'] = value
        jsonschema.validate(args, schema)
        assert LT.build_script(LT.BY_NAME['lampway_weight_transfer'], args)
    for value in (-.01, 1.01, '0.5'):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({'object': 'piece', 'source': 'body', 'matched_fraction_warning_threshold': value}, schema)

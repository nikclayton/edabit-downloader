# Test data is contained in goldens.json. This is an array of objects, with
# keys:
#
#  - original_code
#  - new_code
#  - original_tests
#  - new_tests
#
# The tests load this file, and then verify that calling fixup_* functions
# on the original_* data returns the same values as in the new_* data.
#
# To generate goldens.json, run "main.py --golden_file goldens.json"

import json
from main import fixup_function
from main import fixup_tests


with open('goldens.json') as golden_file:
    goldens = json.load(golden_file)


def test_everything():
    for golden in goldens:
        assert fixup_function(golden['original_code']) == golden['new_code']
        assert fixup_tests(golden['original_tests']) == golden['new_tests']
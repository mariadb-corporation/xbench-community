import os

import pytest
from xbench import parse_unknown


def test_parse_string():

    test_string1 = "--backend.network.public_ip=127.0.0.1"
    test_string2 = "--backend1.network.public_ip=127.0.0.1"
    expected_dict = {
        "backend": {"network": {"public_ip": "127.0.0.1"}},
        "backend1": {"network": {"public_ip": "127.0.0.1"}},
    }
    print(parse_unknown([test_string1, test_string2]))
    pytest.assume(expected_dict == parse_unknown([test_string1, test_string2]))

def test_parse_string2():
    test_string1 = "--backend.config.cmapi=cmapi"
    test_string2 = "--backend.config.mcs=mcs"
    expected_dict = {
        "backend": {"config": {"mcs": "mcs", "cmapi": "cmapi"}},
    }
    print(test_parse_string)
    print(parse_unknown([test_string1, test_string2]))
    pytest.assume(expected_dict == parse_unknown([test_string1, test_string2]))

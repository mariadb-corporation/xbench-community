import os

import pytest

from common import validate_name_rfc1035


def test_valid():
    res = validate_name_rfc1035('dsv-cluster')
    pytest.assume(res is True)

def test_invalid():
    res = validate_name_rfc1035('dsv_cluster')
    pytest.assume(res is False)

def test_complex():
    res = validate_name_rfc1035('dsv-cluster-backend-1')
    pytest.assume(res is True)

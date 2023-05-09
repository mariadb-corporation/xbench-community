import os

import pytest
from cloud.ephemeral import EphemeralCloud
from lib.xbench_config import XbenchConfig


@pytest.fixture
def ec():
    XbenchConfig().initialize()
    return EphemeralCloud(cluster_name="etest", public_ip="128.128.128.128")


def test_launch_instance(ec):
    params = {
        "name": "driver_0",
        "role": "driver",
        "klass": "driver.BaseDriver",
        "klass_config_label": "sysbench",
    }
    nodes = ec.launch_instances([params])
    pytest.assume(len(nodes) == 1)

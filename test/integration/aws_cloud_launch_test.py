import pytest

from cloud.aws import AwsCloud
from xbench import Xbench

instance_params_assuming_ssd = {
    "count": 1,
    "zone": "us-west-2a",
    "instance_type": "c5d.xlarge",
    "os_type": "CentOS8",
    "name": "ec2_test",
    "role": "driver",
    "network": {"cloud_type": "public_cloud"},
    "klass": "Sysbench",
    "key_file": "ENV['HOME']/.xbench/pem/MariaDBPerformance.pem",
    "managed": True,
    "klass_config_label": "bla",
    "use_placement_group": False,
    "storage": {"type": "ephemeral", "device": "/dev/nvme1n1"},
    "env": "env_1",
    "provisioned": True,
}


@pytest.fixture
def node():
    cluster_name = "i_test_cluster"
    xb = Xbench(cluster_name)
    cloud_config = xb.load_cloud("aws")

    region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)

    cloud = AwsCloud(
        cluster_name=cluster_name,
        **region_config,
    )
    node = cloud.launch_instance(**(instance_params_assuming_ssd | region_config))
    yield node
    cloud.terminate_instance(node)


@pytest.mark.order(1)
def test_launch_ssd_based_instance(node):
    pytest.assume(node.vm.storage.id is not None)


@pytest.mark.order(2)
def test_os(node):
    pytest.assume("CentOS" in node.os_name)


@pytest.mark.order(3)
def test_os_version(node):
    pytest.assume("8" in node.os_version)

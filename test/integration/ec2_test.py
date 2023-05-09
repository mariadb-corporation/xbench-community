import pytest

from cloud.aws import AwsCli, AwsEc2
from xbench import Xbench

instance_params = {
    "count": 1,
    "zone": "us-west-2a",
    "instance_type": "t2.micro",
    "os_type": "CentOS7",
    "name": "ec2_test",
    "role": "driver",
    "network": {"cloud_type": "public_cloud"},
    "klass": "Sysbench",
    "key_file": "ENV['HOME']/.xbench/pem/MariaDBPerformance.pem",
    "managed": True,
    "klass_config_label": "bla",
    "env": "env_1",
    "provisioned": True,
}


@pytest.fixture
def ec2():
    xb = Xbench("cl1")
    cloud_config = xb.load_cloud("aws")

    region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)

    cli = AwsCli(
        cluster_name="cl1",
        **region_config,
    )
    ec2 = AwsEc2(cli=cli, **instance_params)
    ec2.create()
    yield ec2
    ec2.destroy()


@pytest.mark.order(1)
def test_provisioning(ec2):
    assert ec2.instance_id.startswith("i-") is True


@pytest.mark.order(2)
def test_describe(ec2):
    instance_info = ec2.describe()
    assert instance_info.get("public_ip") is not None

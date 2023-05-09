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
    "use_placement_group": True,
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
    yield ec2


@pytest.mark.order(1)
def test_group_name_not_epmty(ec2):
    assert ec2.vm.placement_group == "Xpand"

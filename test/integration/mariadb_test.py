from os.path import expanduser

import pytest
from backend.mariadb import MariaDBEnterprise
from cloud.aws import AwsCli, AwsEc2
from compute.node import Node
from metrics.server import MetricsServer
from xbench import Xbench

instance_params = {
    "count": 1,
    "zone": "us-west-2a",
    "instance_type": "c5.4xlarge",
    "os_type": "Rocky8",
    "name": "mariadb",
    "role": "backend",
    "network": {"cloud_type": "public_cloud"},
    "klass": "Sysbench",
    "key_file": f"{expanduser('~')}/.xbench/pem/MariaDBPerformance.pem",
    "managed": True,
    "klass_config_label": "latest",
}


@pytest.fixture
def node():
    xb = Xbench("cl1")
    cloud_config = xb.load_cloud("aws")

    region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)
    MetricsServer().initialize(**region_config.get("metric_server", None))

    cli = AwsCli(
        cluster_name="cl1",
        **region_config,
    )
    ec2 = AwsEc2(cli=cli, **instance_params)
    vm = ec2.create()
    node = Node(vm)
    yield node
    ec2.destroy()


@pytest.mark.order(1)
def test_provisioning(node, capsys):
    node.configure()
    m = MariaDBEnterprise(node)
    pytest.assume(m.mariadb_config.data_dir == "/data/mariadb")
    print(m.mariadb_config)
    m.configure()
    bt = m.install()
    pytest.assume(bt.user == "xbench")
    captured = capsys.readouterr()
    pytest.assume("10.6" in captured.out)

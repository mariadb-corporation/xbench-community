import os
import time

import pytest

from cloud.aws.aws_cli import AwsCli
from cloud.aws.aws_ec2 import AwsEc2
from metrics.server import MetricsServer
from xbench import Xbench

instance_params = {
    "count": 1,
    "zone": "us-west-2a",
    "instance_type": "t2.micro",
    "os_type": "CentOS7",
    "name": "pytest_ssh_server",
    "role": "driver",
    "network": {"cloud_type": "public_cloud"},
    "klass": "Sysbench",
    "key_file": f"{os.path.expanduser('~')}/.xbench/pem/MariaDBPerformance.pem",
    "managed": True,
    "klass_config_label": "bla",
    "env": "env_1",
    "provisioned": True,
}


@pytest.fixture(scope="session")
def aws_ssh_server():
    xb = Xbench("cl1")
    cloud_config = xb.load_cloud("aws")

    region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)
    MetricsServer().initialize(**region_config.get("metric_server", None))

    cli = AwsCli(
        cluster_name="cl1",
        **region_config,
    )
    ec2 = AwsEc2(cli=cli, **instance_params)
    ec2.create()
    # have to wait for sshd to start before we are ready
    time.sleep(60)
    yield ec2
    ec2.destroy()

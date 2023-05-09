import logging
import os

import yaml

from cloud.aws import AwsCli, AwsEc2
from compute import Node
from xbench import Xbench
from metrics.server import MetricsServer


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)
CLUSTER = "grant_xb_prom_reg"
xb = Xbench(CLUSTER)
cloud_config = xb.load_cloud("aws")

region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)

cli = AwsCli(
    cluster_name=CLUSTER,
    **region_config,
)

instance_params = {
    "env": "env_0",
    "provisioned": False,
    "count": 1,
    "zone": "us-west-2a",
    "instance_type": "t2.micro",
    "os_type": "CentOS7",
    "name": "ec2_test",
    "role": "driver",
    "network": {"cloud_type": "public_cloud"},
    "klass": "Sysbench",
    "klass_config_label": "stable",
    "key_file": f"{os.getenv('HOME')}/.xbench/pem/MariaDBPerformance.pem",
    "managed": True,
}
ms = MetricsServer()
ms.initialize(**region_config.get("metric_server", None))
ec2 = AwsEc2(cli=cli, **instance_params)
vm = ec2.create()
node = Node(vm)
node.configure(**xb.xbench_config_instance.xbench_config)

ec2.destroy()
ms.deregister_cluster(CLUSTER)

import dataclasses
import logging

from cloud.aws import AwsCli, AwsEc2
from xbench import Xbench

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

xb = Xbench("cl1")
cloud_config = xb.load_cloud("aws")

region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)

cli = AwsCli(
    cluster_name="cl1",
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
    "key_file": "ENV['HOME']/.xbench/pem/MariaDBPerformance.pem",
    "managed": True,
    "klass_config_label": "bla",
}

ec2_1 = AwsEc2(cli=cli, **instance_params)
vm = ec2_1.create()
print((dataclasses.asdict(vm)))

ec2_2 = AwsEc2.from_vm(cli, vm)

ec2_2.stop()
ec2_2.start()
ec2_2.reboot()
ec2_2.destroy()

import dataclasses
import logging

from cloud.aws import AwsCli, AwsEbs, AwsEc2
from cloud.virtual_storage import VirtualStorage
from xbench import Xbench
from dacite import from_dict

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
    "klass_config_label": "bla",
    "count": 1,
    "zone": "us-west-2a",
    "instance_type": "t2.micro",
    "os_type": "CentOS7",
    "name": "driver",
    "role": "driver",
    "network": {"cloud_type": "public_cloud"},
    "klass": "Sysbench",
    "key_file": "ENV['HOME']/.xbench/pem/MariaDBPerformance.pem",
    "managed": True,
}
ec2 = AwsEc2(cli=cli, **instance_params)
vm = ec2.create()

print((dataclasses.asdict(vm)))

storage_params = {
    "iops": 111,
    "type": "io2",
    "size": 120,
    "zone": "us-west-2a",
    "device": "/dev/sdf",
}
storage = from_dict(
    data_class=VirtualStorage,
    data=storage_params,
)
ebs = AwsEbs(cli, storage)

virtual_storage = ebs.create()
print(ebs.describe())
ebs.attach_storage(vm)
vm.storage = virtual_storage
print(vm)

# Now let's destroy everything

ec2.destroy()
ebs.destroy()

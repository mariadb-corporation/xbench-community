#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

from cloud import VirtualMachine
from cloud.aws import AwsEc2
from cloud.virtual_storage import VirtualStorage
from dacite import from_dict

d = {
    "name": "cl1-vm",
    "id": "i-017750414b84ad273",
    "klass": "Xpand",
    "private_ip": None,
    "public_ip": None,
    "instance_type": "t2.micro",
    "zone": "us-west-2a",
    "role": "",
    "os_type": "CentOS7",
    "managed": True,
    "virtual_storage": {
        "id": "vol-098aefd599e47785b",
        "name": "cl1-volume",
        "size": 500,
        "iops": 1000,
        "type": "io2",
        "device": "/dev/sdf",
        "zone": "us-west-2a",
    },
}

d = {
    "cluster_name": "restore_test",
    "env": "env_0",
    "provisioned": False,
    "klass_config_label": "bla",
    "cloud": "aws",
    "region": "us-west-2-PerformanceEngineering",
    "use_placement_group": True,
    "managed": True,
    "os_type": "CentOS7",
    "klass": "Xpand",
    "count": 3,
    "zone": "us-west-2a",
    "instance_type": "t2.micro",
    "public_ip": "public",
    "storage": {"type": "io2", "size": 111, "iops": 999, "zone": "us-west-2a"},
    "role": "backend",
    "name": "backend_1",
}
s = {"type": "io2", "size": 111, "iops": 999, "zone": "us-west-2a"}
vs = from_dict(
    data_class=VirtualStorage,
    data=s,
)
print(vs)
vm = from_dict(
    data_class=VirtualMachine,
    data=d,
)
print(vm)
print(vm.storage)

exit(0)

print("############ EC2 test ############")
from cloud.aws import AwsCli, AwsEbs
from xbench import Xbench

xb = Xbench("cl1")
cloud_config = xb.load_cloud("aws")

region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)

cli = AwsCli(
    cluster_name="cl1",
    **region_config,
)
ec2 = AwsEc2(cli, **d)

print(ec2.as_dict())
ec2.destroy()

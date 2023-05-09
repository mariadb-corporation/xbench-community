#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


# https://stackoverflow.com/questions/54987361/python-asyncio-handling-exceptions-in-gather-documentation-unclear

import logging
import os

from cloud.aws import AwsCli, AwsEc2
from compute import Node
from compute.exceptions import (
    NodeException,
    PsshClientException,
    SshClientTimeoutException,
)
from compute.pssh_client import PsshClient
from xbench import Xbench

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="INFO",
)
CLUSTER = "dsv"
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

ec2_1 = AwsEc2(cli=cli, **instance_params)
ec2_2 = AwsEc2(cli=cli, **instance_params)
vm_1 = ec2_1.create()
vm_2 = ec2_2.create()

n1 = Node(vm_1)
n2 = Node(vm_2)
nodes = [n1, n2]
ips = []
for n in nodes:
    ips.append(n.vm.network.get_public_iface())

pssh_config = {
    "hostnames": ips,
    "username": n1.vm.ssh_user,
    "key_file": n1.vm.key_file,
}
pssh = PsshClient(**pssh_config)

cmd = "sleep 10"
print(f"my command is {cmd}")
try:
    output = pssh.run(cmd=cmd, timeout=2)
    print(output)
except (NodeException, SshClientTimeoutException) as e:
    print(e)
finally:
    ec2_1.destroy()
    ec2_2.destroy()

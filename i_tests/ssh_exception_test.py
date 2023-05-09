#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
import os

from cloud.aws import AwsCli, AwsEc2
from compute import Node
from compute.exceptions import NodeException
from xbench import Xbench

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
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
    "klass_config_label": "bla",
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

ec2 = AwsEc2(cli=cli, **instance_params)
vm = ec2.create()
# vm.network.public_ip = "33.33.3.3"
node = Node(vm)

try:
    cmd = "really bad command"
    print(f"my command is {cmd}")
    output = node.run(cmd=cmd, timeout=600, ignore_errors=False)

    # cmd = "sleep 10"
    # print(f"my command is {cmd}")

    # output = node.run(cmd=cmd, timeout=2)
    # print(output)
except NodeException as e:
    print(e)
finally:
    ec2.destroy()

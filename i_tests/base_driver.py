#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
from os.path import expanduser

from cloud.aws import AwsCli, AwsEc2
from compute.node import Node
from driver.base_driver import BaseDriver
from xbench import Xbench

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

instance_params = {
    "env": "env_0",
    "provisioned": False,
    "count": 1,
    "zone": "us-west-2a",
    "instance_type": "c5.2xlarge",
    "os_type": "CentOS7",
    "name": "mariadb",
    "role": "backend",
    "network": {"cloud_type": "public_cloud"},
    "klass": "Sysbench",
    "key_file": f"{expanduser('~')}/.xbench/pem/MariaDBPerformance.pem",
    "managed": True,
    "klass_config_label": "sysbench",
}


try:
    xb = Xbench("cl1")
    cloud_config = xb.load_cloud("aws")

    region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)

    cli = AwsCli(
        cluster_name="cl1",
        **region_config,
    )
    ec2 = AwsEc2(cli=cli, **instance_params)
    vm = ec2.create()
    node = Node(vm)

    b = BaseDriver(node)
    b.configure()
except Exception as e:
    print(e)
finally:
    # ec2.destroy()
    print("By!")

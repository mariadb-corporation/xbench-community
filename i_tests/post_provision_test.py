#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
import os
import sys

from backend import Xpand, XpandException
from cloud import VirtualMachine
from compute import Node
from dacite import from_dict
from metrics.server import MetricsServer
from xbench import Provisioning
from benchmark import Sysbench

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

try:
    arg = sys.argv[1]
except IndexError:
    raise SystemExit(f"Usage: {sys.argv[0]} <name of cluster>")

p = Provisioning(
    cluster_name=arg,
    topo="test_only",
    impl="performance",
    dry_run=False,
    extra_impl_params=None,
)
cluster = p.load_cluster()
region_config = p.cloud_config.get(cluster.region)
MetricsServer().initialize(**region_config.get("metric_server", None))

nodes = []
drivers = []
for k, n in cluster.members.items():
    if n.asdict()["role"] == "backend":
        vm = from_dict(data_class=VirtualMachine, data=n.asdict())
        nodes.append(Node(vm))
    if n.asdict()["role"] == "driver":
        vm = from_dict(data_class=VirtualMachine, data=n.asdict())
        drivers.append(Node(vm))

t = """
[
    {
        "labels": {
            "cloud": "aws",
            "cluster_name": "omm",
            "zone": "us-west-2a",
            "machine_type": "c5.2xlarge",
            "role": "driver",
            "name": "driver_1"
        },
        "targets": [
            "54.184.65.79:9100"
        ]
    }
]
"""

local_file = os.path.join("/tmp/", "omm.json")
with open(local_file, "w+") as f:
    f.write(t)
    f.flush()
    # we have to use `mv` after `scp` because we are scp'ing a file to
    # a docker volume that will be owned by root
    print(f"Local file: {local_file}, remote file /tmp/omm.json")
    nodes[0].ms.ssh_client.scp_files(local_file, f"tmp/omm.json")
    nodes[0].ms.ssh_client.run(cmd=f"mv tmp/omm.json /tmp/omm.json", sudo=True)

exit()

xp = Xpand(nodes, backend_config="stable")
xp.clean()
xp.configure()
xp.install()

sb = Sysbench()
sb.prepare()
sb.run()

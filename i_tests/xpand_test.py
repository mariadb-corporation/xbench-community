#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
import os
import sys

from backend import AbstractBackend, Xpand, XpandException
from cloud import VirtualMachine
from compute import Node
from dacite import from_dict
from metrics import MetricsServer
from xbench import Provisioning

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="INFO",
)

# Hot to get ips
# Create a new cluster
#  ./bin/provision.py --topo test_only --cluster cl2 --impl test_only --step configure --log-level=INFO --log-dir /tmp
# ./bin/provision.py --topo test_only --cluster cl2 --impl test_only --step make --log-level=INFO --log-dir /tmp
#  check ip addresses
#  cat $HOME/.xbench/clusters/cl2.yaml
# Clean up
# ./bin/deprovision.py  --cluster cl2  --log-level=INFO --log-dir /tmp
try:
    arg = sys.argv[1]
except IndexError:
    raise SystemExit(f"Usage: {sys.argv[0]} <name of cluster>")

p = Provisioning(
    cluster_name=arg,
    topo="test_only",
    impl="test_only",
    dry_run=False,
    extra_impl_params=None,
)
cluster = p.load_cluster()
home = os.environ["HOME"]
ms = MetricsServer().initialize(
    hostname="34.213.90.125",
    username="ubuntu",
    key_file=f"{home}/.xbench/pem/MariaDBPerformance.pem",
    remote_target_path="/etc/prometheus/targets",
)
nodes = []
for k, n in cluster.members.items():
    if n.asdict()["role"] == "backend":
        vm = from_dict(data_class=VirtualMachine, data=n.asdict())
        nodes.append(Node(vm))

xp = Xpand(nodes, backend_config="stable")
print(isinstance(xp, AbstractBackend))
exit(1)


try:
    xp.clean()
    xp.configure()
    xp.install()

# xp.connect()
# xp.set_globals()
except XpandException as e:
    print(e)

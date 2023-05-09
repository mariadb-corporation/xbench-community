#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
from typing import Dict

from anytree.search import find
from backend import Xpand
from common.common import get_class_from_klass
from compute import Cluster
from proxy import AbstractProxy
from xbench import Xbench

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)
#  ./bin/provision.py -c dsv_cluster2 --topo default_xpand --impl default_xpand --step configure --log-dir /tmp

CLUSTER = "dsv_cluster"
xb = Xbench(CLUSTER)
cl: Cluster = xb.load_cluster()

print(cl.level_order_group_cluster_members())
print(cl.get_all_driver_nodes())
# Goal is to get something like:
# 'backend': {'klass': <class 'backend.xpand.xpand.Xpand'>,
# 'proxy1': {'klass': <class 'proxy.maxscale.maxscale.Maxscale'>, 'nodes': <

# node_instances: Dict = dict()

# for group in cl.level_order_group_cluster_members():
#     for g in group:
#         print(g.name)  # This print driver_0, driver_1
#         # I can get node per name from cluster.members.

#         for m in g.name.split(","):
#             node = cl.members.get(m, None)
#             node_klass = get_class_from_klass(node.vm.klass)  # driver.Sysbench
#             # Basically it means that top level component has to connect to it as cluster
#             if node_klass.clustered:
#                 label = node.vm.role  # backend1_1 ->backend
#                 if node_instances.get(label) is None:
#                     node_instances[label] = {
#                         "klass": node_klass,
#                         "nodes": [node],
#                         "name": g.name,
#                     }
#                 else:
#                     node_instances[label]["nodes"].append(node)

#             else:  # TODO create groups based on name (remove counter)
#                 # label = cl.group_name(m)  # driver1_0 ->driver1
#                 # if node_instances.get(label) is None:
#                 #     node_instances[label] = {
#                 #         "klass": node_klass,
#                 #         "nodes": [node],
#                 #         "name": g.name,
#                 #     }
#                 # else:
#                 #     node_instances[label]["nodes"].append(node)
#                 node_instances[m] = {"klass": node_klass, "nodes": node, "name": g.name}

node_instances = cl.group_nodes_by_name()
for k, v in node_instances.items():
    print(v.get("klass"))


# Here I am running install(). Once it done it return name, bt

name = "backend1_0,backend1_1"
my_node = cl.find_node_by_name(name)
print(f"Find result {my_node}")
print("Printing all parents")

for k, v in node_instances.items():
    if v.get("name") == my_node.parent.name:
        print(issubclass(v.get("klass"), AbstractProxy))  # We found proxy


exit(1)

# So I know the klass and total number of nodes to call the klass instance
# I need to pass anytree.node.name along with

# See how I can find
my_any_t = find(
    cl.cluster_tree, lambda node: node.name == g.name
)  # This is Anytree object
print("Parent is")
print(my_any_t.parent.name)


# print(cl.render_cluster_tree())
# print(cl.get_all_driver_nodes())
# all_backends = cl.get_backend_nodes()
# print(all_backends)
print("here2")
print(cl.group_by_nodes_by_role())
print("here3")
exit(1)
backend: Xpand = get_class_from_klass(all_backends[0].vm.klass)
print(cl.get_member_nodes_klasses())
xpand = backend(all_backends)
xpand.db_connect()
xpand.self_test()

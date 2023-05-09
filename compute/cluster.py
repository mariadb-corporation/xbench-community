# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


import logging
import os
import random
import string
from dataclasses import asdict
from enum import Enum
from typing import Any, Dict, List, Tuple, Union

import yaml
from anytree import LevelOrderGroupIter, LevelOrderIter
from anytree import Node as AnyNode
from anytree import RenderTree
from anytree.exporter import DictExporter
from anytree.importer import DictImporter
from anytree.search import findall
from dacite import Config, from_dict

from cloud.virtual_storage import VirtualStorage
from common.common import get_class_from_klass
from lib import XbenchConfig

from .backend_target import BackendTarget
from .exceptions import ClusterException
from .node import Node


class Environment:
    def __init__(self, name: str, cloud: str, cloud_klass: str, region: str):
        self.name: str = name
        self.cloud: str = cloud
        self.cloud_klass: str = cloud_klass
        self.region: str = region

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cloud": self.cloud,
            "cloud_klass": self.cloud_klass,
            "region": self.region,
        }


class ClusterState(str, Enum):
    ready = "ready"  # Once we have software installed
    down = "down"  # If cluster was shutdown
    failed = "failed"
    allocated = "allocated"  # Once we got machine allocated
    not_ready = "not_ready"
    # We don't have deleted state as we do simply delete cluster file

    def __str__(self):
        return self.value


class Cluster:
    """Represents cluster"""

    def __init__(
        self,
        cluster_name: str = "cluster",
        topo: str = "xpand",  # Topo name, for information purpose only
    ):
        # Class properties
        self.cluster_name = cluster_name
        self.state: ClusterState = ClusterState.not_ready
        self.topo = topo  # Topology name
        self.envs: list[Environment] = []  # List of environments
        self.members: Dict = {}  # Dict: name: Node class
        self.cluster_tree = AnyNode("cluster")  # Implementation tree
        self.topo_map: Dict = {}  # Dict {driver1: [driver1_0, driver1_1]
        self.bt: BackendTarget = BackendTarget("", "", "", "", 0)
        self.incarnation = self.generate_incarnation()
        self.shared_storage: List[VirtualStorage] = []
        #
        self.logger = logging.getLogger(__name__)

    def add_member(self, instance_name, node: Node):
        self.members[instance_name] = node

    def as_dict(self) -> Dict:
        """Return Dict representation of the Cluster"""

        dict_repr = {
            "cluster_name": self.cluster_name,
            "state": str(self.state),
            "topo_name": self.topo,
            "topo_map": self.topo_map,
            "envs": [x.to_dict() for x in self.envs],
            "cluster_tree": DictExporter().export(self.cluster_tree),
            "bt": self.bt.as_dict(),
            "shared_storage": self.shared_storage,
        }
        all_members = {}
        for (
            name,
            member,
        ) in self.members.items():  # I need dict representation of each member
            all_members[name] = member.asdict()  # convert Node to dict
        #
        dict_repr["members"] = all_members
        return dict_repr

    def save_config(self, yaml_config_file: str):

        with open(yaml_config_file, "w") as f:
            yaml.dump(self.as_dict(), f, sort_keys=False)

    def load_from_config(self, yaml_config_file: str):
        try:
            with open(yaml_config_file, "rt") as f:
                yaml_config_dict = yaml.load(f, Loader=yaml.Loader)
        except FileNotFoundError as e:
            raise ClusterException(e)

        # Initiate the real object
        self.cluster_name = yaml_config_dict.get("cluster_name")
        self.state = yaml_config_dict.get("state")
        self.topo = yaml_config_dict.get("topo_name")
        self.topo_map = yaml_config_dict.get("topo_map")
        self.envs = [Environment(**e) for e in yaml_config_dict.get("envs")]
        self.incarnation = yaml_config_dict.get("incarnation")
        members = yaml_config_dict.get("members")
        self.bt = from_dict(
            data_class=BackendTarget,
            data=yaml_config_dict.get("bt"),
            config=Config(cast=[Enum]),
        )
        self.shared_storage = yaml_config_dict.get("shared_storage")
        # Initiate all nodes
        for n, m in members.items():
            node = Node.from_dict(m)
            self.add_member(n, node)

        self.cluster_tree = DictImporter().import_(yaml_config_dict.get("cluster_tree"))

        self.logger.info(f"Cluster {self.cluster_name} has been successfully initiated")

    # def list_members_by_name (self, name: str):
    #

    @staticmethod
    def generate_incarnation(string_len=3):
        """
        Generate random id
        """

        letters = string.ascii_lowercase
        return "".join(random.choice(letters) for i in range(string_len))

    def __str__(self):
        return f"{self.as_dict()}"

    def _add_children(self, children, parent):

        if isinstance(children, dict):
            for k, v in children.items():
                p = AnyNode(k, parent=parent)
                self._add_children(v, p)

        if isinstance(children, list):  # list is the latest level in yaml
            for c in children:
                AnyNode(c, parent=parent)

    def build_tree_from_dict(self, d: Union[Dict, List]):
        """Build anyTree from dict (or topo dict)

        Args:
            d (Dict): this is a normal map
            d (List): a very special case, when you need a driver or backend only
        """
        # Let's build cluster tree
        if isinstance(d, Dict):
            for k, v in d.items():
                branch = AnyNode(name=k, parent=self.cluster_tree)
                self._add_children(v, branch)
        elif isinstance(d, List):
            self._add_children(d, self.cluster_tree)

    def render_cluster_tree(self):
        for pre, fill, any_node in RenderTree(self.cluster_tree):
            print("%s%s" % (pre, any_node.name))

    def level_order_cluster_members(self) -> List:
        return [
            node
            for node in LevelOrderIter(
                self.cluster_tree, filter_=lambda n: n.name != "cluster"
            )
        ]

    @staticmethod
    def unique_nodes(nodes: list) -> list:
        """Anytree allow adding nodes with the same names just to a different parents.
        This function return unique nodes based on names.

        Args:
            nodes (list): list of anytree objects

        Returns:
            list: unique list based on names
        """
        used = set()
        unique = [x for x in nodes if x.name not in used and (used.add(x.name) or True)]
        return unique

    def level_order_group_cluster_members(self) -> List:
        """Return array with level ordered cluster members(names) - all drivers, all proxies, all databases

        Returns:
            List: cluster members names
        """
        members = [
            self.unique_nodes([node for node in children])
            for children in LevelOrderGroupIter(self.cluster_tree)
        ]
        return members[1:]  # I don't need a  root entry
        # remove

    def get_all_driver_nodes(self):
        cluster_members = self.level_order_group_cluster_members()
        # [[AnyNode(name='driver_0,driver_1')], [AnyNode(name='backend_0,backend_1,backend_2')]]
        drivers = cluster_members[0]

        all_driver_nodes = []
        for driver in drivers:
            for d in driver.name.split(","):
                node = self.members.get(d)
                all_driver_nodes.append(node)
        return all_driver_nodes

    def get_backend_nodes(self):
        cluster_members = self.level_order_group_cluster_members()
        backends = cluster_members[-1][0]
        all_backend_nodes = []
        for backend in backends.name.split(","):
            node = self.members.get(backend)
            all_backend_nodes.append(node)
        return all_backend_nodes

    @staticmethod
    def remove_numbers(s: str) -> str:
        """Remove all numbers from string.

        Args:
            s (str): driver1_0, backend2_0

        Returns:
            str: driver, backend
        """
        return "".join(i for i in s if (not i.isdigit() and i != "_"))

    @staticmethod
    def group_name(s: str) -> str:
        """Generate group name, part of the name before _

        Args:
            s (str): driver1_0, backend2_0

        Returns:
            str: driver1, backend2
        """
        return s.split("_")[0]

    # TODO THIS SHOULD BE REMOVED
    def group_by_nodes_by_role(self) -> Dict:
        # I need to build something like that
        # {'backend': { 'klass': '<class ref>', 'nodes':  [1,2,3]}} # clustered=True
        # {'driver_0': { 'klass': '<class ref>', 'nodes':  1 }} # clustered=False
        node_instances: Dict = dict()
        for (
            i,
            node,
        ) in self.members.items():  # i is driver_0 or backend_1, node is Node
            # if node.vm.managed:
            node_klass = get_class_from_klass(node.vm.klass)  # driver.Sysbench
            if node_klass.clustered:
                label = self.remove_numbers(i)
                if node_instances.get(label) is None:
                    node_instances[label] = {
                        "klass": node_klass,
                        "nodes": [node],
                    }
                else:
                    node_instances[label]["nodes"].append(node)

            else:
                node_instances[i] = {"klass": node_klass, "nodes": node}
        return node_instances

    def get_member_nodes_klasses(self, node_instances: Dict) -> List[Tuple]:
        """Return klass and Nodes to initialize this class

        Args:
            node_instances (Dict): _description_

        Returns:
            List[Tuple]: _description_
        """
        node_instances = self.group_by_nodes_by_role()
        klass_instances: List[Tuple] = []
        for k, v in node_instances.items():

            klass_instances.append(
                (v.get("klass"), (v.get("nodes")))
            )  #  , **self.extra_impl_params)

        return klass_instances

    def find_node_by_name(self, node_name: str) -> Any:
        """Find a cluster tree node by name

        Args:
            node_name (str): name of the tree node

        Returns:
            Any: AnyTree object
        """
        # I have to use findall as it could be nodes with the same name under different parents
        any_tree_tuple = findall(
            self.cluster_tree, lambda node: node.name == node_name
        )  # This is Anytree object
        if len(any_tree_tuple) == 0:
            raise ClusterException(f"There is no node with a name {node_name}")
        return any_tree_tuple[0]

    def group_nodes_by_name(self) -> Dict[str, Dict]:
        """Group nodes based on their

        I need to build something like that
        {'backend': { 'klass': '<class ref>', 'nodes':  [1,2,3]}, 'name': 'backend'} # clustered=True
        {'driver_0': { 'klass': '<class ref>', 'nodes':  1 }, 'driver_0,driver_1'} # clustered=False
        """

        node_instances: Dict = dict()

        for group in self.level_order_group_cluster_members():
            for g in group:
                # print(g.name)  # This print driver_0, driver_1
                # I can get node per name from cluster.members.

                for m in g.name.split(","):
                    node = self.members.get(m, None)
                    node_klass = get_class_from_klass(node.vm.klass)  # driver.Sysbench
                    # remove all groups put all nodes together
                    if node_klass.clustered:
                        label = node.vm.role  # backend1_1 ->backend
                        if node_instances.get(label) is None:
                            node_instances[label] = {
                                "klass": node_klass,
                                "nodes": [node],
                                "name": g.name,
                                "env": node.vm.env,
                            }
                        else:
                            node_instances[label]["nodes"].append(node)

                    else:  # TODO create groups based on name (remove counter)
                        # label = cl.group_name(m)  # driver1_0 ->driver1
                        # if node_instances.get(label) is None:
                        #     node_instances[label] = {
                        #         "klass": node_klass,
                        #         "nodes": [node],
                        #         "name": g.name,
                        #     }
                        # else:
                        #     node_instances[label]["nodes"].append(node)
                        # self.group_name(m)
                        node_instances[m] = {
                            "klass": node_klass,
                            "nodes": node,
                            "name": g.name,
                            "env": node.vm.env,
                        }

        return node_instances

# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

# This class should be compatible with ReleaseTracker

import json
from datetime import date
from fnmatch import translate
from typing import Any, Dict, Iterable, List, Optional, Union

from compute import Node, NodeException, VirtualMachine
from dateutil.parser import parse
from mysql_client import MySqlClient, MySqlClientException

from .exceptions import XpandException


class cXpand(MySqlClient):
    """Generic class for Xpand"""

    def __init__(self, nodes_list: Iterable[Dict], db_config: Dict):
        """[summary]

        Args:
            nodes_list (Iterable[Dict]): List of nodes (see Node class)
            db_properties (Dict): Mysql properties
        """
        self.nodes = []
        # Convert list of dict into Nodes class
        for i in nodes_list:
            n = Node(**i)
            self.nodes.append(n)
        pass

        MySqlClient.__init__(self, **db_config)

    def db_connect(self):
        """Connect to Xpand"""
        try:
            self.connect()
            self.print_db_version()
        except MySqlClientException as e:
            raise XpandException(e)

    def startup(self, **kwargs):
        pass

    def sudo(self):
        return "sudo" if self.nodes[0].ssh_user != "root" else ""

    def start(self):
        cmd = f"""
        {self.sudo} systemctl start clustrix.service
        {self.sudo} systemctl start hugetlb
        """
        self.info("running start comand in all nodes")
        self.run_remote_command_on_all_nodes(cmd)

    def stop(self):
        cmd = f"""
        {self.sudo} systemctl stop clustrix.service
        {self.sudo} systemctl stop hugetlb
        """
        self.info("running stop comand in all nodes")
        self.run_remote_command_on_all_nodes(cmd)

    def restart(self):
        self.stop()
        self.start()

    def get_version(self):
        query = "select @@version as version"
        row = self.select_one_row(query)
        return row.get("version")

    def get_branch_build(self):
        version = self.get_version()  # It should be 5.0.45-Xpand-mainline1-17376
        try:
            cluster_branch = version.split("-")[2]
            cluster_build = int(version.split("-")[3])
            return (cluster_branch, cluster_build)
        except IndexError:  # For prod release it just 5.0.45-Xpand-5.3.17
            raise XpandException("Unable to obtain branch and version")

    def check_logs(self):
        """Grep logs for any errors
        Return: an Exception if FATAL error found
        """
        # Do we always have a log in this directory? I think there is clx command to do grep over multiple logs.
        # I need always return true to prevent get an exception that command failed. grep return 1 if not found
        cmd = "grep FATAL  /data/clustrix/log/clustrix.log || true"
        ret_dict = self.run_remote_command_on_all_nodes(cmd)
        for k, v in ret_dict.items():
            output = "".join(v[0].split())
            if output:
                raise XpandException(f"Fatal errors found on {k} node")

    def check_quorum(self):
        """Check if we have a quorum"""
        query = "SELECT nid, status FROM system.membership where status != 'quorum'"
        try:
            row = self.select_one_row(query)
            if len(row) == 0:
                self.logger.info("Cluster is in quorum")
            else:
                raise XpandException(
                    "There is no quorum in the cluster"
                )  # At least one row found
        except MySqlClientException as e:
            raise XpandException("Unable to check quorum")

    def get_expiration_date(self) -> date:
        """Return license expiration date"""
        query = "select @@license as license"
        row = self.select_one_row(query)
        license_info_as_str = row.get("license")
        license_info_as_dict = json.loads(license_info_as_str)
        return parse(license_info_as_dict.get("expiration"), ignoretz=True)

    def run_remote_command_on_node(
        self, node, cmd: Union[list, str], timeout: Optional[int] = None
    ) -> tuple:
        self.logger.debug(f"Running on node  {node.id}")
        stdout, stderr, exit_code = node.run_remote_command(cmd, timeout)
        self.logger.debug(f"Node: {node.id} output: {stdout}")
        return (stdout, stderr, exit_code)

    def run_remote_command_on_all_nodes(
        self, cmd: Union[list, str], timeout: Optional[int] = None
    ) -> Dict:

        ret_dict = {}
        try:
            self.logger.info(f"Running {cmd} on all nodes")
            for n in self.nodes:
                stdout, stderr, exit_code = self.run_remote_command_on_node(
                    n, cmd, timeout
                )
                ret_dict[n.id] = (stdout, stderr, exit_code)
            self.logger.info(f"Command successfully executed on all nodes")
            return ret_dict
        except NodeException as e:
            raise XpandException(e)

    def get_head_node(self):
        return self.nodes[0]

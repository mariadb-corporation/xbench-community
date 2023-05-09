# -*- coding: utf-8 -*-
# Copyright (C) 2021 detravi

import logging

from compute import BackendTarget, Node
from lib import XbenchConfig
from proxy import AbstractProxy
from xbench.common import get_default_cluster

from .aws_cli import get_aws_cli
from .exceptions import ColumnstoreException
from .config_templates import storagemanager_cnf

def get_storagemanager_config(bucket):
    cli = get_aws_cli()
    return storagemanager_cnf.format(bucket = bucket,
                                     aws_access_key_id = cli.aws_access_key_id,
                                     aws_secret_access_key = cli.aws_secret_access_key,
                                     aws_region=cli.aws_region)


def write_config_file_command(bucket, config_name):
    return (f"cat << EOF > {config_name} \n"
            f"{get_storagemanager_config(bucket)} \n"
            "EOF")


class ColumnstoreS3Backend(AbstractProxy):
    """Class to setup S3 details for underlying backends"""
    clustered = False

    def __init__(self, node: Node, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.node = node
        self.cluster_name = XbenchConfig().cluster_name()

    def post_install(self, bt: BackendTarget):
        self.logger.info(f"Propagating storagemanager.cnf for S3bucket '{self.cluster_name}'")
        private_nodes_ips = bt.host.split(",")
        config_command = write_config_file_command(self.cluster_name, "storagemanager.cnf")
        config_path = "/etc/columnstore/storagemanager.cnf"

        if not private_nodes_ips:
            raise ColumnstoreException("No ips for backends to put storagemanager config")

        cluster = get_default_cluster()

        head_ssh_user = None
        for node_num, ip in enumerate(private_nodes_ips):
            ssh_user = None

            for node in cluster.members.values():
                if node.vm.role == "backend" and node.vm.network.get_private_iface() == ip:
                    ssh_user = node.vm.ssh_user
                    if node_num == 0:
                        head_ssh_user = ssh_user
                    break

            if not ssh_user:
                raise ColumnstoreException(f"No ssh_user for backend with private ip {ip}")

            self.node.run(f"ssh {ssh_user}@{ip} bash -c '{config_command}'")
            self.node.run(f"ssh {ssh_user}@{ip} sudo mv storagemanager.cnf {config_path}")

        self.node.run(f"ssh {head_ssh_user}@{private_nodes_ips[0]} sudo /usr/bin/mcs cluster restart")

        for ip in private_nodes_ips:
            test_connection = self.node.run(f"ssh rocky@{ip} testS3Connection")
            self.logger.info(f"S3 test: {test_connection} ")
            self.logger.info(f"storagemanager.cnf deployed to {ip} '")

        return bt

    def configure(self):
        pass

    def install(self):
        pass

    def db_connect(self):
        pass

    def self_test(self):
        pass

    def clean(self):
        pass

    def start(self, **kwargs):
        pass

    def stop(self, **kwargs):
        pass



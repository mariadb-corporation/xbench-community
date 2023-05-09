# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

import logging
import os
from typing import Dict, List, Union

from common.retry_decorator import backoff, retry
from compute.exceptions import (
    MultiNodeException,
    NodeException,
    PsshClientException,
    SshClientException,
    SshClientTimeoutException,
)
from lib.xbench_config import XbenchConfig

from .node import Node
from .pssh_client import PsshClient

DEFAULT_EXECUTION_TIMEOUT = 300


class MultiNode:
    """This class provides service for running on multiple nodes"""

    def __init__(self, nodes: List[Node], **kwargs):
        self.nodes = nodes
        self.logger = logging.getLogger(__name__)

        self.xbench_config = XbenchConfig().xbench_config
        pem_dir = self.xbench_config.get("pem_dir")

        pssh_config = {
            "hostnames": self._all_public_ips(),
            "username": self.head_node.vm.ssh_user,
            "key_file": os.path.join(
                pem_dir, "xbench.pem"
            ),  # This is required for multi-region #  self.head_node.vm.key_file,
        }
        self.pssh = PsshClient(**pssh_config)

    @property
    def num_nodes(self):
        return len(self.nodes)

    @property
    def head_node(self):
        return self.nodes[0]

    def _all_public_ips(self) -> List:
        ips = []
        for n in self.nodes:
            ips.append(n.vm.network.get_public_iface())
        return ips

    def _all_client_ips(self) -> List:
        ips = []
        for n in self.nodes:
            ips.append(n.vm.network.get_client_iface())
        return ips

    def _all_private_ips(self) -> List:
        ips = []
        for n in self.nodes:
            ips.append(n.vm.network.get_private_iface())
        return ips

    def run_on_one_node(
        self, cmd: Union[list, str], timeout: int = DEFAULT_EXECUTION_TIMEOUT, sudo=True
    ) -> str:
        """This method does not need to retry as node.run already handle this"""
        try:
            return self.head_node.run(cmd, sudo=sudo, timeout=timeout)
        except NodeException as e:
            raise MultiNodeException(e)

    @retry(
        (SshClientException, SshClientTimeoutException, PsshClientException),
        MultiNodeException,
        delays=backoff(delay=10, attempts=3),
        max_delay=600,
    )
    def run_on_all_nodes(
        self,
        cmd: Union[list, str],
        timeout: int = DEFAULT_EXECUTION_TIMEOUT,
        sudo: bool = True,
        host_args: list = None,
        ignore_errors: bool = False,
    ) -> List[Dict[str, str]]:

        return self.pssh.run(
            cmd=cmd,
            timeout=timeout,
            sudo=sudo,
            host_args=host_args,
            ignore_errors=ignore_errors,
        )

    def scp_to_all_nodes(
        self,
        local_file,
        remote_file,
        timeout: int = DEFAULT_EXECUTION_TIMEOUT,
        recursive=False,
    ):
        """Copy local file to all remote nodes

        Args:
            local_file (_type_): _description_
            remote_file (_type_): _description_
            timeout (Optional[int], optional): _description_. Defaults to None.
        """
        try:
            self.logger.info(f"transferring {local_file} to all nodes to {remote_file}")
            self.pssh.send_files(local_file, remote_file, recursive)
        except PsshClientException as e:
            raise MultiNodeException(f"Error while connecting to hosts {e}")

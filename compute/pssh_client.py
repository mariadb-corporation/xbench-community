# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

"""This client uses asyncIO to run ssh commands on the remote server.

"""
import asyncio
import logging
from typing import Dict, List, Optional, Union

import asyncssh

from common import clean_cmd

from .exceptions import PsshClientException, SshClientException
from .ssh_client import SshClient

asyncssh.set_log_level(logging.CRITICAL)
asyncssh.set_sftp_log_level(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


DEFAULT_EXECUTION_TIMEOUT = 300  # no single command should take more than 10 mins
DEFAULT_READ_TIMEOUT = 60  # Use read_timeout in order to read partial output.


class PsshClient:
    """Parallel SSH Client based on asyncssh"""

    def __init__(
        self,
        hostnames: list,
        port: int = 22,
        username: str = "root",
        password: Optional[str] = None,
        key_file: Optional[str] = None,
    ):
        self.logger = logging.getLogger(__name__)
        self.hostnames = hostnames
        self.pssh_clients = []
        for hostname in self.hostnames:
            self.pssh_clients.append(
                SshClient(hostname, port, username, password, key_file)
            )

    @staticmethod
    def get_or_create_event_loop():
        try:
            return asyncio.get_event_loop()
        except RuntimeError as ex:
            if "There is no current event loop in thread" in str(ex):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return asyncio.get_event_loop()

    async def _run_clients(
        self,
        cmd: str,
        timeout: int = DEFAULT_EXECUTION_TIMEOUT,
        sudo=False,
        host_args: list = None,
        ignore_errors: bool = False,
    ) -> List:

        if host_args:
            tasks = (
                ssh_client._run_client(
                    cmd=cmd % host_args[i],
                    timeout=timeout,
                    sudo=sudo,
                    ignore_errors=ignore_errors,
                )
                for i, ssh_client in enumerate(self.pssh_clients)
            )
        else:
            tasks = (
                ssh_client._run_client(
                    cmd=cmd, timeout=timeout, sudo=sudo, ignore_errors=ignore_errors
                )
                for ssh_client in self.pssh_clients
            )

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        except SshClientException as e:
            raise PsshClientException(e)

    async def _send_file_sftp(self, local, remote):
        tasks = [runner._sftp_send(local, remote) for runner in self.pssh_clients]
        results = await asyncio.gather(tasks, return_exceptions=True)
        return results

    async def _send_file_scp(self, local, remote, recursive=False):
        tasks = (
            runner._scp_send(local, remote, recursive) for runner in self.pssh_clients
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def _receive_file_scp(self, remote, local, recursive):
        tasks = (
            runner._scp_receive(remote, local, recursive)
            for runner in self.pssh_clients
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    def send_file_sftp(self, local, remote):
        """compare performance with send_file_scp"""
        try:
            self.get_or_create_event_loop().run_until_complete(
                self._send_file_sftp(local, remote)
            )
        except (OSError, asyncssh.Error) as e:
            raise PsshClientException(f"SFTP operation failed: {e}")

    def send_files(self, local, remote, recursive=False):
        """compare performace with send_file_sftp"""
        try:
            self.get_or_create_event_loop().run_until_complete(
                self._send_file_scp(local, remote, recursive)
            )
        except (OSError, asyncssh.Error) as e:
            raise PsshClientException(f"S operation failed: {e}")

    def receive_files(self, remote, local, recursive):
        """compare performace with send_file_sftp"""
        try:
            self.get_or_create_event_loop().run_until_complete(
                self._receive_file_scp(remote, local, recursive)
            )
        except (OSError, asyncssh.Error) as e:
            raise PsshClientException(f"S operation failed: {e}")

    def run(
        self,
        cmd: Union[list, str],
        timeout: int = DEFAULT_EXECUTION_TIMEOUT,
        sudo: bool = False,
        host_args: list = None,
        ignore_errors: bool = False,
    ) -> List[Dict[str, str]]:
        """_summary_

        Args:
            cmd (Union[list, str]): _description_
            timeout (int, optional): _description_. Defaults to DEFAULT_EXECUTION_TIMEOUT.
            sudo (bool, optional): _description_. Defaults to False.

        Returns:
            List[Dict[str,str]]: List of stdout per host {'hostname'=, 'stdout'=}
        """
        self.logger.debug(f"Running {cmd} on {self.hostnames}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(
            self._run_clients(
                cmd=clean_cmd(cmd),
                timeout=timeout,
                sudo=sudo,
                host_args=host_args,
                ignore_errors=ignore_errors,
            )
        )
        for r in results:
            if isinstance(r, asyncio.TimeoutError):
                raise PsshClientException(
                    f"Command {cmd} timed out on one of the hosts"
                )
            if isinstance(r, Exception):
                raise PsshClientException(r)

        return results

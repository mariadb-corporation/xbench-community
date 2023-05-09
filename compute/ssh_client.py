# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

import asyncio
import logging
import socket
from typing import Dict, Optional, Union

import asyncssh

from common import backoff_with_jitter, clean_cmd, retry

from .exceptions import SshClientException, SshClientTimeoutException

asyncssh.set_log_level(logging.INFO)
asyncssh.set_sftp_log_level(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.INFO)


DEFAULT_EXECUTION_TIMEOUT = 300  # no single command should take more than 10 mins
LOGIN_TIMEOUT = 60  # The maximum time in seconds allowed for authentication to complete
CONNECT_TIMEOUT = (
    60  # The maximum time in seconds allowed to complete an outbound SSH connection
)
KEEPALIVE_INTERVAL = 10
KEEPALIVE_COUNT_MAX = 6
SCP_BLOCK_SIZE = 16384


class SshClient:
    """SSH Client based on asyncssh"""

    def __init__(
        self,
        hostname: str,
        port: int = 22,
        username: str = "root",
        password: Optional[str] = None,
        key_file: Optional[str] = None,
    ):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.key_file = key_file

        self.logger = logging.getLogger(__name__)

        self.options = asyncssh.SSHClientConnectionOptions(
            login_timeout=LOGIN_TIMEOUT,
            connect_timeout=CONNECT_TIMEOUT,
            username=self.username,
            known_hosts=None,
            keepalive_interval=KEEPALIVE_INTERVAL,
            keepalive_count_max=KEEPALIVE_COUNT_MAX,
            # request_pty="force",  $ THis breaks scp # Without a PTY, a join call with a timeout will complete with timeout exception raised but the remote process will be left running as per SSH protocol specifications.
            client_keys=[key_file],
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

    async def _run_client(
        self,
        cmd: str,
        timeout: int,
        sudo: bool,
        ignore_errors: bool = False,
        user: str = None,
    ) -> Dict[str, str]:
        async with asyncssh.connect(
            self.hostname,
            options=self.options,
        ) as conn:

            result_stdout = []

            is_multiline_cmd = True if len(cmd.splitlines()) > 1 else False

            if not ignore_errors and is_multiline_cmd:
                cmd = f"set -e\n{cmd}"

            if user:  # user always require sudo
                c = f"sudo -i -u {user} -S $SHELL -c '{cmd}'"
            elif sudo:
                c = f"sudo -S $SHELL -c '{cmd}'"
            else:
                c = cmd

            self.logger.debug(f"Running {c} with timeout {timeout}")
            result = await conn.run(c, timeout=timeout, check=False)
            # TODO I can be a bit smart about which command to repeat
            # based on return code. 127 command not found doesn't make to repeat
            if result.exit_status > 0:
                err_msg = f"Command {c} failed with {result.exit_status}: {result.stderr}: {result.stdout}"
                if ignore_errors:
                    self.logger.warning(f"{err_msg}")
                else:
                    raise SshClientException(err_msg)
            if isinstance(result, asyncio.TimeoutError):
                raise SshClientTimeoutException(
                    f"Command {c} timed out after {timeout} "
                )
            else:
                for l in result.stdout.splitlines():
                    result_stdout.append(l)

            return {"hostname": self.hostname, "stdout": "\n".join(result_stdout)}

    @retry(
        (
            asyncssh.Error,
            asyncio.exceptions.TimeoutError,
            ConnectionError,
            ConnectionRefusedError,
            socket.timeout,
        ),
        SshClientException,
        delays=backoff_with_jitter(delay=10, attempts=30, cap=45),
    )
    def run(
        self,
        cmd: Union[list, str],
        timeout: int = DEFAULT_EXECUTION_TIMEOUT,
        sudo: bool = False,
        ignore_errors: bool = False,
        user: str = None,
    ) -> str:
        """This command will retry Network or other ssh related issues"""
        return self._unsafe_run(
            cmd=cmd, timeout=timeout, sudo=sudo, ignore_errors=ignore_errors, user=user
        )

    def _unsafe_run(
        self,
        cmd: Union[list, str],
        timeout: int = DEFAULT_EXECUTION_TIMEOUT,
        sudo: bool = False,
        ignore_errors: bool = False,
        user: str = None,
    ) -> str:

        """Run a single command, which can be multiline
        Args:
            cmd (Union[list, str]): string, multiline string or list
            timeout (Optional[int], optional): timeout for the execution. Defaults to DEFAULT_EXECUTION_TIMEOUT.

            Be carefull with sudo:
            sudo -S $SHELL -c '<comand here>'

        Returns:
            str:  stdout
        Raises:
            SshClientException: generic ssh client exception
        """

        try:
            ret = self.get_or_create_event_loop().run_until_complete(
                self._run_client(
                    clean_cmd(cmd),
                    timeout=timeout,
                    sudo=sudo,
                    ignore_errors=ignore_errors,
                    user=user,
                )
            )
            return ret.get("stdout")
        # Connection is a sub class of OSError so has to be handled before
        except ConnectionError as e:
            raise
        except OSError as e:  # exit code > 0; We don't want to retry in this module
            if ignore_errors:
                self.logger.warning(e)
                return ""
            else:
                raise SshClientException(e)

        except asyncssh.process.TimeoutError as e:  # Command time out
            raise SshClientTimeoutException(f"command {cmd} timed out")

        except asyncio.exceptions.TimeoutError as e:
            raise ConnectionError(e)

        except Exception as e:
            self.logger.error(
                f"Something really bad has happened on {self.hostname} {type(e)} {e}"
            )
            raise

    @retry(
        (OSError, asyncssh.Error, asyncio.exceptions.TimeoutError),
        SshClientException,
        delays=backoff_with_jitter(delay=10, attempts=3, cap=45),
    )
    async def _scp_send(self, local: str, remote: str, recursive=False):
        """Helper function for send_files

        Args:
            local (str): _description_
            remote (str): _description_
            recursive (bool): _description_
        """

        async with asyncssh.connect(
            self.hostname,
            options=self.options,
        ) as conn:
            await asyncssh.scp(
                local,
                (conn, remote),
                recurse=recursive,
                block_size=SCP_BLOCK_SIZE,
            )

    async def _scp_receive(self, remote: str, local: str, recursive=False):
        """Helper function for receive_files

        Args:
            remote (str): _description_
            local (str): _description_
            recursive (bool): _description_
        """

        async with asyncssh.connect(
            self.hostname,
            options=self.options,
        ) as conn:
            await asyncssh.scp(
                (conn, remote),
                local,
                recurse=recursive,
                block_size=SCP_BLOCK_SIZE,
            )

    async def _sftp_send(self, local, remote):
        self.logger.info("beginning upload")
        async with asyncssh.connect(
            self.hostname, username=self.username, options=self.options
        ) as conn:
            async with conn.start_sftp_client() as sftp:
                await sftp.put(local, remotepath=remote)

    @retry(
        (OSError, asyncssh.Error, asyncio.exceptions.TimeoutError),
        SshClientException,
        delays=backoff_with_jitter(delay=10, attempts=30, cap=45),
    )
    def send_files(self, local: str, remote: str, recursive=False):
        """Copy files from local to remote

        Args:
            local (str): local file name
            remote (str): remote file name
            recursive (bool, optional): Recursive copy. Defaults to False.

        Raises:
            SshClientException:
        """
        self.get_or_create_event_loop().run_until_complete(
            self._scp_send(local, remote, recursive)
        )

    @retry(
        (OSError, asyncssh.Error, asyncio.exceptions.TimeoutError),
        SshClientException,
        delays=backoff_with_jitter(delay=10, attempts=30, cap=45),
    )
    def receive_files(self, remote: str, local: str, recursive=False):
        """Copy files from remote to local

        Args:
            remote (str): remote file name
            local (str): local file name
            recursive (bool, optional): Recursive copy. Defaults to False.

        Raises:
            SshClientException:
        """
        self.get_or_create_event_loop().run_until_complete(
            self._scp_send(remote, local)
        )

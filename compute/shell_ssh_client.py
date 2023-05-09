# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

"""This client shells out to "ssh" binary to run commands on the remote server.

"""
import logging
import os
from subprocess import Popen
from typing import Any, List, Optional, Union

from common import backoff_with_jitter, retry

from .exceptions import (
    ProcessExecutionException,
    ShellSSHClientException,
    TimeoutException,
)
from .run_subprocess import RunSubprocess

DEFAULT_EXECUTION_TIMEOUT = 300  # no single command should take more than 10 mins


class ShellSSHClient:
    def __init__(
        self,
        hostname,  # type: str
        port=22,  # type: int
        username="root",  # type: str
        password=None,  # type: Optional[str]
        key=None,  # type: Optional[str]
        key_file=None,  # type: Optional[str]
        connect_timeout=None,  # type: Optional[float]
    ):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.key_file = key_file
        self.connect_timeout = connect_timeout

        self.logger = logging.getLogger(__name__)

        if self.password:
            raise ShellSSHClientException("ShellOutSSHClient only supports key auth")

        proc = RunSubprocess(cmd="which ssh", timeout=15)
        _, _, retcode = proc.run()
        if retcode == 127:  # Not found
            raise ShellSSHClientException("ssh client is not available")
        self.logger.debug("SSH command found")

    def connect(self):
        """
        This client doesn't support persistent connections establish a new
        connection every time "run" method is called.
        """
        return True

    def put(self, path, contents=None, chmod=None, mode="w"):
        if mode == "w":
            redirect = ">"
        elif mode == "a":
            redirect = ">>"
        else:
            raise ValueError("Invalid mode: " + mode)

        cmd = ['echo "%s" %s %s' % (contents, redirect, path)]
        self._run_remote_shell_command(cmd)
        return path

    def putfo(self, path, fo=None, chmod=None):
        content = fo.read()
        return self.put(path=path, contents=content, chmod=chmod)

    def delete(self, path):
        cmd = ["rm", "-rf", path]
        self._run_remote_shell_command(cmd)
        return True

    def close(self):
        return True

    def _get_base_ssh_command(self) -> List[str]:

        cmd = "ssh -q -oStrictHostKeyChecking=no"

        if self.key_file:
            cmd = f"{cmd} -i {self.key_file}"

        if self.connect_timeout:
            cmd = f"{cmd} -oConnectTimeout={self.timeout}"

        cmd = f"{cmd} {self.username}@{self.hostname}"

        return cmd

    def run_one_command(
        self, cmd: str, timeout: Optional[int] = DEFAULT_EXECUTION_TIMEOUT
    ):
        """This will run a single command, one line only

        Args:
            cmd (str): [description]
            timeout (Optional[int], optional): [description]. Defaults to DEFAULT_EXECUTION_TIMEOUT.

        Returns:
            [type]: [description]
        """

        return self._run_remote_shell_command(" ".join(cmd.split()), timeout)

    def run(
        self, cmd: Union[list, str], timeout: Optional[int] = DEFAULT_EXECUTION_TIMEOUT
    ):
        """This function will try to determine if cmd is multiline or not.
        If it is a multiline then it will send an array which will be executed inside EOF block

        Args:
            cmd (str): [description]
            timeout (Optional[int], optional): [description]. Defaults to DEFAULT_EXECUTION_TIMEOUT.

        Returns:
            [type]: [description]
        """
        # Let's check if this is a multiline command
        if isinstance(cmd, str):
            cmd_list = [y for y in (x.strip() for x in cmd.splitlines()) if y]
            cmd = cmd_list[0] if len(cmd_list) == 1 else cmd_list
        return self._run_remote_shell_command(cmd, timeout)

    @retry(
        ProcessExecutionException,
        ShellSSHClientException,
        delays=backoff_with_jitter(delay=3, attempts=10, cap=30),
    )
    def _run_remote_shell_command(
        self, cmd: Union[list, str], timeout: Optional[int] = None, wait: bool = True
    ) -> Union[tuple, Popen]:
        """[summary]

        Args:
            cmd (Union[list, str]): single line cmd command as string or list of command
            timeout (Optional[int], optional): timeout. Defaults to None.

        Raises:
            ShellSSHClientException: [description]

        Returns:
            tuple: stdout,stdin,error code or Popen
        """
        if isinstance(cmd, str):
            cmd = f"{self._get_base_ssh_command()} '{cmd}'"
        else:  # For the list I want to use << EOF trick
            if ".exe" in os.environ["SHELL"]:
                # Below changes for Git Bash on Windows
                self.logger.debug("Using string concat")
                cmd = "\n".join(cmd)
                cmd = f"{self._get_base_ssh_command()} '{cmd}'"
            else:
                self.logger.debug("Using EOF block")
                cmd = (
                    f"{self._get_base_ssh_command()} << EOF\n"
                    + "\n".join(cmd)
                    + "\nEOF\n"
                )

        try:
            proc = RunSubprocess(cmd=cmd, timeout=timeout)
            result = proc.run_as_shell(wait)  # Result could be tuple or proc
            return result
        except ProcessExecutionException as e:
            if "reboot" in cmd and "closed by remote host" in str(e):
                return ("", "", 0)  # Yeah, you losing connection after reboot command
            elif "error code 255" in str(e):  # Access problem I should retry
                raise
            else:
                raise ShellSSHClientException(f"ssh command failed with {e}")

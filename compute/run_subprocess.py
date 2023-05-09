# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

"""Run suprocess

"""
import logging
import os
import shlex
import signal
import subprocess
from typing import Any, List, Optional

from .exceptions import (CommandException, ShellSSHClientException,
                         TimeoutException)

DEFAULT_TIMEOUT = 5 * 60

# ToDo: Thread execution: https://stackoverflow.com/questions/984941/python-subprocess-popen-from-a-thread
# ToDO: exception to raise if command fails. None - no exception
# ToDo: printing process output: https://stackoverflow.com/questions/984941/python-subprocess-popen-from-a-thread


class RunSubprocess:
    def __init__(self, cmd: str, timeout: Optional[int] = DEFAULT_TIMEOUT):
        self.logger = logging.getLogger(__name__)
        self.cmd = cmd
        self.timeout = timeout

    def run(self):
        """[Split arguments into arrray and then executed it]

        Returns:
            tuple: stdout,stdin,error code
        """

        cmd = shlex.split(self.cmd)
        return self._run(cmd, shell=False)

    def run_as_shell(self, wait: bool = True):
        """This version for complex commands like using | (shell only)

        Returns:
            tuple: stdout,stdin,error code
        """
        if wait:
            return self._run(self.cmd, shell=True)
        else:
            return self._run_no_wait(self.cmd, shell=True)

    def _run(self, cmd, shell: bool = False):
        """
        Returns:
            tuple: stdout,stdin,error code
        """
        self.logger.debug(f"Executing command \n {self.cmd} \n with timeout {self.timeout}")
        try:
            env = dict(os.environ)
            env["LC_ALL"] = "C"
            if ".exe" in env["SHELL"]:
                shell = False
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=shell,
                env=env,
            )

            stdout, stderr = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            pid = proc.pid
            del proc
            os.kill(pid, signal.SIGKILL)
            raise TimeoutException(
                f"Command {cmd} timed out after {self.timeout} seconds"
            )
        except FileNotFoundError as e:
            raise CommandException(f"Command {cmd} failed with: {e}")

        stdout_str = stdout.decode("utf-8")
        stderr_str = stderr.decode("utf-8")

        if proc.returncode != 0:
            raise CommandException(
                f"Command {cmd} failed with {stderr_str}, error code {proc.returncode}"
            )

        return (stdout_str, stderr_str, proc.returncode)

    def _run_no_wait(self, cmd, shell: bool = False):
        """Run process and return Popen object whiteout  waiting:

        Args:
            cmd ([type]): [description]
            shell (bool, optional): [description]. Defaults to False.
        """
        self.logger.debug(f"Executing command {self.cmd}")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=shell,
                universal_newlines=True,
            )
            return proc

        except FileNotFoundError as e:
            raise CommandException(f"Command {cmd} failed with: {e}")

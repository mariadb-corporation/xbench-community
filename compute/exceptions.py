# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


class SshClientException(Exception):
    """native  command failed"""

class PsshClientException(Exception):
    """native  command failed"""


class SshClientTimeoutException(SshClientException):
    """native  command failed"""


class ShellSSHClientException(Exception):
    """SSH command failed"""


class ProcessExecutionException(Exception):
    """An HTTP error occurred."""

    def __init__(self, err_message=None):
        self.err_message = err_message

    def __str__(self):
        return "{err_message}".format(err_message=self.err_message)


class CommandException(ProcessExecutionException):
    """A process failed"""


class TimeoutException(ProcessExecutionException):
    """A process timeout"""


class NodeException(Exception):
    """Something wrong while working with a node"""

class MultiNodeException(NodeException):
    """Some went wrong while running on multiple hosts"""

class ClusterException(Exception):
    """Something wrong while initialize a new node"""

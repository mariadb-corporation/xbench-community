# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov
from abc import ABCMeta, abstractmethod

from .os_types import *

# Location of the EPEL RPM.
EPEL_URL = "https://dl.fedoraproject.org/pub/epel/epel-release-latest-{}.noarch.rpm"

# Dict of vm.OS_TYPE to the yum RPM to install.  Must include all OSes that
# can install EPEL.
EPEL_URLS = {
    CENTOS7: EPEL_URL.format(7),
    RHEL7: EPEL_URL.format(7),
    CENTOS8: EPEL_URL.format(8),
    ROCKY8: EPEL_URL.format(8),
    AMAZONLINUX2: EPEL_URL.format(7),
}

PACKAGE_MANAGERS_INSTALL = {
    CENTOS7: "yum install -y",
    RHEL7: "yum install -y",
    CENTOS8: "dnf install -y",
    ROCKY8: "dnf install -y",
    AMAZONLINUX2: "yum install -y",
}

PACKAGE_MANAGERS_GROUP_INSTALL = {
    CENTOS8: "dnf group install -y",
    ROCKY8: "dnf group install -y",
    CENTOS7: "yum group install -y",
    RHEL7: "yum group install -y",
    AMAZONLINUX2: "yum group install -y",
}

PACKAGE_MANAGERS_LOCAL_INSTALL = {
    CENTOS7: "yum localinstall -y",
    RHEL7: "yum localinstall -y",
    CENTOS8: "dnf localinstall -y",
    ROCKY8: "dnf localinstall -y",
    AMAZONLINUX2: "yum localinstall -y",
}

PACKAGE_MANAGERS_REMOVE = {
    CENTOS7: "yum erase -y",
    RHEL7: "yum erase -y",
    CENTOS8: "dnf erase -y",
    ROCKY8: "dnf erase -y",
    AMAZONLINUX2: "yum erase -y",
}

PACKAGE_MANAGERS_GROUP_REMOVE = {
    CENTOS8: "dnf group erase -y",
    ROCKY8: "dnf group erase -y",
    CENTOS7: "yum group erase -y",
    RHEL7: "yum group erase -y",
    AMAZONLINUX2: "yum group erase -y",
}

PACKAGE_MANAGERS_ENABLE_REPO = {
    CENTOS7: "yum --enablerepo",
    RHEL7: "yum --enablerepo",
    CENTOS8: "dnf --enablerepo",
    ROCKY8: "dnf --enablerepo",
    AMAZONLINUX2: "yum --enablerepo",
}

PACKAGE_MANAGERS_DISABLE_REPO = {
    CENTOS7: "yum --disablerepo",
    RHEL7: "yum --disablerepo",
    CENTOS8: "dnf --disablerepo",
    ROCKY8: "dnf --disablerepo",
    AMAZONLINUX2: "yum --disablerepo",
}

PACKAGE_MANAGERS_DISABLE_MODULE = {
    ROCKY8: "dnf -qy module disable",
}

PACKAGE_MANAGERS_FILE_EXTENSION = {
    CENTOS7: "rpm",
    RHEL7: "rpm",
    CENTOS8: "rpm",
    ROCKY8: "rpm",
    AMAZONLINUX2: "rpm",
}

# Additional commands to run after installing the RPM.
EPEL_CMDS = {
    CENTOS7: f"{PACKAGE_MANAGERS_INSTALL[CENTOS7]} {EPEL_URLS[CENTOS7]}",
    RHEL7: f"{PACKAGE_MANAGERS_INSTALL[RHEL7]} {EPEL_URLS[RHEL7]}",
    CENTOS8: f"{PACKAGE_MANAGERS_INSTALL[CENTOS8]} {EPEL_URLS[CENTOS8]}",
    ROCKY8: f"{PACKAGE_MANAGERS_INSTALL[ROCKY8]} {EPEL_URLS[ROCKY8]}",
    AMAZONLINUX2: "amazon-linux-extras install -y epel",
}


class PackageManager(metaclass=ABCMeta):
    def __init__(self, os_type: str):
        """we could make this a factory method that returns an appropriate
        subtype based on the os_type string"""
        if os_type not in ALL_OS_TYPES:
            raise NotImplementedError(f"OS {os_type} is not implemented")
        else:
            self.os_type = os_type

    @abstractmethod
    def install_pkg_cmd(self) -> str:
        """return package install command"""

    @abstractmethod
    def remove_pkg_cmd(self) -> str:
        """return package uninstall command"""


class Yum(PackageManager):
    def install_epel_command(self) -> str:
        return EPEL_CMDS[self.os_type]

    def install_pkg_cmd(self) -> str:
        return PACKAGE_MANAGERS_INSTALL[self.os_type]

    def install_local_pkg_cmd(self) -> str:
        return PACKAGE_MANAGERS_LOCAL_INSTALL[self.os_type]

    def remove_pkg_cmd(self) -> str:
        return PACKAGE_MANAGERS_REMOVE[self.os_type]

    def enable_repo_cmd(self) -> str:
        return PACKAGE_MANAGERS_ENABLE_REPO[self.os_type]

    def disable_repo_cmd(self) -> str:
        return PACKAGE_MANAGERS_DISABLE_REPO[self.os_type]

    def disable_module_cmd(self) -> str:
        return PACKAGE_MANAGERS_DISABLE_MODULE[self.os_type]

    def package_file_extension(self) -> str:
        return PACKAGE_MANAGERS_FILE_EXTENSION[self.os_type]

    def install_group(self) -> str:
        return PACKAGE_MANAGERS_GROUP_INSTALL[self.os_type]

    def remove_group(self) -> str:
        return PACKAGE_MANAGERS_GROUP_REMOVE[self.os_type]

    def version_number(self)->str:
        """Return Redhat version number

        """
        if '7' in self.os_type:
            return '7'
        else:
            return '8'

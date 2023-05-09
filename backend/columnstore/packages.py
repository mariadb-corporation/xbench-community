# -*- coding: utf-8 -*-
# Copyright (C) 2021 detravi

import re

from cloud.arch_types import AARCH64, X86_64
from compute.os_types import ROCKY8

from .exceptions import ColumnstoreException

os_mapping = {ROCKY8: "rockylinux8"}

arch_mapping = {AARCH64: "arm64", X86_64: "amd64"}


def split_build_tokens(build):
    return re.split("[-:_]", build)


def get_build_subpath(build):

    if build == "latest":
        return build

    build_tokens = split_build_tokens(build)

    if (
        len(build_tokens != 2)
        or not build_tokens[1].isnumeric()
        or build_tokens[0] not in ["pull_request", "cron", "custom"]
    ):
        raise ColumnstoreException("Wrong build set for drone: {build}")

    return f"{build_tokens[0]}/{build_tokens[1]}"


def get_engine_drone_build_bucket(
    branch: str, arch: str, os: str, server_version: str, build: str
):
    os_branch = os_mapping[os]
    arch_branch = arch_mapping[arch]
    return f"s3://cspkg/{branch}/{get_build_subpath(build)}/{server_version}/{arch_branch}/{os_branch}"


def get_cmapi_build_bucket(branch, arch, build):
    arch_branch = arch_mapping[arch]
    return f"s3://cspkg/cmapi/develop/{get_build_subpath(build)}/{arch_branch}/"

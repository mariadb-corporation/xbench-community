#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
import os
import shlex
from tempfile import TemporaryDirectory

import pytest
from compute import PsshClient, PsshClientException

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

p = PsshClient(
    hostname="54.202.142.45",
    username="ec2-user",
    key_file="~/.xbench/pem/MariaDBPerformance.pem",
)
p.run(cmd="uptime", timeout=300, sudo=True)

with TemporaryDirectory() as tmp:
    local_file = os.path.join(tmp, "./1.txt")
    fname = os.path.basename(local_file)

    with open(local_file, "w") as f:
        f.write("test message")
        f.flush()
    p.scp_files(local_file, f"tmp/{fname}", recursive=False)
    p.run(cmd=f"mv tmp/{fname} /tmp/{fname}", sudo=True)

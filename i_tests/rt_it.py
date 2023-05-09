#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

# Read properties file and initialize Xpand class with all nodes

import logging
from collections import defaultdict
from typing import Dict

from release_tracker import ReleaseTracker

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)


cluster = "yang4-xpand-dev"
config_file = "release_tracker_dev.yaml"

rt = ReleaseTracker(
    cluster=cluster,
    rt_config_file=config_file,
    dry_run=False,
)

rt.connect()

rt.check_logs()
rt.run_stop_reboot()

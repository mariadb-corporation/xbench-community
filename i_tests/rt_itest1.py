#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

# Read properties file and initialize Xpand class with all nodes

import logging

from release_tracker import ReleaseTracker

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)


cluster = "yang4-xpand-dev"
config = "release_tracker_dev.yaml"

# Initialize Release tracker
rt = ReleaseTracker(
    cluster=cluster,
    rt_config_file=config,
    dry_run=False,
)

rt.connect()
rt.check_logs()
# rt.run_clean_drivers()
# rt.run_reboot_drivers()

# -*- coding: utf-8 -*-
# Copyright (C) 2021 detravi

import logging
import os

from backend.columnstore.exceptions import ColumnstoreException
from cloud.aws.aws_cli import AwsCli
from compute import Cluster, cluster
from compute.exceptions import ClusterException
from lib import XbenchConfig
from lib.xbench_config import XbenchConfigException
from lib.yaml_config import YamlConfig
from lib.yaml_config.yaml_config import YamlConfigException
from xbench.common import get_default_cluster


def get_aws_cli():
    logger = logging.getLogger(__name__)

    cluster = get_default_cluster()
    region = cluster.envs[0].region
    logger.debug(f"Using {region} for AWS credentials")

    cloud_yaml_file = os.path.join(XbenchConfig().get_key("conf_dir"), "cloud.yaml")
    vault_file = XbenchConfig().get_key("vault_file")
    cloud_yaml = YamlConfig(yaml_config_file=cloud_yaml_file, vault_file=vault_file)
    aws = cloud_yaml.get_key("providers", "aws")
    region_config = aws.get(region, None)

    cli = AwsCli(
        cluster_name=XbenchConfig().cluster_name(),
        **region_config,
    )

    return cli

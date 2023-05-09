# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import logging
import os
from typing import Dict

from compute import Cluster
from compute.exceptions import ClusterException
from lib import XbenchConfig, XbenchConfigException
from lib.yaml_config import YamlConfig, YamlConfigException

from common import mkdir

from .exceptions import XbenchException


class Xbench:
    """Main support class to deal with provisioning/deprovisioning"""

    def __init__(self, cluster_name, dry_run=False):
        self.cluster_name = cluster_name
        # self.cluster = None
        self.logger = logging.getLogger(__name__)

        try:
            XbenchConfig(cluster_name=cluster_name).initialize()
            self.xbench_config_instance = XbenchConfig()
            self.xbench_config_dir = self.xbench_config_instance.get_key("conf_dir")
            self.clusters_dir = self.xbench_config_instance.get_key("clusters_dir")
            self.vault_file = self.xbench_config_instance.get_key("vault_file")
            self.dry_run = dry_run

        except (YamlConfigException, XbenchConfigException) as e:
            raise XbenchException(e)

    def cluster_yaml_exists(self):
        """Return true if cluster yaml file already exists"""
        cluster_config_yaml = os.path.join(
            self.clusters_dir, f"{self.cluster_name}.yaml"
        )
        return os.path.exists(cluster_config_yaml)

    def remove_cluster_yaml(self):
        cluster_config_yaml = os.path.join(
            self.clusters_dir, f"{self.cluster_name}.yaml"
        )
        try:
            os.remove(cluster_config_yaml)
        except FileNotFoundError:
            self.logger.debug("Could not find cluster file!")

    def load_cluster(self) -> Cluster:
        try:
            cluster = Cluster(cluster_name=self.cluster_name)
            cluster_config_yaml = os.path.join(
                self.clusters_dir, f"{self.cluster_name}.yaml"
            )
            cluster.load_from_config(cluster_config_yaml)

            return cluster
        except (YamlConfigException, XbenchConfigException, ClusterException) as e:
            raise XbenchException(e)

    def save_cluster(self, cluster: Cluster, archive: str = None):
        mkdir(self.clusters_dir)
        cluster_config_yaml = os.path.join(
            self.clusters_dir, f"{cluster.cluster_name}.yaml"
        )
        cluster.save_config(cluster_config_yaml)
        self.logger.info(
            f"Cluster {cluster.cluster_name} save as {cluster_config_yaml}"
        )
        if archive:
            cluster_config_yaml = os.path.join(archive, f"{cluster.cluster_name}.yaml")
            cluster.save_config(cluster_config_yaml)
            self.logger.info(
                f"Cluster {cluster.cluster_name} {cluster_config_yaml}"
            )

    def load_impl(self, impl) -> Dict:

        try:
            impl_yaml_file = os.path.join(self.xbench_config_dir, "impl.yaml")
            self.impl_yaml = YamlConfig(yaml_config_file=impl_yaml_file, vault_file=self.vault_file)
            return self.impl_yaml.get_key(impl, use_defaults=True)

        except YamlConfigException as e:
            raise XbenchException(e)

    def load_cloud(self, cloud: str) -> Dict:
        """Load cloud from yaml file"""
        try:
            cloud_yaml_file = os.path.join(self.xbench_config_dir, "cloud.yaml")
            cloud_yaml = YamlConfig(
                yaml_config_file=cloud_yaml_file, vault_file=self.vault_file
            )
            return cloud_yaml.get_key("providers", cloud)

        except YamlConfigException as e:
            raise XbenchException(e)

    def load_topo(self, topo: str) -> Dict:
        """Load topology from yaml file

        Raises:
            XbenchException: if something went wrong while reading yaml

        Returns:
            Dict: params of the requested topo
        """
        try:
            # Load topology
            topo_yaml_file = os.path.join(self.xbench_config_dir, "topo.yaml")
            topo_yaml = YamlConfig(
                yaml_config_file=topo_yaml_file
            )  # topo shouldn't have any vault specific info
            return topo_yaml.get_key(topo)
        except YamlConfigException as e:
            raise XbenchException(e)

    @staticmethod
    def _clear_component(t):
        """Component in topo could be string, list or list of list. I need just a string

        Returns:
            str : component name (driver, database, proxy)
        """
        if isinstance(t, str):
            return t
        elif isinstance(t, list):
            if isinstance(t[0], str):
                return t[0]
            else:
                return t[0][0]

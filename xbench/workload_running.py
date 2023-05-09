# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.abstract_backend import AbstractBackend
from benchmark.exceptions import BenchmarkException
from common import get_class_from_klass, save_dict_as_yaml
from common.common import mkdir
from driver.abstract_driver import AbstractDriver
from lib import Grafana, XbenchConfig
from lib.yaml_config import YamlConfig, YamlConfigException
from proxy.abstract_proxy import AbstractProxy

from .exceptions import XbenchException
from .xbench import Xbench


class WorkloadRunning(Xbench):
    """Main class to run workload"""

    def __init__(
        self,
        cluster_name,
        benchmark_name: str,
        workload_name: str,
        artifact_dir: str,
        extra_impl_params: dict = {},
        tag: Optional[
            str
        ] = None,  # Useful when multiple workloads run for the same cluster
    ):
        super(WorkloadRunning, self).__init__(cluster_name)
        self.cluster = self.load_cluster()
        self.benchmark_name = benchmark_name
        self.workload_name = workload_name
        self.artifact_dir = artifact_dir
        self.extra_impl_params = extra_impl_params
        self.tag = tag

        workload_yaml = XbenchConfig().load_yaml("workload.yaml")
        # This hack is required because workload yaml is not standard file
        workload_yaml.defaults = workload_yaml.get_key(
            root=self.benchmark_name, leaf="defaults"
        )  # Load defaults from sysbench section

        # Finally
        workload_yaml.yaml_config_dict = workload_yaml.get_key(
            root=self.benchmark_name, leaf="workloads", use_defaults=True
        )

        self.workload_conf = workload_yaml.get_key(
            root=self.workload_name, use_defaults=True
        ) | self.extra_impl_params.get("workload", {})
        self.cluster.bt.update(self.extra_impl_params.get("bt", {}))
        self.all_backends = self.cluster.get_backend_nodes()
        backend_klass = get_class_from_klass(self.all_backends[0].vm.klass)
        # If not clustered then send only single node
        self.backend = backend_klass(
            self.all_backends if backend_klass.clustered else self.all_backends[0],
            bt=self.extra_impl_params.get("bt", {}),
        )
        self.grafana_servers = []
        for env in self.cluster.envs:
            try:
                grafana_host = self.load_cloud(env.cloud)[env.region]["metric_server"]
                self.grafana_servers.append(
                    Grafana(grafana_host["sa_token"], grafana_host["hostname"])
                )
            except KeyError:
                self.logger.info(
                    f"Environment {env.name} does not have a metric server"
                )

    def load_workload(self, workload_name: str) -> Dict:
        try:
            w_yaml_file = os.path.join(self.xbench_config_dir, "workload.yaml")
            self.w_yaml = YamlConfig(yaml_config_file=w_yaml_file)
            return self.w_yaml.get_key(workload_name, use_defaults=True)

        except YamlConfigException as e:
            raise XbenchException(e)

    # Todo Exception handling
    def self_test(self):
        """Check that backend is working and the all drivers in the cluster can connect to database

        Returns:
            Exception if once of the test failed
        """
        self.logger.info(f"Cluster connect string \n{self.cluster.bt}")
        node_instances = self.cluster.group_nodes_by_name()
        for k, v in node_instances.items():
            klass = v.get("klass")
            instance = klass(v.get("nodes"), bt=self.extra_impl_params.get("bt", {}))
            if issubclass(klass, AbstractDriver):
                instance.self_test(self.cluster.bt)
            elif issubclass(klass, AbstractProxy):
                instance.self_test()
            elif issubclass(klass, AbstractBackend):
                instance.db_connect()
                instance.self_test()

    def prepare(self):
        """Clean database and run prepare command for workload"""
        all_nodes = self.cluster.get_all_driver_nodes()
        driver_klass = all_nodes[0].get_klass()
        driver_klass(all_nodes[0]).clean_database(self.cluster.bt)

        workload_runner_class = get_class_from_klass(self.workload_conf.get("klass"))
        workload_runner_class(all_nodes, **self._get_all_params()).prepare()
        workload_runner_class(all_nodes, **self._get_all_params()).data_check()
        self.backend.db_connect()
        self.backend.print_db_size(self.cluster.bt.database)

    # Every workload has to take care about killing drivers before starting a new run
    def run(self) -> str:
        """
        Run the workload
        Raises:
            XbenchException: _description_

        Returns:
            str: artifact directory
        """
        try:
            all_nodes = self.cluster.get_all_driver_nodes()
            # For each run we need to create unique run directory
            now = datetime.now()
            self.artifact_dir = f'{self.artifact_dir}/{self.cluster.cluster_name}/{now.strftime("%Y_%m_%d_%H_%M")}_{self.benchmark_name}'
            if self.tag:
                self.artifact_dir = f"{self.artifact_dir}_{self.tag}"
            mkdir(self.artifact_dir)
            workload_runner_class = get_class_from_klass(
                self.workload_conf.get("klass")
            )
            time_from = self.save_timestamp(os.path.join(self.artifact_dir, "start"))
            self.save_tag(os.path.join(self.artifact_dir, "tag"))
            # Save workload config to the artifact directory
            save_dict_as_yaml(
                os.path.join(self.artifact_dir, "workload.yaml"), self.workload_conf
            )
            workload_runner_class(all_nodes, **self._get_all_params()).run()
            time_to = self.save_timestamp(os.path.join(self.artifact_dir, "stop"))
            for grafana in self.grafana_servers:
                snapshot_urls = grafana.create_snapshot(
                    self.cluster, time_from, time_to
                )
                self.save_snapshot_urls(
                    snapshot_urls, (os.path.join(self.artifact_dir, "snapshot_url"))
                )
                for url in snapshot_urls:
                    self.logger.info(f"Snapshot URL: {url}")
            return self.artifact_dir
        except (OSError, BenchmarkException) as e:
            raise XbenchException(e)

    def _get_all_params(self):
        return (
            self.workload_conf
            | asdict(self.cluster.bt)
            | {"artifact_dir": self.artifact_dir}
            | {"workload_name": self.workload_name}
            | {"backend": self.backend}
            | self.extra_impl_params
        )

    def _backup_restore_dest(self) -> str:
        # Naming convention = <backup type>/<benchmark>_<workload>_<scale_string>_<tag>
        tag = f"_{self.tag}" if self.tag else ""
        all_nodes = self.cluster.get_all_driver_nodes()
        workload_runner_class = get_class_from_klass(self.workload_conf.get("klass"))
        scale_string = workload_runner_class(
            all_nodes, **self._get_all_params()
        ).get_scale_string()
        dest = f"{self.cluster.bt.get_backup_type()}/{self.benchmark_name}_{self.workload_conf.get('bench')}_{scale_string}{tag}"
        return dest

    def backup(self, target: str):
        """Backup database to specified destination"""

        for env in self.cluster.envs:
            # Get the backend env
            if env.name == self.all_backends[0].vm.env:
                cloud_args = self.load_cloud(env.cloud)[env.region]

        backup_dest = self._backup_restore_dest()
        self.logger.info(
            f"Performing backup of {self.cluster.bt.database} database to the"
            f" {backup_dest}"
        )
        self.backend.backup(self.cluster.bt.database, backup_dest, cloud_args, target)
        self.logger.info("Backup complete")

    def restore(self, target: str):
        """Restore from specified source"""

        for env in self.cluster.envs:
            # Get the backend env
            if env.name == self.all_backends[0].vm.env:
                cloud_args = self.load_cloud(env.cloud)[env.region]

        restore_dest = self._backup_restore_dest()
        self.logger.info(
            f"Restoring {self.cluster.bt.database} database from {restore_dest}"
        )
        self.backend.restore(self.cluster.bt.database, restore_dest, cloud_args, target)
        self.logger.info("Restore complete")
        workload_runner_class = get_class_from_klass(self.workload_conf.get("klass"))
        workload_runner = workload_runner_class(
            self.cluster.get_all_driver_nodes(), **self._get_all_params()
        )
        workload_runner.data_check()
        workload_runner.setup()  # Need to setup benchbase on driver

    @staticmethod
    def save_timestamp(file_name: str):
        """Save time stamp in a file

        Args:
            file_name (str): full file path
        """
        with open(file_name, "w") as f:
            now = datetime.now(timezone.utc)
            now = now.replace(tzinfo=timezone.utc)
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            f.write(now_str)
        return now_str

    @staticmethod
    def save_snapshot_urls(urls: List[str], file_name: str):
        """Save grafana snapshot URL to a file

        Args:
            file_name (str): full file path
        """
        for url in urls:
            with open(file_name, "a") as f:
                f.write(f"{url}\n")

    def save_tag(self, file_name: str = "tag"):
        tag = self.tag or f"{self.benchmark_name}_{self.workload_name}"
        with open(file_name, "w") as f:
            f.write(tag)

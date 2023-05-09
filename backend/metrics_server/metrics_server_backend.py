import logging
import os
import tempfile
from typing import Any, Optional

import yaml
from dacite import from_dict

from backend.base_backend import mdadm_command, mkdir_command
from compute.backend_target import BackendTarget
from compute.node import Node
from lib import XbenchConfig

from .exceptions import MetricsServerException
from .metrics_server_config import MetricsServerConfig

METRICS_CONFIG_FILE = "metricsserver.yaml"


# TODO: parameterize some config values that are currently strings
class MetricsServerBackend:

    clustered = False

    def __init__(self, node: Node, **kwargs):
        """
        This class deploys the metrics server and is not to be confused with
        `metrics.server.MetricsServer` which is the singleton class that
        exposes the metric target registration behaviors

        The metrics server doesn't fit into the topology concept for xbench,
        so as a work around we will have to make it a fake driver host
        that will need to be manually deprovisioned afterwards

        We cannot circularly register ourself as a metrics target so we will need
        to turn off the metrics exporters on the underlying node class

        Only going to allow this class to be run if a server doesn't already exist.
        We will check the MetricsServer() singleton and see if we have a non-null value
        """
        self.node: Node = node
        self.logger = logging.getLogger(__name__)
        if self._metrics_server_already_exists():
            self.logger.warning(f"metrics server already deployed")

        self.config: MetricsServerConfig = from_dict(
            data_class=MetricsServerConfig,
            data=XbenchConfig().get_key_from_yaml(
                yaml_file_name=METRICS_CONFIG_FILE,
                key_name=self.node.vm.klass_config_label,
                use_defaults=True,
            ),
        )
        self.xbench_config = XbenchConfig().config

        if "rocky" not in self.node.os_name.lower():
            raise MetricsServerException(
                "metrics server is only available on Rocky Linux, not"
                f" {self.node.os_name}"
            )
        self._prometheus_container: str = "docker.io/prom/prometheus"
        self._grafana_container: str = "docker.io/grafana/grafana"
        self._prometheus_container_name: str = "prom"
        self._grafana_container_name: str = "graf"
        self._container_network_name: str = "metrics"
        self._dashboard_directory: str = "/etc/grafana/dashboards"
        self._metrics_scrape_targets_directory: str = "/etc/prometheus/targets"
        self._nobody_uid: str = "65534"
        self._nobody_gid: str = self._nobody_uid
        self._grafana_uid: str = "472"
        self._grafana_gid: str = "0"
        self._grafana_port: str = "3000"
        self._prometheus_port: str = "9090"
        # maybe allow setting prometheus port here?
        self._grafana_conf: dict[str, Any] = {
            "apiVersion": 1,
            "datasources": [
                {
                    "name": "Prometheus",
                    "url": f"http://{self._prometheus_container_name}:9090",
                    "access": "proxy",
                    "type": "prometheus",
                }
            ],
        }
        self._dashboard_conf: dict[str, Any] = {
            "apiVersion": 1,
            "providers": [
                {
                    "name": "xbench",
                    "folder": "xbench",
                    "type": "file",
                    "options": {
                        "path": self._dashboard_directory,
                        "foldersFromFilesStructure": True,
                    },
                }
            ],
        }
        # maybe allow configuring the scrape interval?
        self._prometheus_conf: dict[str, Any] = {
            "global": {
                "scrape_interval": "1m",
            },
            "scrape_configs": [
                {
                    "job_name": "central_metrics_poll",
                    "scrape_interval": "15s",
                    "file_sd_configs": [
                        {
                            "files": [
                                f"{os.path.basename(self._metrics_scrape_targets_directory)}/*.json"
                            ]
                        }
                    ],
                }
            ],
        }

    def _metrics_server_already_exists(self) -> bool:
        if self.node.ms:
            return True
        return False

    def _install_container_runtime(self):
        pkgs: list[str] = ["podman", "podman-plugins"]
        for pkg in pkgs:
            self.node.run(f"{self.node.yum.install_pkg_cmd()} {pkg}", sudo=True)

    def _create_container_network(self):
        self.node.run(
            f"podman network create {self._container_network_name}", sudo=True
        )

    def _set_directory_permissions(self):
        self.node.run(
            f"chown -R {self._nobody_uid}:{self._nobody_gid} /etc/prometheus", sudo=True
        )
        self.node.run(
            "chown -R"
            f" {self._nobody_uid}:{self._nobody_gid} {self.config.data_dir}/prometheus",
            sudo=True,
        )
        self.node.run(
            "chown -R"
            f" {self._grafana_uid}:{self._grafana_gid} {self.config.data_dir}/grafana",
            sudo=True,
        )
        self.node.run(
            f"chown -R {self._grafana_uid}:{self._grafana_gid} /etc/grafana/", sudo=True
        )

    def _create_prometheus_directories(self):
        prom_dirs: tuple[str, ...] = (
            self._metrics_scrape_targets_directory,
            f"{self.config.data_dir}/prometheus",
        )
        for d in prom_dirs:
            self.node.run(f"mkdir -p {d}", sudo=True)

    def _create_grafana_directories(self):
        graf_dirs: tuple[str, ...] = (
            "/etc/grafana",
            self._dashboard_directory,
            "/etc/grafana/provisioning",
            "/etc/grafana/provisioning/datasources",
            "/etc/grafana/provisioning/dashboards",
            f"{self.config.data_dir}/grafana",
        )
        for d in graf_dirs:
            self.node.run(f"mkdir -p {d}", sudo=True)

    def _create_config_files(self):
        # call this after _set_directory_permissions
        configs: dict[str, dict[str, Any]] = {
            "/etc/grafana/provisioning/datasources/local-prom.yml": self._grafana_conf,
            "/etc/grafana/provisioning/dashboards/dash.yml": self._dashboard_conf,
            "/etc/prometheus/prometheus.yml": self._prometheus_conf,
        }
        for conf in configs:
            with tempfile.NamedTemporaryFile("r+") as tmp:
                tmp.write(yaml.dump(configs[conf]))
                tmp.flush()
                remote_file_name: str = f"/tmp/{os.path.basename(tmp.name)}"
                self.node.scp_file(tmp.name, remote_file_name)
                self.node.run(f"mv {remote_file_name} {conf}", sudo=True)

    def _start_prometheus(self):
        cmd: list[str] = [
            f"podman run -d --name {self._prometheus_container_name}",
            f"--network {self._container_network_name}",
            f"--publish {self._prometheus_port}:9090",  # maybe allow configuring this port?
            "--volume"
            f" {self._metrics_scrape_targets_directory}:/etc/prometheus/targets",
            "--volume /etc/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml",
            f"--volume {self.config.data_dir}/prometheus:/prometheus",
            self._prometheus_container,
            "--storage.tsdb.retention.time=1y",  # maybe allow configuring retention?
            "--config.file=/etc/prometheus/prometheus.yml",
            "--storage.tsdb.path=/prometheus",
            "--web.console.libraries=/usr/share/prometheus/console_libraries",
            "--web.console.templates=/usr/share/prometheus/consoles",
        ]
        self.node.run(" ".join(cmd), sudo=True)

    def _start_grafana(self):
        # TODO: put credentials in vault.yaml
        # maybe allow setting the grafana port?
        cmd: list[str] = [
            f"podman run -d --name {self._grafana_container_name}",
            f"--network {self._container_network_name}",
            f"--publish {self._grafana_port}:3000",
            f"--env GF_SECURITY_ADMIN_USER={self.config.grafana_user}",
            f"--env GF_SECURITY_ADMIN_PASSWORD={self.config.grafana_password}",
            "--volume"
            " /etc/grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards",
            "--volume"
            " /etc/grafana/provisioning/datasources:/etc/grafana/provisioning/datasources",
            f"--volume {self._dashboard_directory}:/etc/grafana/dashboards",
            f"--volume {self.config.data_dir}/grafana:/var/lib/grafana",
            self._grafana_container,
        ]
        self.node.run(" ".join(cmd), sudo=True)

    def _upload_dashboards(self):
        dash_dir: str = self.xbench_config.get("dash_dir")
        for fname in os.listdir(dash_dir):
            self.logger.debug(f"uploading dashboard {os.path.join(dash_dir, fname)}")
            self.node.scp_file(os.path.join(dash_dir, fname), f"/tmp/{fname}")
        self.node.run(f"mv /tmp/*.json {self._dashboard_directory}", sudo=True)
        self.node.run(f"podman restart {self._grafana_container_name}", sudo=True)

    def _setup_storage(self):
        cmd: Optional[str]
        device: Optional[str]
        directory: str = self.config.data_dir
        cmd, device = mdadm_command(self.node)
        if cmd is not None:
            self.node.run(cmd, sudo=True)
        if device is not None:
            self.node.run(
                mkdir_command(directory, device, mount_to_parent=False), sudo=True
            )

    def configure(self):
        """
        install docker / podman
        start and enable the systemd unit
        create container network
        make grafana and prometheus directory structures
        set permissions
        create grafana and prometheus config files
        create volume lifecycle for automated backup and retention
        """
        self.logger.info("Setting up Metrics Server")
        self._install_container_runtime()
        self._create_container_network()
        self._setup_storage()
        self._create_grafana_directories()
        self._create_prometheus_directories()
        self._create_config_files()
        self._set_directory_permissions()

    def install(self) -> BackendTarget:
        """
        run the grafana and prometheus containers
        upload dashboards

        """
        self.logger.info("Starting up Metrics Server")
        self._start_prometheus()
        self._start_grafana()
        self._upload_dashboards()
        return BackendTarget(
            host="127.0.0.1",
            user="user",
            password="no value",
            database="no_value",
            port=0,
        )

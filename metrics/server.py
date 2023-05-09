import logging
import os
import tempfile

from compute.ssh_client import SshClient

from .metrics_target import MetricsTarget


class MetricsServer:
    """
    singleton class that provides dynamic registration of metric scraping targets
    """

    __instance = None

    def initialize(self, **kwargs):

        self.remote_target_path = kwargs.get("remote_target_path")
        self.logger = logging.getLogger(__name__)
        self._prometheus_user: str = "nobody"
        self._prometheus_group: str = self._prometheus_user

        hostname = kwargs.get("hostname", None)
        if hostname:  # Some cloud may not have MetricsServer
            self.ssh_client = SshClient(
                hostname=kwargs.get("hostname"),
                username=kwargs.get("username"),
                key_file=kwargs.get("key_file"),
            )
        else:
            self.ssh_client = None

        self.logger.info(f"Metrics server at {kwargs.get('hostname')}")

    def __new__(cls, *args, **kwargs):
        if not MetricsServer.__instance:
            MetricsServer.__instance = object.__new__(cls)
        return MetricsServer.__instance

    def register_metric_target(self, exporter: MetricsTarget):
        """Send metric file to the prometheus server

        Args:
            exporter (MetricsTarget): prometheus consumable metrics
        """
        if self.ssh_client is None:
            self.logger.warning('Metric server is missing in the config')

        else:
            t: str = exporter.target()
            fname: str = os.path.basename(exporter.target_name())
            self.logger.debug(f"Prometheus metric target: {t}")

            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.write(str.encode(t))
            temp_file.close()

            self.ssh_client.send_files(temp_file.name, f"/tmp/{fname}")

            # we have to use `mv` after `scp` because we are scp'ing a file to
            # a docker volume that will be owned by root
            finalize_file: str = f"""
            mv /tmp/{fname} {self.remote_target_path}/{fname}
            chown {self._prometheus_user}:{self._prometheus_group} {self.remote_target_path}/{fname}
            chmod +r {self.remote_target_path}/{fname}
            """

            self.ssh_client.run(finalize_file, sudo=True)
            os.unlink(temp_file.name)

    def deregister_metric_target(self, exporter: MetricsTarget):
        if self.ssh_client is None:
            self.logger.warning('Metric server is missing in the config')
        else:
            fname = exporter.target_name()
            self.ssh_client.run(
                f"rm {self.remote_target_path}/{fname}", sudo=True, ignore_errors=True
            )

    def deregister_cluster(self, cluster_name: str):
        if self.ssh_client:
            self.ssh_client.run(
                f"rm {self.remote_target_path}/{cluster_name}*.json",
                sudo=True,
                ignore_errors=True,
            )
            self.logger.info("Cluster has been de-register from Prometheus")

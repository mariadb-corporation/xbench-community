from typing import Optional

from cloud.cli_factory import CliFactory
from cloud.cloud_factory import CloudFactory
from compute import run_parallel
from metrics.server import MetricsServer
from xbench.common import klass_instance_clean

from .xbench import Xbench


class DeProvisioning(Xbench):
    """Main class to de-provision cluster in the cloud"""

    def __init__(
        self,
        cluster_name,
        cloud: Optional[str],
        cloud_region: Optional[str],
        artifact_dir: str,
        dry_run: bool = False,
        force: bool = False,
    ):
        super(DeProvisioning, self).__init__(cluster_name, dry_run)
        self.artifact_dir = f"{artifact_dir}/{cluster_name}"
        if not force or cloud is None:
            self.cluster = self.load_cluster()
        else:
            self.cluster_name = cluster_name
            self.cloud = cloud
            self.cloud_region = cloud_region

    def __deregister_from_MetricsServer(self):
        ms = MetricsServer()
        ms.deregister_cluster(self.cluster.cluster_name)

    def clean(self):
        """Tear down the entire cluster"""

        self.save_cluster(self.cluster, self.artifact_dir)
        for env in self.cluster.envs:

            cloud_config = self.load_cloud(env.cloud)
            region_config = cloud_config.get(env.region)

            MetricsServer().initialize(**region_config.get("metric_server", {}))

            # Loading cloud class dynamically
            cloud = CloudFactory().create_cloud_from_str(
                env.cloud, self.cluster_name, **region_config
            )

            ms = MetricsServer()
            ms.deregister_cluster(self.cluster.cluster_name)

            # I am ready to terminate all instances

            all_nodes = []
            for k, n in self.cluster.members.items():
                if n.vm.env == env.name:
                    if self.dry_run:
                        self.logger.info(f"Going to deprovision {n.asdict()}")
                    if n.vm.provisioned:
                        all_nodes.append(n)

            if cloud.is_persistent:
                if self.dry_run:
                    self.logger.info(f"Going to deprovision cluster and wipe all nodes")
                else:
                    self.logger.info("cleaning all instances")
                    clean_args = [
                        {"klass": member.get("klass"), "nodes": member.get("nodes")}
                        for member in self.cluster.group_nodes_by_name().values()
                        if member.get("env") == env.name or env.name == "*"
                    ]

                    noop = lambda x: x
                    run_parallel(clean_args, noop, klass_instance_clean)

            if not self.dry_run:
                if len(all_nodes) > 0:
                    cloud.terminate_instances(all_nodes)

                cloud.terminate_storage_instances(self.cluster.shared_storage)

        self.remove_cluster_yaml()
        self.logger.info(f"Deleted cluster file")

    def nuke(self):
        """Nuke the entire cluster by requesting resources from the cloud by tag"""
        cli = None
        cloud_config = self.load_cloud(self.cloud)
        region_config = cloud_config.get(self.cloud_region)

        MetricsServer().initialize(**region_config.get("metric_server", {}))
        ms = MetricsServer()
        ms.deregister_cluster(self.cluster_name)

        cli = CliFactory().create_cli_from_str(
            self.cloud, self.cluster_name, **region_config
        )

        if cli is not None:
            all_instances = cli.describe_instances_by_tag()
            all_volumes = cli.describe_volumes_by_tag()

            if self.dry_run:
                self.logger.info(f"Going to deprovision instances: {all_instances}")
                self.logger.info(f"Going to deprovision volumes: {all_volumes}")
                self.logger.info(f"Dry run finished.")
                return

            print(all_instances)
            if len(all_instances) > 0:
                cli.terminate_instances(all_instances)
                cli.wait_for_instances(all_instances, cli.ComputeState.terminated)

            print(all_volumes)
            if len(all_volumes) > 0:
                cli.delete_volumes(all_volumes)

        else:
            self.logger.warning("Only aws currently supported")

        self.remove_cluster_yaml()
        self.logger.info(f"Deleted cluster file")

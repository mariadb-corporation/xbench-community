import logging

from backend.abstract_backend import AbstractBackend
from cloud.abstract_cloud import AbstractCloud
from cloud.cloud_factory import CloudFactory
from compute import Cluster, ClusterState, Node
from xbench import Xbench, XbenchException


class CloudCommands(Xbench):
    def __init__(self, cluster_name: str):
        self.logger = logging.getLogger(__name__)
        super(CloudCommands, self).__init__(cluster_name)
        self.cluster: Cluster = self.load_cluster()

    def start_stop_cluster(self, on_off: str):
        for env in self.cluster.envs:
            cloud_config: dict = self.load_cloud(env.cloud)
            region_config: dict = cloud_config[env.region]
            c: AbstractCloud = CloudFactory().create_cloud_from_str(
                env.cloud, self.cluster_name, **region_config
            )

            instances: list[Node] = [
                self.cluster.members[k]
                for k in self.cluster.members
                if (
                    (
                        self.cluster.members[k].vm.storage
                        and self.cluster.members[k].vm.storage.type != "ephemeral"
                    )
                    or self.cluster.members[k].vm.storage is None # No storage - no problem 
                )
                and self.cluster.members[k].vm.env == env.name
            ]

            if on_off == "start":
                if self.cluster.state != ClusterState.down:
                    raise XbenchException("Cluster already running")

                new_instances = c.start_instances(instances)
                # After the start Public IP could change (at least in AWS), while Private IP should remind the same
                # Update cluster object with new instances
                for instance in new_instances:
                    if instance:
                        self.cluster.add_member(
                            instance_name=instance.vm.name, node=instance
                        )  # add_member will update by name

                self.cluster.state = ClusterState.ready
                self.save_cluster(self.cluster)

                # Start services (backend? only for now)
                for _, v in self.cluster.group_nodes_by_name().items():
                    if issubclass(v.get("klass"), AbstractBackend):
                        klass_instance = v.get("klass")(v.get("nodes"))
                        klass_instance.start()

            elif on_off == "stop":
                if self.cluster.state != ClusterState.ready:
                    raise XbenchException(
                        "Cluster is not ready (already shutdown or has not been"
                        " initialized)"
                    )

                if len(instances) > 0:
                    self.logger.info(
                        f"Shutting down {[e.vm.name for e in instances]}.  "
                        "Instances with ephemeral storage (if any) will be left running"
                    )
                    # Stop databases # TODO: stop every service
                    for _, v in self.cluster.group_nodes_by_name().items():
                        if issubclass(v.get("klass"), AbstractBackend):
                            klass_instance = v.get("klass")(v.get("nodes"))
                            klass_instance.stop()
                    # Stop instances
                    self.cluster.state = ClusterState.down
                    self.save_cluster(self.cluster)
                    c.stop_instances(instances)

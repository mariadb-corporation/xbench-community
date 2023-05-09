import dataclasses
import json
import logging
from typing import Optional, Tuple

from dacite import from_dict

# from backend.aurora.aurora_mysql import AuroraMySql
from cloud.gcp.gcp_alloydb_cli import GcpAlloyDBCli
from common import round_down_to_even

from ..exceptions import CloudCliException
from ..virtual_machine import VirtualMachine
from .exceptions import GcpAlloyDBCloudException

# https://cloud.google.com/compute/docs/general-purpose-machines#n2-high-mem
# Available CPU count values
# https://cloud.google.com/alloydb/docs/instance-primary-create
N2_HIGH_MEM_TYPES = {
    "n2-highmem-2": {"cpu_count": 2, "memory_gb": 16},
    "n2-highmem-4": {"cpu_count": 4, "memory_gb": 32},
    "n2-highmem-8": {"cpu_count": 8, "memory_gb": 64},
    "n2-highmem-16": {"cpu_count": 16, "memory_gb": 128},
    "n2-highmem-32": {"cpu_count": 32, "memory_gb": 256},
    "n2-highmem-64": {"cpu_count": 64, "memory_gb": 512},
}


class GcpAlloyDBCompute:
    def __init__(self, cli: GcpAlloyDBCli, **kwargs):
        self.logger = logging.getLogger(__name__)

        self.cli = cli
        self.cluster_name = cli.cluster_name
        self.cluster_password = kwargs.get("password")

        # Creating VM
        self.vm = from_dict(
            data_class=VirtualMachine,
            data=kwargs | {"cluster_name": self.cluster_name, "cloud": "gcp_alloydb"},
        )
        self.db_cluster = self.cluster_name.replace("_", "-")

    @property
    def instance_id(self):
        # if self.vm.id is None:
        pass

    @classmethod
    def from_vm(cls, cli: GcpAlloyDBCli, vm: VirtualMachine):
        return cls(cli, **dataclasses.asdict(vm))

    def get_nproc_memory(self, n2_type: str) -> Tuple[int, int]:
        """Return cpu count and memory gb for the instance type"""
        n2 = N2_HIGH_MEM_TYPES.get(n2_type, None)
        if n2 is None:
            raise GcpAlloyDBCloudException(
                f"Instance type {n2_type} not in {N2_HIGH_MEM_TYPES}"
            )
        else:
            return n2.get("cpu_count", 0), 1024 * n2.get("memory_gb", 0)

    def get_settings(self, nproc, memory_mb) -> dict:
        startup_settings = {}

        startup_settings["shared_buffers"] = round_down_to_even(memory_mb / 4)
        startup_settings["max_connections"] = nproc * 8 + 10
        startup_settings["max_connections"] = (
            256 + nproc
            if startup_settings["max_connections"] < 256
            else startup_settings["max_connections"]
        )
        # AlloyDB max_connections minimum allowed value is 1000
        if startup_settings["max_connections"] < 1000:
            self.logger.warning("Minimum value for max_connections is 1000")
            startup_settings["max_connections"] = 1000

        startup_settings["work_mem"] = round_down_to_even(
            startup_settings["shared_buffers"] / startup_settings["max_connections"]
        )
        # AlloyDB work_mem minimum allowed value is 64
        if startup_settings["work_mem"] < 64:
            startup_settings["work_mem"] = 64

        startup_settings["effective_cache_size"] = round_down_to_even(memory_mb * 0.75)
        startup_settings["max_worker_processes"] = nproc
        # AlloyDB max_worker_processes minimum allowed value is 64
        if startup_settings["max_worker_processes"] < 64:
            startup_settings["max_worker_processes"] = 64

        return startup_settings

    def create_db_cluster(self):
        """Implements
        https://cloud.google.com/sdk/gcloud/reference/alloydb/clusters/create
        """
        self.logger.info(f"Creating AlloyDB cluster {self.db_cluster}")
        cmd = f"clusters create {self.db_cluster} --region={self.vm.zone} --password={self.cluster_password} --disable-automated-backup"
        self.cli.run(cmd)

    def create_db_instance(self, instance_type: str = "PRIMARY", node_count: int = 1):
        """Implements
        https://cloud.google.com/sdk/gcloud/reference/beta/alloydb/instances/create
        """

        db_params = ""
        nproc, memory_mb = self.get_nproc_memory(self.vm.instance_type)
        settings = self.get_settings(nproc, memory_mb)
        if settings is not None:
            kv = []
            for k, v in settings.items():
                kv.append(f"{k}={v}")
            kv_str = ",".join(kv)
            db_params = f"--database-flags={kv_str}"

        if instance_type == "PRIMARY":  # There is only one primary
            instance_name = (
                f"primary-instance"  # same instance name allowed in different clusters
            )
            self.logger.info(
                f"Creating AlloyDB instance {instance_name}, instance_type {instance_type} "
            )

            cmd = f"""instances create {instance_name}
            --instance-type=PRIMARY
            {db_params}
            --cpu-count={nproc}
            --region={self.vm.zone}
            --cluster={self.db_cluster}
            """
            self.cli.run(cmd)
        else:
            instance_name = f"read--pool-instance"  # same instance name allowed in different clusters
            self.logger.info(
                f"Creating AlloyDB instance {instance_name}, instance_type {instance_type}, count {node_count} "
            )
            cmd = f"""instances create {instance_name}
                --instance-type=READ_POOL
                {db_params}
                --cpu-count={nproc}
                --region={self.vm.zone}
                --cluster={self.db_cluster}
                --read-pool-node-count={node_count}
                """
            self.cli.run(cmd)

    def get_endpoint(self):
        """Return IP of the primary instance"""
        instance_name = (
            f"primary-instance"  # same instance name allowed in different clusters
        )
        self.logger.info(f"Describing AlloyDB instance {instance_name}")
        cmd = f"""instances describe {instance_name}
        --region={self.vm.zone}
        --cluster={self.db_cluster}
        """
        stdout_str, _, _ = self.cli.run(cmd)
        endpoint = json.loads(stdout_str)
        return endpoint.get("ipAddress")

    def delete_db_cluster(self):
        # --force deletes instances (if any) within this cluster, before deleting the cluster.
        # See: https://cloud.google.com/sdk/gcloud/reference/beta/alloydb/clusters/delete
        cmd = f"clusters delete {self.db_cluster} --region={self.vm.zone} --quiet --force --async"
        self.cli.run(cmd)
        self.logger.info(f"Cluster {self.db_cluster} will be deleted soon")

    def create(self, node_count: int = 1) -> VirtualMachine:
        """Implements
        https://cloud.google.com/alloydb/docs/cluster-create

        Raises:
            GcpAlloyDBCloudException:

        Returns:
            VirtualMachine:
        """
        try:
            self.create_db_cluster()
            self.create_db_instance()  # Create Primary instance
            if node_count > 1:  # Create additional read only instances
                self.create_db_instance(
                    instance_type="READ-POOL", node_count=node_count - 1
                )
            self.vm.network.private_ip = self.get_endpoint()

            return self.vm

        except CloudCliException as e:
            raise GcpAlloyDBCloudException(f"aws aurora command failed with {e}")

    def destroy(self):
        self.delete_db_cluster()

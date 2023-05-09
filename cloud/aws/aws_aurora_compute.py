# Attach volume to the instance
# https://github.com/GoogleCloudPlatform/PerfKitBenchmarker/blob/2bb427083c4cf46fddc8e06fadec79937dfa66a2/perfkitbenchmarker/providers/aws/aws_disk.py

# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import dataclasses
import json
import logging

from dacite import from_dict

from backend import AuroraMySql
from cloud.abstract_compute import AbstractCompute
from cloud.aws.aws_aurora_cli import AwsAuroraCli
from common import constant_delay, get_class_from_klass, retry
from compute.node import Node

from ..exceptions import CloudCliException
from ..virtual_machine import VirtualMachine
from .exceptions import (
    AwsAuroraCliException,
    AwsAuroraCliWaitException,
    AwsAuroraComputeException,
)


class AwsAuroraCompute(AbstractCompute):
    def __init__(self, cli: AwsAuroraCli, **kwargs):
        """_summary_

        Args:
            cli (AwsAuroraCli): Cloud CLI module
            kwargs:  Instance parameters from impl.yam
        """
        self.logger = logging.getLogger(__name__)

        self.cli = cli
        self.cluster_name = cli.cluster_name

        # Creating VM
        self.vm = from_dict(
            data_class=VirtualMachine,
            data=kwargs | {"cluster_name": self.cluster_name, "cloud": "aws_aurora"},
        )
        # This is creating AuroraMySQL or AuroraPostgresql
        self.backend_klass = get_class_from_klass(kwargs.get("klass", None))
        self.aurora = self.backend_klass(Node(self.vm))

        # The parameter DBClusterIdentifier is not a valid identifier. Identifiers must begin with a letter; must contain only ASCII letters, digits, and hyphens; and must not end with a hyphen or contain two consecutive hyphens.
        self.db_cluster = self.cluster_name.replace("_", "-")
        self.instance_identifier = (
            f"i-aws-{self.db_cluster}-{self.vm.instance_type.replace('.','-')}"
        )

    @property
    def instance_id(self):
        # if self.vm.id is None:
        pass

    @classmethod
    def from_vm(cls, cli: AwsAuroraCli, vm: VirtualMachine):
        return cls(cli, **dataclasses.asdict(vm))

    def create_db_cluster(self):
        # https://docs.aws.amazon.com/cli/latest/reference/rds/create-db-cluster.html
        self.logger.info(f"Creating Aurora instance cluster {self.db_cluster}")
        cmd = f"""create-db-cluster
        --db-cluster-identifier={self.db_cluster}
        --engine={self.aurora.config.engine}
        --engine-version={self.aurora.config.engine_version}
        --master-username={self.aurora.config.db.user}
        --master-user-password={self.aurora.config.db.password}
        --db-subnet-group-name={self.cli.db_subnet_group_name}
        --vpc-security-group-ids={self.cli.vpc_security_group}
        --port={self.aurora.config.db.port}
        --tags Key=Name,Value={self.db_cluster}
        """
        self.cli.run(cmd)

    def delete_db_cluster(self):
        cmd = (
            "delete-db-cluster"
            f" --db-cluster-identifier={self.db_cluster} --skip-final-snapshot"
        )
        self.cli.run(cmd)

    @retry(
        AwsAuroraCliWaitException,
        AwsAuroraCliException,
        delays=constant_delay(delay=30, attempts=20),
        max_delay=600,
    )

    # TODO: make an Enum for all the clsuter states and replace these strings
    def wait_for_db_cluster(self, status: str = "available"):
        cmd = (
            f"describe-db-clusters --db-cluster-identifier={self.db_cluster} --output"
            " json"
        )
        # to prevent ValueError Format specifier missing precision
        final_cmd = cmd + " | jq '.DBClusters[] | { status: .Status }' | jq -s"
        stdout, stderr, exit_code = self.cli.run(final_cmd)
        response = json.loads(stdout)[0]  # there is only one cluster
        if response.get("status") != status:
            raise AwsAuroraCliWaitException(f"cluster {self.db_cluster} is not ready")

    def create_db_instance(self):
        # https://docs.aws.amazon.com/cli/latest/reference/rds/create-db-instance.html
        # aws rds create-db-instance --db-instance-identifier=aws-db-r5-12xlarge-aurora-tpcc-server-1 --db-instance-class=db.r5.12xlarge --engine=aurora-mysql --availability-zone=us-west-2a --db-parameter-group-name=default.aurora-mysql8.0 --db-cluster-identifier=aws-db-r5-12xlarge-aurora-tpcc-cluster --publicly-accessible

        self.logger.info(f"Launching Aurora instance {self.instance_identifier}")
        cmd = (
            "create-db-instance"
            f" --db-instance-identifier={self.instance_identifier} --db-cluster-identifier={self.db_cluster} --engine"
            f" {self.aurora.config.engine} --db-instance-class={self.vm.instance_type} --availability-zone={self.vm.zone} --db-parameter-group-name={self.aurora.config.db_parameter_group_name} --publicly-accessible"
            " --no-multi-az"
        )
        self.cli.run(cmd)
        self.vm.id = self.instance_identifier

    def delete_db_instance(self):
        cmd = (
            "delete-db-instance"
            f" --db-instance-identifier={self.vm.id} --skip-final-snapshot"
            " --delete-automated-backups"
        )
        self.cli.run(cmd)

    @retry(
        AwsAuroraCliWaitException,
        AwsAuroraCliException,
        delays=constant_delay(delay=30, attempts=20),
        max_delay=600,
    )
    def wait_for_db_instance(self, status: str = "available"):
        # # status has to be "available"
        cmd = (
            f"describe-db-instances --output json --db-instance-identifier={self.vm.id}"
        )
        final_cmd = (
            cmd + " | jq '.DBInstances[] | { status: .DBInstanceStatus }' | jq -s"
        )
        stdout, stderr, exit_code = self.cli.run(final_cmd)
        response = json.loads(stdout)[0]  # there is only one instance
        if response.get("status") != status:
            raise AwsAuroraCliWaitException(f"instance {self.vm.id} is not ready")

    def create(self) -> VirtualMachine:
        """Implements
        https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.CreateInstance.html

        Raises:
            AwsAuroraComputeException:

        Returns:
            VirtualMachine:
        """
        try:
            self.create_db_cluster()
            self.wait_for_db_cluster()
            self.create_db_instance()
            self.wait_for_db_instance()
            self.vm.network.public_ip = self.get_endpoint()
            self.vm.network.cloud_type = (  # currently we use public ip, see publicly-accessible parameter in create cluster
                "private_cloud"
            )

            return self.vm

        except CloudCliException as e:
            raise AwsAuroraComputeException(f"aws aurora command failed with {e}")

    @retry(
        AwsAuroraCliWaitException,
        AwsAuroraCliException,
        delays=constant_delay(delay=30, attempts=20),
        max_delay=600,
    )
    def get_endpoint(self):
        # Endpoint looks like
        # Endpoint": "dsv.cluster-caolmoycvvxz.us-west-2.rds.amazonaws.com"
        cmd = (
            f"describe-db-clusters --db-cluster-identifier={self.db_cluster} --output"
            " json | jq '.DBClusters[] | { endpoint: .Endpoint }' | jq -s"
        )
        # return f"{self.db_cluster}.cluster-caolmoycvvxz.{self.cli.aws_region}.rds.amazonaws.com"
        stdout_str, _, _ = self.cli.run(cmd)
        endpoint = json.loads(stdout_str)[0]
        return endpoint.get("endpoint")

    def destroy(self):
        # maybe wait for status "deleting" not longer
        cmd = (
            "delete-db-instance"
            f" --db-instance-identifier={self.vm.id} --skip-final-snapshot"
            " --delete-automated-backups"
        )
        _, _, _ = self.cli.run(cmd)
        self.wait_for_db_instance(status="deleting")

        cmd = (
            "delete-db-cluster"
            f" --db-cluster-identifier={self.db_cluster} --skip-final-snapshot"
        )
        _, _, _ = self.cli.run(cmd)
        self.logger.info(f"Audra cluster {self.db_cluster} has been deleted")

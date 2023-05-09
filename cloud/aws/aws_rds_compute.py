# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import dataclasses
import json
import logging

from dacite import from_dict

from backend.rds.rds_mysql import RdsMySql
from cloud.aws.aws_rds_cli import AwsRdsCli
from common import constant_delay, retry
from compute.node import Node

from ..abstract_compute import AbstractCompute
from ..exceptions import CloudCliException
from ..virtual_machine import VirtualMachine
from .exceptions import (
    AwsRdsCliException,
    AwsRdsCliWaitException,
    AwsRdsComputeException,
)


class AwsRdsCompute(AbstractCompute):
    def __init__(self, cli: AwsRdsCli, **kwargs):
        self.logger = logging.getLogger(__name__)

        self.cli = cli
        self.cluster_name = cli.cluster_name

        # Creating VM
        self.vm = from_dict(
            data_class=VirtualMachine,
            data=kwargs | {"cluster_name": self.cluster_name, "cloud": "aws_rds"},
        )
        self.rds = RdsMySql(Node(self.vm))

        # The parameter DBClusterIdentifier is not a valid identifier. Identifiers must begin with a letter; must contain only ASCII letters, digits, and hyphens; and must not end with a hyphen or contain two consecutive hyphens.
        self.db_cluster = self.cluster_name.replace("_", "-")
        self.vm.id = f"i-aws-rds-{self.vm.instance_type.replace('.','-')}"

    @property
    def instance_id(self):
        # if self.vm.id is None:
        pass

    @classmethod
    def from_vm(cls, cli: AwsRdsCli, vm: VirtualMachine):
        return cls(cli, **dataclasses.asdict(vm))

    @retry(
        AwsRdsCliException,
        AwsRdsCliException,
        delays=constant_delay(delay=30, attempts=20),
        max_delay=600,
    )
    def create_db_instance(self):
        # https://docs.aws.amazon.com/cli/latest/reference/rds/create-db-instance.html
        # aws rds create-db-instance --db-instance-identifier=aws-db-r5-12xlarge-aurora-tpcc-server-1 --db-instance-class=db.r5.12xlarge --engine=aurora-mysql --availability-zone=us-west-2a --db-parameter-group-name=default.aurora-mysql8.0 --db-cluster-identifier=aws-db-r5-12xlarge-aurora-tpcc-cluster --publicly-accessible

        self.logger.info(f"Launching RDS instance {self.vm.id}")
        cmd = f"""create-db-instance
        --db-instance-identifier={self.vm.id}
        --engine={self.rds.config.engine}
        --engine-version={self.rds.config.engine_version}
        --db-instance-class={self.vm.instance_type}
        --availability-zone={self.vm.zone}
        --publicly-accessible
        --master-username={self.rds.config.db.user}
        --master-user-password={self.rds.config.db.password}
        --db-subnet-group-name={self.cli.db_subnet_group_name}
        --vpc-security-group-ids={self.cli.vpc_security_group}
        --port={self.rds.config.db.port}
        --tags Key=Name,Value={self.db_cluster}
        --allocated-storage={self.vm.storage.size}
        --iops={self.vm.storage.iops}
        --storage-type={self.vm.storage.type}
        --backup-retention-period=0
        --db-parameter-group-name={self.rds.config.db_parameter_group_name}
        """
        try:
            self.cli.run(cmd)
        except CloudCliException as e:
            if "DBInstanceAlreadyExists" in str(e):
                self.logger.warning(
                    f"Instance {self.vm.id} already exists. Going to re-use it"
                )
            else:
                raise

    def delete_db_instance(self):
        cmd = f"delete-db-instance --db-instance-identifier={self.vm.id} --skip-final-snapshot --delete-automated-backups"
        self.cli.run(cmd)

    @retry(
        AwsRdsCliWaitException,
        AwsRdsCliException,
        delays=constant_delay(delay=60, attempts=20),
        max_delay=600,
    )
    def wait_for_db_instance(self, status: str = "available"):
        # # status has to be "available"
        self.logger.info("Waiting for the instance became available...")
        cmd = f"describe-db-instances --db-instance-identifier={self.vm.id}"
        final_cmd = (
            cmd + " | jq '.DBInstances[] | { status: .DBInstanceStatus }' | jq -s"
        )
        stdout, stderr, exit_code = self.cli.run(final_cmd)
        response = json.loads(stdout)[0]  # there is only one instance
        if response.get("status") != status:
            raise AwsRdsCliWaitException(f"instance {self.vm.id} is not ready")

    def create(self) -> VirtualMachine:
        """Implements
        https://docs.aws.amazon.com/cli/latest/reference/rds/create-db-instance.html

        Raises:
            AwsAuroraComputeException:

        Returns:
            VirtualMachine:
        """
        try:
            self.create_db_instance()
            self.wait_for_db_instance()
            self.vm.network.public_ip = self.get_endpoint()
            self.vm.network.cloud_type = "private_cloud"  # currently we use public ip, see publicly-accessible parameter in create cluster

            return self.vm

        except CloudCliException as e:
            raise AwsRdsComputeException(f"aws rds  command failed with {e}")

    @retry(
        AwsRdsCliWaitException,
        AwsRdsCliException,
        delays=constant_delay(delay=30, attempts=20),
        max_delay=600,
    )
    def get_endpoint(self):
        """Return domain name for the main? read/write? endpoint"""
        cmd = f"describe-db-instances --db-instance-identifier={self.vm.id}  | jq '.DBInstances[] | {{ endpoint: .Endpoint }}' | jq -s"
        stdout_str, _, _ = self.cli.run(cmd)
        # [{'endpoint': {'Address': 'i-aws-rds-db-r5-2xlarge.crhax4z1fffh.us-west-2.rds.amazonaws.com', 'Port': 3306, 'HostedZoneId': 'Z1PVIF0B656C1W'}}]
        endpoints = json.loads(stdout_str)

        return endpoints[0]["endpoint"].get("Address")

    def destroy(self):
        # maybe wait for status "deleting" not longer
        cmd = f"delete-db-instance --db-instance-identifier={self.vm.id} --skip-final-snapshot --delete-automated-backups"
        _, _, _ = self.cli.run(cmd)
        self.wait_for_db_instance(status="deleting")

        self.logger.info(f"RDS instance {self.vm.id} has been deleted")

# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

from typing import Dict

from compute import RunSubprocess

from ..abstract_cli import AbstractCli
from .exceptions import AwsRdsCliException

AWS_CLI_VERSION_REQUIRED = "2."

# AWS cli examples: https://github.com/aws/aws-cli/tree/develop/awscli/examples/ec2


class AwsRdsCli(AbstractCli):
    def __init__(self, cluster_name: str, **kwargs):
        """Implements AWS RDS

        Args:
            cluster_name (str): cluster name
            kwargs: region config fields
        Raises:
            AwsRdsCliException: Generic exception for the class
        """
        self.aws_region = "us-west-2"
        self.aws_access_key_id = ""
        self.aws_secret_access_key = ""
        self.db_subnet_group_name = ""
        self.vpc_security_group = ""

        super(AwsRdsCli, self).__init__(cluster_name, **kwargs)

        # Check jq command
        proc = RunSubprocess(cmd="which jq", timeout=15)
        _, _, ret_code = proc.run()
        if ret_code == 127:  # Not found
            raise AwsRdsCliException("jq client is not available")
        self.logger.debug("jq command found")

    def check_cli_version(self):
        cmd = "--version"
        stdout, _, _ = self.run(cmd=cmd, timeout=30, shell=True)
        if f"aws-cli/{AWS_CLI_VERSION_REQUIRED}" not in stdout:
            raise AwsRdsCliException("aws cli version 2 is not installed")
        else:
            self.logger.debug("AWS CLI 2 is installed")

        return self.run(cmd=cmd, timeout=30, shell=True)

    def get_base_command(self) -> str:
        cmd = f"export AWS_ACCESS_KEY_ID={self.aws_access_key_id} && export AWS_SECRET_ACCESS_KEY={self.aws_secret_access_key} && aws rds --region {self.aws_region} --output json "
        return cmd

    def describe_instance(self):
        # aws rds describe-db-instances --region us-west-2 --output json
        pass

    def describe_instances_by_tag(self):
        # TODO need to implement
        pass
        # """Return cluster if exists
        # Tags support is very strange in RDS so I keep this function for compatibility purpose only
        # Returns:
        #     cluster_name, status
        # """
        # cmd = f"describe-db-clusters --filters Name=db-cluster-id,Values={self.db_cluster} --output json"
        # # to prevent ValueError Format specifier missing precision
        # final_cmd = (
        #     cmd
        #     + " | jq '.DBClusters[] | {cluster_name: .DBClusterIdentifier, status: .Status }' | jq -s"
        # )
        # stdout, stderr, exit_code = self.run(final_cmd)
        # response = json.loads(stdout)  # there is only one cluster
        # return response

    def terminate_instances(self, instances: list[Dict]):
        """Terminated instances"""

    def wait_for_instances(self, instances: list[Dict], instance_status: str):
        """Wait for status"""

    def describe_volumes_by_tag(self) -> list[Dict]:
        """List of attached volumes per cluster"""

    def delete_volumes(self, volumes: list[Dict]):
        """Delete attached volumes"""

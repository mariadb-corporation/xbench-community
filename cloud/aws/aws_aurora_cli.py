# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import json
from typing import Dict

from compute import RunSubprocess

from ..abstract_cli import AbstractCli
from .aws_rds_cli import AwsRdsCli
from .exceptions import AwsAuroraCliException

AWS_CLI_VERSION_REQUIRED = "2."

# AWS cli examples: https://github.com/aws/aws-cli/tree/develop/awscli/examples/ec2


class AwsAuroraCli(AwsRdsCli):
    def __init__(self, cluster_name: str, **kwargs):
        self.db_cluster = cluster_name.replace("_", "-")

        super(AwsAuroraCli, self).__init__(cluster_name, **kwargs)

    def describe_instance(self):
        # aws rds describe-db-instances --region us-west-2 --output json
        pass

    def describe_instances_by_tag(self):
        """Return cluster if exists
        Tags support is very strange in RDS so I keep this function for compatibility purpose only
        Returns:
            cluster_name, status
        """
        cmd = f"describe-db-clusters --filters Name=db-cluster-id,Values={self.db_cluster} --output json"
        # to prevent ValueError Format specifier missing precision
        final_cmd = (
            cmd
            + " | jq '.DBClusters[] | {cluster_name: .DBClusterIdentifier, status: .Status }' | jq -s"
        )
        stdout, stderr, exit_code = self.run(final_cmd)
        response = json.loads(stdout)  # there is only one cluster
        return response

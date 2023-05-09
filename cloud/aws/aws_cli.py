# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import json
from enum import Enum
from typing import Dict, List

from compute import RunSubprocess

from ..abstract_cli import AbstractCli, SecurityRecord
from ..exceptions import CloudCliException
from .exceptions import AwsCliException

AWS_CLI_VERSION_REQUIRED = "2."
AWS_RETRY_MODE = (  # https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-retries.html#cli-usage-retries-modes
    "adaptive"
)
AWS_MAX_ATTEMPTS = 10


# AWS cli examples: https://github.com/aws/aws-cli/tree/develop/awscli/examples/ec2


class AwsCli(AbstractCli):
    class ComputeState(str, Enum):
        running = "instance-running"
        terminated = "instance-terminated"
        stopped = "instance-stopped"

        def __repr__(self):
            return self.value

    class StorageState(str, Enum):
        ready = "volume-available"
        in_use = "volume-in-use"
        deleted = "volume-deleted"

        def __repr__(self):
            return self.value

    def __init__(self, cluster_name: str, **kwargs):
        self.aws_region = "us-west-2"
        self.aws_access_key_id = ""
        self.aws_secret_access_key = ""
        self.security_group = ""
        self.placement_group = None
        self.key_name = ""
        self.key_file = ""

        super(AwsCli, self).__init__(cluster_name, **kwargs)

        # Check jq command
        proc = RunSubprocess(cmd="which jq", timeout=15)
        _, _, retcode = proc.run()
        if retcode == 127:  # Not found
            raise AwsCliException("jq client is not available")
        self.logger.debug("jq command found")

        # An important mapping of zones name - zones Ids
        self.describe_availability_zones()

    def check_cli_version(self):
        cmd = "--version"
        stdout, _, _ = self.run(cmd=cmd, timeout=30, shell=True)
        if f"aws-cli/{AWS_CLI_VERSION_REQUIRED}" not in stdout:
            raise AwsCliException("aws cli version 2 is not installed")
        else:
            self.logger.debug("AWS CLI 2 is installed")

        return self.run(cmd=cmd, timeout=30, shell=True)

    def get_base_command(self) -> str:

        cmd = (  # , "--profile", self.profile_name]
            f"export AWS_ACCESS_KEY_ID={self.aws_access_key_id} && export"
            f" AWS_SECRET_ACCESS_KEY={self.aws_secret_access_key} && export"
            f" AWS_MAX_ATTEMPTS={AWS_MAX_ATTEMPTS} && export"
            f" AWS_RETRY_MODE={AWS_RETRY_MODE} && aws --region"
            f" {self.aws_region} --output json "
        )
        return cmd

    def describe_availability_zones(self):
        """Describe zones for given region
        This command used for pre-check that requested zone is availbel in the region and aws cli correctly configured.
        To make it works I had to add an Administrator Access to the user cbench
        """
        cmd = (
            f"ec2 describe-availability-zones --region {self.aws_region}  | jq"
            " '.AvailabilityZones[] | {zoneName: .ZoneName, zoneId: .ZoneId}' |"
            " jq -s"
        )
        stdout_str, _, _ = self.run(cmd)
        zones = json.loads(stdout_str)
        self.logger.info(f"Zone mapping for region {self.aws_region}: {zones}")

    def describe_instances_by_tag(self) -> list[Dict]:
        # aws ec2 describe-instances --output json --region $REGION --filters Name=tag:Name,Values=cl_dsv* Name=instance-state-name,Values=pending,running  |  jq  '.Reservations[].Instances[] | {id: .InstanceId }' | jq -s

        cmd = (
            "ec2 describe-instances --output json --filters Name=tag:Name,Values=%s*"
            " Name=instance-state-name,Values=pending,running  | jq "
            " '.Reservations[].Instances[] | {id: .InstanceId, private_ip:"
            " .PrivateIpAddress, public_ip: .PublicIpAddress, name: .Tags[].Value}' |"
            " jq -s" % (self.cluster_name)
        )
        stdout_str, _, _ = self.run(cmd)
        return json.loads(stdout_str)  # this is a list of dict

    def describe_volumes_by_tag(self) -> list[Dict]:
        # aws ec2 describe-instances --output json --region $REGION --filters Name=tag:Name,Values=cl_dsv* Name=instance-state-name,Values=pending,running  |  jq  '.Reservations[].Instances[] | {id: .InstanceId }' | jq -s

        cmd = (
            "ec2 describe-volumes --output json --filters Name=tag:Name,Values=%s*  |"
            " jq  '.Volumes[] | {id: .VolumeId, name: .Tags[].Value}' | jq -s"
            % (self.cluster_name)
        )
        stdout_str, _, _ = self.run(cmd)
        return json.loads(stdout_str)  # this is a list of dict

    def wait_for_instances(self, instances: list[Dict], instance_status: str):
        for instance in instances:
            self.wait_for_instance(instance.get("id", None), instance_status)

    def wait_for_instance(self, instance_id: str, wait_for_status: str):
        cmd = (  # ToDO instance-status-ok is slow.  instance-running is fast but it could be not ready for ssh yet
            f"ec2 wait {wait_for_status} --instance-ids {instance_id}"
        )
        _, _, _ = self.run(cmd)

    def terminate_instances(self, instances: list[Dict]):
        for instance in instances:
            self.terminate_instance(instance.get("id", None))

    def terminate_instance(self, instance_id: str):
        cmd = f"ec2 terminate-instances --instance-ids {instance_id}"
        _, _, _ = self.run(cmd)

    def delete_volumes(self, volumes: list[Dict]):
        for volume in volumes:
            self.delete_volume(volume.get("id", None))

    def delete_volume(self, volume_id: str):
        cmd = f"ec2 delete-volume --volume-id {volume_id}"
        _, _, _ = self.run(cmd)

    # TODO - check if instance type is available
    def instance_type_offerings(self, zone):
        """_summary_"""
        # aws ec2 describe-instance-type-offerings --location-type "availability-zone" --filters Name=location,Values=us-west-2d --region us-west-2 | jq '.InstanceTypeOfferings[] | {instance_type: .InstanceType}' | jq -s
        # aws ec2 describe-instance-type-offerings --location-type "availability-zone" --filters Name=location,Values=us-west-2d --region us-west-2 --query "InstanceTypeOfferings[*].[InstanceType]"

    def describe_instance_type(self, instance_type) -> Dict:
        """Implements
        https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-instance-types.html

        This command return something like:
        {
        "instance_type": "c5d.4xlarge",
        "hypervisor": "nitro",
        "nvme_support": "required",
        "ebs_baseline_iops": 20000,
        "ebs_baseline_throughput": 593.75,
        "local_nvme": true,
        "local_nvme_disks": [
            {
            "SizeInGB": 400,
            "Count": 1,
            "Type": "ssd"
            }
        ]
        }

        """
        try:
            cmd = (
                "ec2 describe-instance-types --region"
                f" {self.aws_region} --instance-types {instance_type} | jq"
                " '.InstanceTypes[] | {instance_type: .InstanceType, hypervisor:"
                " .Hypervisor, nvme_support: .EbsInfo.NvmeSupport, ebs_baseline_iops:"
                " .EbsInfo.EbsOptimizedInfo.BaselineIops,ebs_baseline_throughput:"
                " .EbsInfo.EbsOptimizedInfo.BaselineThroughputInMBps, local_nvme:"
                " .InstanceStorageSupported, local_nvme_disks:"
                " .InstanceStorageInfo.Disks}'  | jq -s"
            )
            stdout_str, _, _ = self.run(cmd)
            info = json.loads(stdout_str)[0]
            return info
        except CloudCliException as e:
            if "InvalidInstanceType" in str(e):
                raise AwsCliException(f"Instance {instance_type} does not exists")
            else:
                raise

    def list_security_access(self) -> List[SecurityRecord]:
        cmd = (
            "ec2 describe-security-groups  --no-paginate --group-ids"
            f" {self.security_group} |  jq  '.SecurityGroups[].IpPermissions[]  |"
            " {from: .FromPort, to: .ToPort, ip_ranges: .IpRanges }' | jq -s"
        )
        res: List[SecurityRecord] = []
        stdout_str, _, _ = self.run(cmd)
        info = json.loads(stdout_str)
        for a in info:
            for r in a.get("ip_ranges"):
                res.append(
                    SecurityRecord(
                        port_from=a.get("from"),
                        port_to=a.get("to"),
                        cidr=r.get("CidrIp"),
                        desc=r.get("Description"),
                    )
                )
        return res

    def authorize_access(self, rec: SecurityRecord):
        cmd = (
            "ec2 authorize-security-group-ingress --group-id"
            f" {self.security_group} --ip-permissions"
            f' "IpProtocol=tcp,FromPort={rec.port_from},ToPort={rec.port_to},IpRanges=[{{CidrIp='
            f"{rec.cidr}"
            + '}]" '
        )
        stdout_str, _, _ = self.run(cmd)

    def revoke_access(self, rec: SecurityRecord):
        cmd = (
            "ec2 revoke-security-group-ingress --group-id"
            f" {self.security_group} --ip-permissions"
            f' "IpProtocol=tcp,FromPort={rec.port_from},ToPort={rec.port_to},IpRanges=[{{CidrIp='
            f"{rec.cidr}"
            + '}]" '
        )
        stdout_str, _, _ = self.run(cmd)

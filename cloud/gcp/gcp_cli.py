# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import json
import os
import random
import string
from enum import Enum
from functools import reduce
from typing import Any, Dict, List, Optional

from packaging import version

from ..abstract_cli import AbstractCli, SecurityRecord
from ..virtual_machine import VirtualMachine
from .exceptions import GcpCliException

GCP_CLI_VERSION_REQUIRED = "414.0.0"  # will be parsed using packaging.version.parse()


class GcpCli(AbstractCli):
    class ComputeState(str, Enum):
        running = "RUNNING"
        terminated = "TERMINATED"
        stopped = "STOPPING"

        def __repr__(self):
            return self.value

    # StorageState should come from AbstractCli. Current GCP does not use storage state

    def __init__(self, cluster_name: str, **kwargs):
        self.gcp_region = ""
        self.service_account_file = ""  # Path to json file for specific service account
        self.gcp_project_id = ""
        self.key_file = ""
        self.network = ""

        super(GcpCli, self).__init__(cluster_name, **kwargs)
        self._check_stderr = False

        self.authorize_service_account()

    def authorize_service_account(self):
        """This is a critical step before running any other commands

        Returns:
            Exception
        """

        cmd = (
            "gcloud auth activate-service-account --key-file"
            f" {self.service_account_file}"
        )
        _, _, _ = self.run(cmd=cmd, timeout=30, shell=True, use_base_command=False)
        self.logger.debug(
            f"gcloud activated service account from file {self.service_account_file}"
        )

    def check_cli_version(self):
        """Let's check that we have required gcloud installed

        Raises:
            GcpCliException: _description_
        """

        grep_pattern_version = "[0-9]\+\.[0-9]\+\.[0-9]\+"
        cmd = (
            f'--version | grep -o "Google Cloud SDK {grep_pattern_version}" | grep -o'
            f' "{grep_pattern_version}"'
        )
        stdout, _, _ = self.run(cmd=cmd, timeout=30, shell=True)
        version_installed = version.parse(stdout)
        if version_installed < version.parse(GCP_CLI_VERSION_REQUIRED):
            raise GcpCliException(f"gcloud {GCP_CLI_VERSION_REQUIRED} is not installed")
        else:
            self.logger.debug(
                f"gcloud {version_installed} is installed and "
                f" {GCP_CLI_VERSION_REQUIRED} is required"
            )

    def get_base_command(self) -> str:
        # TODO: Refactor hard-coded project ID
        cmd = f"gcloud --project={self.gcp_project_id} --format=json "
        return cmd

    def describe_availability_zones(self):
        """Describe zones for given region."""
        cmd = (  # {self.aws_region}  | jq '.AvailabilityZones[] | {{zoneName: .ZoneName, zoneId: .ZoneId}}' | jq -s"
            f"compute zones list"
        )
        stdout_str, _, _ = self.run(cmd, timeout=30)
        zones = json.loads(stdout_str)
        # self.logger.info(f"Zone mapping for region {self.aws_region}: {zones}")
        self.logger.info(f"Zones list: {zones}")

    def create(self, vm: VirtualMachine, image: dict, tags: Optional[list]) -> Any:
        format_arg = lambda a: a.replace("_", "-")

        instance_name = format_arg(f"{vm.cluster_name}-{vm.name}")
        zone_id = vm.zone
        instance_type = vm.instance_type

        image_family_id = image.get("image_family", None)
        image_id = image.get("image_id", None)

        if image_family_id is None and image_id is None:
            raise GcpCliException(
                "Both 'image_family' and 'image_id' are empty. At least one must be"
                " specified."
            )
        cmd = f"""compute instances create
        {instance_name}
        --zone {zone_id}
        --machine-type={instance_type}
        --boot-disk-type=pd-ssd
        --network {self.network}
        """
        if vm.pub_file:
            if not os.path.exists(vm.pub_file):
                m = f"GCP key file does not exist: {vm.pub_file}"
                self.logger.error(m)
                raise GcpCliException(m)  # silenced in GcpCloud.launch_instance()
            cmd = cmd + f"--metadata-from-file ssh-keys={vm.pub_file} "
        # handle optional params
        render_arg = (
            lambda name, val: f"--{format_arg(name)}={val} " if val is not None else ""
        )
        add_image_arg = lambda name: render_arg(name, image.get(name, None))
        cmd = reduce(
            lambda p, c: p + add_image_arg(c),
            ["image_family", "image_project", "image_id"],
            cmd,
        )
        cmd += (
            render_arg("tags", format_arg(",".join(tags))) if tags is not None else ""
        )

        stdout_str, stderr, exit_code = self.run(cmd)
        instances = json.loads(stdout_str)
        self.logger.debug(f"GCP instances create returned: {instances}")
        if exit_code != 0:
            raise GcpCliException(
                f"GCP cannot create instance {instance_name}: {stderr}"
            )

        return instances

    def terminate_instance(self, instance_id, zone, ignore_error: bool = False):
        cmd = f"""compute instances delete
        {instance_id}
        --zone {zone}
        --delete-disks=all
        --quiet
        """

        _, stderr, exit_code = self.run(cmd)
        if not ignore_error and exit_code != 0:
            raise GcpCliException(f"GCP cannot delete instance {instance_id}: {stderr}")

    def describe_instances_by_tag(self, is_short=True) -> list[Dict]:
        cmd = f"""compute instances list
        --filter=\"tags:{self.cluster_name}\"
        """

        cmd += (
            " | jq '.[] | {id: .id, name: .name, tags: .tags, private_ip:"
            " .networkInterfaces[].networkIP, public_ip:"
            " .networkInterfaces[].accessConfigs[].natIP, zone: .zone}' -r | jq -s"
            if is_short == True
            else ""
        )

        stdout_str, _, _ = self.run(cmd)
        return json.loads(stdout_str)  # this is a list of dict

    def describe_volumes_by_tag(self) -> list[Dict]:
        """Nuke functionality wants this function. GCP takes cares about all volume when delete instances

        Returns:
            list[Dict]: _description_
        """

        cmd = f"""compute disks list
        --filter=\"tags:{self.cluster_name}\"
        """
        cmd += " | jq '.[] | {id: .id, zone: .zone}' -r | jq -s"

        stdout_str, _, _ = self.run(cmd)
        return json.loads(stdout_str)  # this is a list of dict

    def terminate_instances(self, instances: list[Dict]):
        for instance in instances:
            self.terminate_instance(
                instance_id=instance.get("id"),
                zone=instance.get("zone"),
                ignore_error=True,
            )

    def wait_for_instances(self, instances: list[Dict], instance_status: str):
        pass

    def delete_volumes(self, volumes: list[Dict]):
        for volume in volumes:
            self.delete_volume(volume.get("id", None), volume.get("zone", None))

    def delete_volume(self, volume_id: str, zone: str):
        cmd = """compute disks delete
            %s
            --zone=%s
            --quiet
            """ % (
            volume_id,  # disk name or id
            zone,
        )

        stdout_str, _, _ = self.run(cmd)

    def list_security_access(self) -> List[SecurityRecord]:
        res: List[SecurityRecord] = []

        cmd = """compute firewall-rules list """
        cmd += (
            " | jq '.[] | {name: .name, source_ranges: .sourceRanges, ports:"
            " .allowed[].ports}' | jq -s"
        )
        stdout_str, _, _ = self.run(cmd)
        info = json.loads(stdout_str)

        for a in info:
            for s in a.get("source_ranges"):  # ['192.240.149.2/32']
                ports = a.get("ports")
                ports = ["0-65535"] if ports is None else ports

                for p in ports:
                    # port can be: 22 or 0-65535
                    if "-" in p:
                        port_from, port_to = p.split("-")
                    else:
                        port_from = port_to = p
                    res.append(
                        SecurityRecord(
                            port_from=port_from,
                            port_to=port_to,
                            cidr=s,
                            name=a.get("name"),
                        )
                    )
        return res

    def authorize_access(self, rec: SecurityRecord):
        """Allow ip"""
        letters = string.ascii_lowercase
        service_name = f"xbench-" + "".join(random.choice(letters) for i in range(3))
        cmd = f"""compute firewall-rules create {service_name} --network={self.network} --allow tcp --source-ranges="{rec.cidr}" --description="Allow incoming traffic on TCP for {rec.cidr}" --direction=INGRESS"""
        stdout_str, _, _ = self.run(cmd)

    def revoke_access(self, rec: SecurityRecord):
        """Remove rule"""

        all_rules = self.list_security_access()
        for r in all_rules:
            if r.cidr == rec.cidr:
                cmd = f"""compute firewall-rules delete {r.name} --quiet"""
                stdout_str, _, _ = self.run(cmd)

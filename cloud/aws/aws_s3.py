# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov

# Implements AWS s3

import dataclasses
import json
import logging
import re
from enum import Enum
from typing import Dict, Optional

from cloud import VirtualMachine
from dacite import from_dict

from cloud.exceptions import CloudCliException, CloudStorageException


from ..abstract_storage import AbstractStorage
from ..virtual_storage import VirtualStorage
from .aws_cli import AwsCli
from .exceptions import AwsStorageException


class S3WaitEvent(str, Enum):
    ready = "volume-available"
    in_use = "volume-in-use"
    deleted = "volume-deleted"

    def __repr__(self):
        return self.value

class AwsS3(AbstractStorage[AwsCli, VirtualStorage]):
    @property
    def volume_id(self):
        if self.vs.id is None:
            raise AwsStorageException("volume is not ready!  It must first be created")
        return self.vs.id

    def as_dict(self):
        return dataclasses.asdict(self.vs)


    def create(self) -> VirtualStorage:
        """Create S3 bucket
        Implements https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/create-bucket.html
        s3api create-bucket --bucket my-bucket --acl private "
        """

        def canonize_bucket_name(name):
            return name.replace("_", "-").lower()

        def check_bucket_name(name):
            """Name requirements: https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html"""

            ip_rexexp = re.compile(r'^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)(\.(?!$)|$)){4}$')
            correct =  3 <= len(name) <= 63 and \
                not name.startswith('xn--') and \
                not name.endswith('-s3alias') and \
                name[0].isalnum() and name[-1].isalnum() and \
                not '..' in name and \
                not ip_rexexp.match(name)

            if not correct:
                raise AwsStorageException(f"bucket name for S3 storage is incorrect: {name}")

        bucket_name = canonize_bucket_name(self.cli.cluster_name)
        check_bucket_name(bucket_name)

        try:
            cmd = f"""s3api head-bucket --bucket {bucket_name}"""
            stdout_str, stderr_str, returncode = self.cli.run(cmd)
        except CloudCliException as e:
            # Error code 254 means it's OK, bucket does't exist
            if "error code 254" not in e.__str__():
                raise e

            cmd = f"""s3api create-bucket --bucket {bucket_name}
            --acl private --create-bucket-configuration LocationConstraint={self.cli.aws_region}"""

            stdout_str, stderr_str, returncode = self.cli.run(cmd)
            self.logger.debug(f"AWS S3 Bucket created: {stdout_str}")
        else:
            self.logger.warn(f"AWS Bucket {bucket_name} already exists")
            self.logger.debug(f"AWS returned {stdout_str}")

        self.vs.id = bucket_name
        return self.vs

    def describe(self) -> Dict:
        """Describe the storage"""
        raise CloudStorageException()

    def attach_storage(self, vm: VirtualMachine):
        """Attach volume to the instance"""
        pass

    def detach_storage(self, vm: VirtualMachine):
        """Detach Storage from instance"""
        pass

    def destroy(self):
        """Delete a S3 bucket
        Implements https://docs.aws.amazon.com/cli/latest/reference/s3api/delete-bucket.html

        aws s3api delete-bucket --bucket my-bucket

        """
        # TODO - All objects (including all object versions and delete markers) in the bucket must be deleted before the bucket itself can be deleted.
        # See also: https://docs.aws.amazon.com/cli/latest/reference/s3/rb.html

        cmd = f"s3api delete-bucket --bucket {self.volume_id}"
        stdout_str, stderr_str, returncode = self.cli.run(cmd)

# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


from ..exceptions import (
    CloudCliException,
    CloudComputeException,
    CloudException,
    CloudStorageException,
)


class AwsCloudException(CloudException):
    """AWS exception"""


class AwsAuroraCloudException(CloudException):
    """AWS exception"""


class AwsCliException(CloudCliException):
    """AWS exception"""


class AwsAuroraCliException(CloudCliException):
    """AWS exception"""


class AwsAuroraCliWaitException(Exception):
    """AWS Aurora specific exception"""


class AwsRdsCliException(CloudCliException):
    """AWS RDS exception"""


class AwsRdsCliWaitException(Exception):
    """AWS RDS specific exception"""


class AwsRdsComputeException(CloudComputeException):
    """Exception during RDS provisioning"""

class AwsEc2Exception(CloudComputeException):
    """Exception during EC2 provisioning"""


class AwsAuroraComputeException(CloudComputeException):
    """Exception during EC2 provisioning"""


class AwsStorageException(CloudStorageException):
    """Aws Storage Exception"""

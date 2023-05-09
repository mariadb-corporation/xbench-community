# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


from ..exceptions import CloudCliException, CloudException, CloudStorageException


class GcpCloudException(CloudException):
    """GCP exception"""


class GcpCliException(CloudCliException):
    """GCP CLI exception"""


class GcpStorageException(CloudStorageException):
    """GCP Storage Exception"""

class GcpAlloyDBCloudException(GcpCloudException):
    """GCP AlloyDB exception"""

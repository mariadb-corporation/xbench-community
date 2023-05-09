# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


class CloudException(Exception):
    """Cloud exception"""


class CloudCliException(CloudException):
    """Cloud CLI exception"""


class CloudComputeException(CloudException):
    """Cloud Compute exception"""


class CloudStorageException(CloudException):
    """Cloud Storage exception"""

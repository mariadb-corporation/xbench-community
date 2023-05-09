# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

from ..exceptions import CloudException


class SkySQLAPIException(CloudException):
    """base exception class"""


class SkySQLAPIClientException(SkySQLAPIException):
    """HTTP 400 to 499 errors from SkySQL"""


class SkySQLAPIServerException(SkySQLAPIException):
    """HTTP 500+ errors from SkySQL"""


class SkySQLServicePending(SkySQLAPIException):
    """service is not ready"""


class SkySQLServiceFailed(SkySQLAPIException):
    """service failed"""

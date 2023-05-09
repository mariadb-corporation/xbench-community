# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov
import requests

from ..exceptions import CloudException


class SkySQLAPIException(CloudException):
    """base exception class"""

    def __init__(self, *args, **kwargs):
        self.status_code: int = kwargs.get("status_code")
        self.message: str = kwargs.get("message")
        self.response: requests.Response = kwargs.get("response")
        super().__init__(f"HTTP error: {self.status_code} {self.message}")


class SkySQLAPIClientException(SkySQLAPIException):
    """HTTP 400 to 499 errors from SkySQL"""


class SkySQLAPIServerException(SkySQLAPIException):
    """HTTP 500+ errors from SkySQL"""


class SkySQLCLoudException(Exception):
    """"""

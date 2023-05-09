# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


from ..exceptions import BackendException


class XpandException(BackendException):
    """A Connection to database error occurred."""


class CheckQuorumException(XpandException):
    """Error checking quorum"""

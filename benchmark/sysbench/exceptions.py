# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

from ..exceptions import BenchmarkException


class SysbenchException(BenchmarkException):
    """sysbench exceptions"""


class SysbenchFatalException(BenchmarkException):
    """sysbench exceptions"""


class SysbenchOutputParseException(SysbenchException):
    """an Exception during parsing has happened"""

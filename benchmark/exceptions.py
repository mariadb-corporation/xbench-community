# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


class BenchmarkException(Exception):
    """Base Benchmark exception has happened"""

    def __init__(self, err_message=None):
        self.err_message = err_message

    def __str__(self):
        return "{err_message}".format(err_message=self.err_message)

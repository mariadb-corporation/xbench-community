# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov

import collections
import functools
from datetime import timezone, datetime
import datetime
import functools


def utc_timestamp():
    dt = datetime.datetime.now(timezone.utc)
    utc_time = dt.replace(tzinfo=timezone.utc)
    return utc_time.timestamp()


class Memoized:
    """Decorator. Caches a function's last value
    Function supposed to return dictionary of metrics
    """

    def __init__(self, cumsum_metrics: list = [], rate_metrics: list = []):
        """[summary]

        Args:
            cumsum_metrics (list, optional): Cumulative sum metrics. Defaults to None.
            rate_metrics (list, optional): Rate metrics, per sec. Defaults to None.
        """
        self.cache = (
            {}
        )  # An dict with {"timestamp": utc_now, "return_dict": <some values>}

        self.cumsum_metrics = cumsum_metrics
        self.rate_metrics = rate_metrics

    def __call__(self, func):
        """[summary]

        Args:
            func ([type]): [description]

        Returns:
            [dict]: empty dict for the first time, then result
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return_dict = {}
            utc_now = utc_timestamp()
            monitor_inst, curr_values = func(*args)
            if self.cache.get(monitor_inst) is not None:
                sec_diff = utc_now - self.cache.get(monitor_inst)["timestamp"]
                prev_values = self.cache.get(monitor_inst)["return_dict"]
                for k, v in curr_values.items():
                    if k in self.cumsum_metrics:
                        return_dict[k] = curr_values[k] - prev_values[k]
                    elif k in self.rate_metrics:
                        return_dict[k] = round(
                            float(curr_values[k] - prev_values[k]) / sec_diff, 1
                        )

                    else:
                        return_dict[k] = curr_values[k]
                return_dict["timestamp"] = utc_now
                # Update with current vales
                self.cache[monitor_inst] = {
                    "timestamp": utc_now,
                    "return_dict": curr_values,
                }
            else:
                self.cache[monitor_inst] = {
                    "timestamp": utc_now,
                    "return_dict": curr_values,
                }
            return return_dict

        return wrapper

    def __repr__(self):
        """Return the function's docstring."""
        return self.func.__doc__

    def __get__(self, obj, objtype):
        """Support instance methods."""
        print("hello")
        return functools.partial(self.__call__, obj)

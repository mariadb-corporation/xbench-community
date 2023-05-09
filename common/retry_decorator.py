#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 dvolkov

import datetime
import inspect
import logging
import random
import sys
import time
from functools import wraps

from .exceptions import RetryException, SigTermException


def iter_islast(iterable):
    """
    Generates pairs where the first element is an item from the iterable
    source and the second element is a boolean flag indicating if it is the
    last item in the sequence.
    """

    it = iter(iterable)
    prev = next(it)
    for item in it:
        yield prev, False
        prev = item
    yield prev, True


def constant_delay(delay, attempts):
    return [delay]*attempts

def backoff(delay=2, attempts=5):
    """
    Simple backoff algorithm
    :return: iterator with all delays requested
    """
    li = []
    for i in range(0, attempts):
        li.append(delay * 2 ** i)
    return li


def backoff_with_jitter(delay=3, attempts=10, cap=15):
    """
    Simple implementation from here: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

    :param delay: initial delay
    :param attempts: number of attempts
    :param cap: max single delay
    :return: iterator with all delays
    """
    li = []
    for i in range(0, attempts):
        li.append(random.randrange(0, min(cap, delay * 2 ** i)))
    return li


def retry(
    exceptions_to_check, exception_to_raise=RetryException, max_delay=300, delays=None
):
    """
    Retry using the decorated function. Delays is a generator, examples provided above.
    In addition to generator you could specify total time to wait.

    :param exceptions_to_check: the exception to check. may be a tuple of exceptions
    :param exception_to_raise: what exception to raise if function failed.
    :param max_delay: maximum time is secs to attempt to executed
    :param delays tuple or generator
    """

    def deco_retry(f):
        @wraps(f)
        def f_retry(self, *args, **kwargs):

            time_started = datetime.datetime.now()

            for i, (delay, last) in enumerate(iter_islast(delays)):
                try:
                    return f(self, *args, **kwargs)

                except exceptions_to_check as e:

                    now = datetime.datetime.now()
                    time_waited = int((now - time_started).total_seconds())

                    if time_waited > max_delay:
                        raise exception_to_raise(
                            "Max delay time %d seconds has reached for the function %s"
                            % (max_delay, f.__name__)
                        )

                    if not last:
                        msg = (
                            "Function: %s. Attempt %d failed with: %s. Retrying in %d seconds..."
                            % (f.__name__, i, str(e), delay)
                        )
                        if logging.getLogger().isEnabledFor(logging.DEBUG):
                            self.logger.error(msg)
                            self.logger.error("See failed function parameters below")
                            self.logger.error(args)
                            self.logger.error(kwargs)

                        time.sleep(delay)

                except SigTermException:  # Special case - I want to propagate this exception
                    raise
                except Exception as e:
                    msg = "Unexpected error: %s, %s" % (
                        e,
                        sys.exc_info(),
                    )  # I might need add more details: sys.exc_info()[0])
                    self.logger.error(msg)
                    raise exception_to_raise(msg)

            # return f(*args, **kwargs)  # Shouldn't I replace this with Retry exception?
            msg = f"Max attempts {i} reached for the function {f.__name__} with args {args}"
            # self.logger.error(msg)
            raise exception_to_raise(msg)

        return f_retry  # true decorator

    return deco_retry

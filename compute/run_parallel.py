# -*- coding: utf-8 -*-
# Copyright (C) 2022 dvolkov


import concurrent.futures
from multiprocessing import cpu_count
from typing import TypeVar

from compute.node import Node

SEP = "."
THREAD_POOL_MAX_WORKERS = cpu_count() - 1

P = TypeVar("P", "Node", dict)


def run_parallel(instances: list[P], fn_result, fn, /, *args, **kwargs):
    """Runs the `fn` routine in parallel for the `instances`.

    Args:
        instances (List): List of instances.
        fn_result (Function): A function reference to call on each completed Future
        fn (Function): A reference to a function that will be executed for each instance.
    """
    with concurrent.futures.ThreadPoolExecutor(THREAD_POOL_MAX_WORKERS) as executor:
        futures = [
            executor.submit(fn, **instance, **kwargs)
            if isinstance(instance, dict)
            else executor.submit(fn, instance)
            if isinstance(instance, Node)  # special case for start/stop functionality
            else executor.submit(fn, instance, *args)
            for instance in instances
        ]

    for future in concurrent.futures.as_completed(futures):
        fn_result(future.result())


def run_parallel_returning(instances: list[P], fn, /, *args, **kwargs) -> list:
    """Runs the `fn` routine in parallel for the `instances`.

    Args:
        instances (List): List of instances.
        fn (Function): A reference to a function that will be executed for each instance.
    """
    results = []
    run_parallel(instances, lambda x: results.append(x), fn, args, kwargs)
    return results

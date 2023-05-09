from multiprocessing import cpu_count
import os
from typing import Dict, TypeVar
from compute.cluster import Cluster
from compute.exceptions import ClusterException

from compute.node import Node
from lib.xbench_config import XbenchConfig, XbenchConfigException
from lib.yaml_config.yaml_config import YamlConfigException

from .exceptions import XbenchException

SEP = "."


def extender(base: Dict, extra: Dict):
    """Extend dictionary if key already exists
    {'workload': {'threads': '[1,2,3]', 'point_selects': '7'}}
    """
    for key in extra:
        # If the key represents a dict on both given dicts, merge the sub-dicts
        if key in base and isinstance(base[key], dict) and isinstance(extra[key], dict):
            extender(base[key], extra[key])
            continue

        # Otherwise, set the key on the base to be the value of the extra.
        base[key] = extra[key]
    return base


def parse_unknown(unknown: list) -> dict:
    """Manual parsing of unknown parameters

    Args:
        unknown (str):  Must be in the form of  --backend.network.public_ip=127.0.0.1

    Return: Dict {'database': {'external_ip':'127.0.0.1}}
    """
    try:
        extra_impl_params: dict = {}
        for arg in unknown:
            if arg.startswith(("-", "--")):
                # you can pass any arguments to add_argument
                k, v = arg.split("=")
                extra_impl_param = helper_splitter(k.replace("-", ""), v)
                extra_impl_params = extender(extra_impl_params, extra_impl_param)
            else:
                raise ValueError

        return extra_impl_params
    except ValueError:
        raise XbenchException(
            f"Additional parameter: {arg} must be in the form --component.param=value"
        )


def helper_splitter(string, val):
    if SEP not in string:
        return {string: internal_eval(val)}
    k, v = string.split(SEP, 1)
    return {k: helper_splitter(v, val)}


def internal_eval(s):
    try:
        value = eval(s)
        return value
    except (ValueError, NameError, SyntaxError):
        return s


def klass_instance_install(klass, nodes, name: str, **extras) -> tuple:
    """Helper function for running install and configure in parallel"""
    klass_instance = klass(nodes, **extras)
    result = klass_instance.install()  # For backend class it could be backendTarget
    return name, result


def klass_instance_configure(klass, nodes, **extras):
    """Helper function for running install and configure in parallel"""
    klass_instance = klass(nodes, **extras)
    klass_instance.configure()


def klass_instance_clean(klass, nodes):
    """Helper function for uninstalling in parallel"""
    klass_instance = klass(nodes)
    klass_instance.clean()

def get_default_cluster()->Cluster:
    clusters_dir = XbenchConfig().get_key("clusters_dir")
    cluster_name = XbenchConfig().cluster_name()

    try:
        cluster = Cluster(cluster_name=cluster_name)
        cluster_config_yaml = os.path.join(
            clusters_dir, f"{cluster_name}.yaml"
        )
        cluster.load_from_config(cluster_config_yaml)

        return cluster

    except (YamlConfigException, XbenchConfigException, ClusterException) as e:
        raise XbenchException(e)
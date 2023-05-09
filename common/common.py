import importlib
import json
import math
import os
import re
from collections.abc import Mapping
from random import randint
from typing import Any, Dict, Union

import requests
import yaml


def bytes2human(n, pretty=1):

    if pretty:
        symbols = ("K", "M", "G", "T", "P", "E", "Z", "Y")
        prefix = {}
        for i, s in enumerate(symbols):
            prefix[s] = 1 << (i + 1) * 10
        for s in reversed(symbols):
            if n >= prefix[s]:
                value = float(n) / prefix[s]
                return "%.1f%s" % (value, s)
        return "%sB" % n
    else:
        return n


def simple_dict_items(d: Dict) -> Dict:
    """Return only simple elements of Dict, skipping Mappings

    Args:
        d (Dict): [description]

    Returns:
        Dict: [description]
    """
    ret = {}
    for k, v in d.items():
        if not isinstance(v, Mapping):
            ret[k] = v

    return ret


def save_dict_merge(dict1: Dict, dict2: Dict) -> Dict:
    """Merge two dict

    Args:
        dict1 (Dict): [description]
        dict2 (Dict): [description]

    Returns:
        Dict: [description]
    """
    if dict2 is None:
        dict2 = {}
    dict_merge = lambda a, b: a.update(b) or a
    ret = dict_merge(dict1, dict2)
    return ret


def recursive_items(d: Dict):
    """Return all keys, values from nested dict

    Args:
        d (Dict): [description]

    Yields:
        [type]: [description]
    """
    for key, value in d.items():
        if type(value) is dict:
            yield from recursive_items(value)
        else:
            yield (key, value)


def json_pretty_please(d: Any) -> str:
    """
    returns pretty printed json
    """
    return f"""{json.dumps(d, indent=4, separators=(", ", ": "))}\n"""


def mkdir(directory):
    """
    General mkdir helper
    :param directory:
    :return:
    """

    if not os.path.exists(directory):
        os.makedirs(directory)


def get_class_from_klass(klass: str) -> Any:
    """Return real Python class from str in the form drivers.Sysbench

    Args:
        klass (str): string with valid module.class_name

    Returns:
        _type_: _description_
    """
    module_name, klass_name = klass.rsplit(".", 1)
    module = importlib.import_module(module_name)
    klass = getattr(module, klass_name)
    return klass


def clean_cmd(cmd: Union[list, str]) -> str:
    # Multiline cmd should become a list
    if isinstance(cmd, str):
        cmd = [y for y in (x.strip() for x in cmd.splitlines()) if y]

    if isinstance(cmd, list):
        cmd = "\n".join(cmd)

    return cmd


def local_ip_addr() -> str:
    res = requests.get("https://ifconfig.me")
    return res.text


def validate_name_rfc1035(name: str) -> bool:
    """Validate (domain) name according https://tools.ietf.org/html/rfc1035

    GCP, SkySQL requires virtual machine name follows rfc.

    Returns:
        bool: True if name is valid
    """
    # the pattern is more restrictive (no uppercase) than RFC1035 becaue of GCP:
    # https://cloud.google.com/compute/docs/naming-resources#resource-name-format
    pattern = r"^[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?$"
    rx = re.compile(pattern)
    regex_pass = rx.match(name)
    return False if not regex_pass else True


def round_down_to_even(f):
    f = int(math.floor(f))
    return f - 1 if f % 2 == 1 else f


def save_dict_as_yaml(file_name: str, d: dict):
    """Save dictionary in human readable format

    Args:
        file_name (str): full path
        d (dict): dictionary to save
    """
    with open(file_name, "w") as yaml_file:
        yaml.dump(d, yaml_file, default_flow_style=False)


def shuffle_list_inplace(l: list) -> list:
    list_length = len(l)
    if list_length > 0:
        for i in range(list_length):
            j = randint(0, list_length - 1)
            l[i], l[j] = l[j], l[i]
    return l

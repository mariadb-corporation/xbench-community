import concurrent.futures
import dataclasses
import logging
from dataclasses import asdict

from cloud import VirtualMachine
from cloud.aws import AwsCli, AwsEbs, AwsEc2, AwsEc2Exception, AwsStorageException
from cloud.virtual_storage import VirtualStorage
from compute import Node
from xbench import Xbench
from dacite import from_dict

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

xb = Xbench("cl1")
cloud_config = xb.load_cloud("aws")

region_config = cloud_config.get("us-west-2-PerformanceEngineering", {})

cli = AwsCli(
    cluster_name="cl1",
    **region_config,
)

import os
from os.path import expanduser

home = expanduser("~")


def launch_instance():
    instance_params = {
        "env": "env_0",
        "provisioned": False,
        "klass_config_label": "bla",
        "zone": "us-west-2a",
        "instance_type": "t2.micro",
        "os_type": "CentOS7",
        "name": "driver",
        "role": "driver",
        "network": {"cloud_type": "public_cloud"},
        "klass": "Sysbench",
        "key_file": os.path.join(home, ".xbench/pem/MariaDBPerformance.pem"),
        "managed": True,
    }
    ec2 = AwsEc2(cli=cli, **instance_params)
    vm = ec2.create()

    print(asdict(vm))

    storage_params = {
        "iops": 100,
        "type": "io2",
        "size": 100,
        "zone": "us-west-2a",
        "device": "/dev/sdf",
    }
    storage = from_dict(
        data_class=VirtualStorage,
        data=storage_params,
    )
    ebs = AwsEbs(cli, storage)

    virtual_storage = ebs.create()
    print(ebs.describe())
    ebs.attach_storage(vm)
    vm.storage = virtual_storage

    # Let's initiate VMs, Storages, and Node itself
    n = Node(vm)
    # n.configure()  # Configure Node
    return vm


def terminate_instance(vm: VirtualMachine):
    ec2 = AwsEc2.from_vm(cli, vm)
    ec2.destroy()
    if vm.storage is not None:
        ebs = AwsEbs(cli, vm.storage)
        ebs.destroy()
    return vm.id


with concurrent.futures.ThreadPoolExecutor() as executor:
    futures = []
    for i in range(1):
        futures.append(executor.submit(launch_instance))

    all_vms = []
    for future in concurrent.futures.as_completed(futures):
        try:
            print("######## RESULT ############")
            print(future.result())
            all_vms.append(future.result())
            print("######## END RESULT ############")

        except (AwsEc2Exception, AwsStorageException) as e:
            print(f"Something has happened {e}")

    futures = []
    for vm in all_vms:
        futures.append(executor.submit(terminate_instance, vm))

    for future in concurrent.futures.as_completed(futures):
        try:
            print("######## RESULT ############")
            print(future.result())
            print("######## END RESULT ############")

        except (AwsEc2Exception, AwsStorageException) as e:
            print(f"Something has happened {e}")

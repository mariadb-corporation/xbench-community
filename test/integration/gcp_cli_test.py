import pytest
import dataclasses
from typing import Dict
from cloud.compute_factory import ComputeFactory
from cloud.gcp import GcpCli
from cloud.gcp.gcp_nas_storage import GcpNasVirtualStorage
from cloud.gcp.exceptions import GcpCloudException, GcpStorageException
from cloud.gcp.gcp_cloud import GcpCloud
from cloud.cloud_factory import CloudFactory
from cloud.storage_factory import StorageFactory
from cloud.virtual_storage import VirtualStorage
from common.common import get_class_from_klass, simple_dict_items
from compute import Node
from xbench import Xbench
from dacite import from_dict


@pytest.fixture
def cli():
    xb = Xbench("cl1")
    cloud_config = xb.load_cloud("gcp")

    region_config = cloud_config.get("us-central1-clustrix", None)

    cli = GcpCli(
        cluster_name="cl1",
        **region_config,
    )

    yield cli

def test_gcp_cli_construction(cli: GcpCli):
    pytest.assume(isinstance(cli, GcpCli))

def test_describe_availability_zones(cli: GcpCli):
    cli.describe_availability_zones()

def test_gcp_cloud_construction():
    xb = Xbench("cl1")
    
    cloud_type = "gcp"
    cloud_config = xb.load_cloud(cloud_type)
    impl_params = xb.load_impl("itest_gcp_shared_storage")
    common_impl_keys = simple_dict_items(impl_params)
    region = common_impl_keys.get("region", "")
    region_config = cloud_config.get(region, None)

    cloud = CloudFactory().create_cloud_from_str(cloud_type, xb.cluster_name, **region_config)

    # Backwards-compatibility test
    cloud_klass_type = cloud_config.get("klass", "")
    cloud_klass = get_class_from_klass(cloud_klass_type)
    cloud1 = cloud_klass(
        cluster_name=xb.cluster_name, **region_config
    )

    pytest.assume(isinstance(cloud, GcpCloud))
    pytest.assume(isinstance(cloud1, GcpCloud))

def test_gcp_cloud_instances():
    xb = Xbench("cl1")
    
    impl = "itest_gcp_shared_storage"
    env = "gcp"
    cloud_config = xb.load_cloud(env)
    impl_params = xb.load_impl(impl)
    common_impl_keys = simple_dict_items(impl_params)
    region = common_impl_keys.get("region", "")
    region_config = cloud_config.get(region, None)
    
    cloud = CloudFactory().create_cloud_from_str(env, xb.cluster_name, **region_config)
    pytest.assume(isinstance(cloud, GcpCloud))
    
    nodes = []
    for k, v in impl_params.items():  # 'driver1': {}
        if isinstance(v, Dict) and k != 'shared_storage':
            component_params = (
                common_impl_keys
                | xb.impl_yaml.get_key(
                    root=impl, leaf=k, use_defaults=True
                )  # I need to apply defaults to nested level
                | {"cluster_name": xb.cluster_name}
            )
            component_params["env"] = env
            component_params["role"] = k
            component = f"{k}"
            for i in range(
                int(component_params.get("count"))
            ):  # int here is required in case param comes from command line as str
                name = f"{component}-{i}"  # new name for the component
                component_params["name"] = name  # cl1-driver0
                n = cloud.launch_instance(**component_params)
                pytest.assume(isinstance(n, Node))
                nodes.append(n) if n != None else None
    pytest.assume(len(nodes) > 0)

    instances = cloud.cli.describe_instances_by_tag()
    
    # primitive test
    pytest.assume(len(instances) == len(nodes))
    # deep test
    arr_node_ids = list(map(lambda n: n.vm.id, nodes))
    arr_inst_ids = list(map(lambda n: n.get("id"), instances))
    pytest.assume(sorted(arr_node_ids) == sorted(arr_inst_ids))

    cloud.terminate_instances(nodes, terminate_storage=True)
    # validate the instances are gone
    no_instances = cloud.cli.describe_instances_by_tag()    
    pytest.assume(len(no_instances) == 0)


def test_compute(cli: GcpCli):
    instance_params = {
        "env": "env_0",
        "role": "driver",
        "name": "driver_0",
        "klass": "driver.BaseDriver",
        "zone": "us-west3-a",
        "klass_config_label": "sysbench",
        "os_type": "Rocky8",
        "managed": False,
        "provisioned": False,
        "instance_name": "test-instance-001",
        "zone_id": "us-west3-a",
        "instance_type": "n1-standard-4",
        "image_project_id": "centos-cloud",
        "image_family_id": "centos-7",
        "region": "us-central1-clustrix"
    }

    gc_1 = ComputeFactory().create_compute(cli, **instance_params)
    vm = gc_1.create()
    print((dataclasses.asdict(vm)))
    pytest.assume(len(vm.id) > 0)

    gc_2 = ComputeFactory().create_compute_from_vm(cli, vm)

    desc = gc_2.describe()
    pytest.assume(desc.get("id") == vm.id)

    desc_2_long = cli.describe_instances_by_tag(False)
    pytest.assume(desc_2_long[0].get("id") == vm.id)
    desc_2_short = cli.describe_instances_by_tag()
    pytest.assume(desc_2_short[0].get("id") == vm.id)

    gc_2.stop()
    gc_2.start()
    # gc_2.reboot()
    gc_2.destroy()

    with pytest.raises(GcpCloudException) as err:
        gc_2.describe()
    pytest.assume("does not exist" in str(err))

def test_gcp_nas_storage(cli: GcpCli):
    nas_instance_params = {
        "type": "filestore",
        "tier": "BASIC_HDD",
        "size": 10,
        "name": "vol1",
        "zone": "us-central1-a"
    }
    nas_storage = from_dict(data_class=GcpNasVirtualStorage, data=nas_instance_params)
    storage = StorageFactory().create_storage(cli, nas_storage)
    vs = storage.create()
    pytest.assume(vs.id != "")

    vs1 = storage.describe()
    pytest.assume(vs.id == vs1.get("name"))

    storage.destroy()
    pytest.assume(vs.id == "")

    with pytest.raises(GcpStorageException) as err:
        storage.describe()
    pytest.assume("does not exist" in str(err))

def test_gcp_storage(cli: GcpCli):
    instance_params = {
        "size": 200,
        "type": "pd-ssd",
        "device": "sdb",
        "name": "testdisk1",
        "zone": "us-central1-a"
    }
    virtual_storage = from_dict(data_class=VirtualStorage, data=instance_params)
    storage = StorageFactory().create_storage(cli, virtual_storage)
    vs = storage.create()
    pytest.assume(vs.id != "")

    vs1 = storage.describe()
    pytest.assume(vs.id == vs1.get("id"))

    storage.destroy()
    pytest.assume(vs.id == "")

    with pytest.raises(GcpStorageException) as err:
        storage.describe()
    pytest.assume("does not exist" in str(err))

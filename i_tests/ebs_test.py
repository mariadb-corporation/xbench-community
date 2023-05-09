import dataclasses
import logging

from cloud.aws import AwsCli, AwsEbs
from cloud.virtual_storage import VirtualStorage
from xbench import Xbench
from dacite import from_dict

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

xb = Xbench("cl1")
cloud_config = xb.load_cloud("aws")

region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)

cli = AwsCli(
    cluster_name="cl1",
    **region_config,
)

storage_params = {
    "iops": 111,
    "type": "io2",
    "size": 120,
    "zone": "us-west-2a",
    "device": "/dev/sdf",
}

storage = from_dict(
    data_class=VirtualStorage,
    data=storage_params,
)
ebs = AwsEbs(cli, storage)

volume = ebs.create()
print(dataclasses.asdict(volume))
print(ebs.describe())
print(ebs.as_dict())
ebs.destroy()

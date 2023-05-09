import dataclasses
import logging

from cloud.aws import AwsS3, AwsCli
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
    cluster_name="columnstore-test-data",
    **region_config,
)

storage_params = {
    "type": "s3",
}
storage = from_dict(
    data_class=VirtualStorage,
    data=storage_params,
)
s3 = AwsS3(cli, storage)
vm = s3.create()
print((dataclasses.asdict(vm)))
s3.destroy()

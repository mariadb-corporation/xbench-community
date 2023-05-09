import logging

import yaml

from cloud.skysql import SkySQLCloud
from xbench import Xbench

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

xb = Xbench("cl1")
cloud_config = xb.load_cloud("skysql")

region_config = cloud_config.get("aws-us-west-2", None)

s = SkySQLCloud(cluster_name="gdh", **region_config)

i = xb.load_impl("skysql_test")
print(i)

with open("./conf/impl.yaml", "r") as f:
    y = yaml.safe_load(f)
    backend = y["skysql_test"]
    print(backend)

my_db: list["Node"] = s.launch_instances([backend])
print(my_db)

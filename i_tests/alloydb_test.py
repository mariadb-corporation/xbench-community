import dataclasses
import logging

from cloud.aws import AwsAuroraCli, AwsAuroraCloud, AwsAuroraCompute
from xbench import Xbench
from backend import AlloyDB, AlloyDBException

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

xb = Xbench("cl1")
cloud_config = xb.load_cloud("gcp")

region_config = cloud_config.get("us-central1-clustrix", None)

node = ?
alloydb = AlloyDB(node)
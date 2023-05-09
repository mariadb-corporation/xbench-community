import dataclasses
import logging

from cloud.aws import AwsAuroraCli, AwsAuroraCloud, AwsAuroraCompute
from xbench import Xbench

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level="DEBUG",
)

xb = Xbench("cl1")
cloud_config = xb.load_cloud("aws_aurora")

region_config = cloud_config.get("us-west-2-Clustrix", None)

cli = AwsAuroraCli(
    cluster_name="dsv_cluster",
    **region_config,
)

instance_params = {
    "count": 1,
    "zone": "us-west-2a",
    "instance_type": "db.r5.2xlarge",
    "os_type": "CentOS7",
    "name": "ec2_test",
    "role": "driver",
    "network": {"cloud_type": "public_cloud"},
    "klass": "Sysbench",
    "key_file": "ENV['HOME']/.xbench/pem/MariaDBPerformance.pem",
    "managed": False,
    "provisioned": True,
    "klass_config_label": "latest",
}

ac = AwsAuroraCompute(cli=cli, **instance_params)
try:
    ac.create_db_cluster()
    ac.wait_for_db_cluster()
    ac.create_db_instance()
    ac.wait_for_db_instance()
except Exception as e:
    print(e)
    ac.delete_db_instance()
    ac.wait_for_db_instance(status="deleting")
    ac.delete_db_cluster()
    ac.wait_for_db_cluster(status="deleting")

# vm = ec2_1.create()
# print((dataclasses.asdict(vm)))

# ec2_2 = AwsEc2.from_vm(cli, vm)

# ec2_2.stop()
# ec2_2.start()
# ec2_2.reboot()
# ec2_2.destroy()

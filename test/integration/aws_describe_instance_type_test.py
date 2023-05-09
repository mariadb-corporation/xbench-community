import pytest
from cloud.aws import AwsCli, AwsCliException
from xbench import Xbench


@pytest.fixture
def cli():
    xb = Xbench("cl1")
    cloud_config = xb.load_cloud("aws")

    region_config = cloud_config.get("us-west-2-PerformanceEngineering", None)

    cli = AwsCli(
        cluster_name="cl1",
        **region_config,
    )

    yield cli


@pytest.mark.order(1)
def test_non_existing_instance_type(cli):
    with pytest.raises(AwsCliException):
        cli.describe_instance_type("gcp_n2")


@pytest.mark.order(2)
def test_existing_nvme_instance_type(cli):
    info = cli.describe_instance_type("c5d.4xlarge")  # Instance with  local SSD
    print(info)
    pytest.assume(len(info.get("local_nvme_disks")) == 1)
    pytest.assume(info.get("local_nvme") is True)


@pytest.mark.order(3)
def test_existing_nvme_instance_type_2_ssd(cli):
    info = cli.describe_instance_type("i3en.2xlarge")  # Instance with  local SSD
    print(info)
    pytest.assume(info.get("local_nvme_disks")[0].get("Count") == 2)
    pytest.assume(info.get("local_nvme") is True)


@pytest.mark.order(4)
def test_existing_non_nvme_instance_type(cli):
    info = cli.describe_instance_type("m5.4xlarge")  # No local SSD
    print(info)
    pytest.assume(info.get("nvme_support") == "required")
    pytest.assume(info.get("local_nvme") is False)

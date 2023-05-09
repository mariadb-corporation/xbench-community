from typing import List, Optional

from cloud.abstract_cli import SecurityRecord
from cloud.cli_factory import CliFactory
from xbench import XbenchException

from .xbench import Xbench

SecurityPorts: List[tuple] = [(0, 65535)]


class SecurityCommands(Xbench):
    """Main class to de-provision cluster in the cloud"""

    def __init__(
        self,
        cloud: str,
        cloud_region: str,
        dry_run: bool = False,
    ):
        if cloud is None or cloud_region is None:
            raise XbenchException("You have to specify cloud and region")
        cluster_name = "not existing one"
        super(SecurityCommands, self).__init__(cluster_name, dry_run)
        cloud_config = self.load_cloud(cloud)
        region_config = cloud_config.get(cloud_region)
        if region_config is None:
            raise XbenchException(
                f"Region {cloud_region} does not exists in the cloud {cloud}"
            )

        self.cli = CliFactory().create_cli_from_str(
            cloud, cluster_name, **region_config
        )

    def list(self, ip_address: Optional[str]):

        security_records = self.cli.list_security_access()
        # TODO add filter by ip
        for s in security_records:
            print(s)

    def addip(self, ip_address: str):
        """Add ip address to the security list"""
        for pair in SecurityPorts:
            s = SecurityRecord(pair[0], pair[1], ip_address)
            self.cli.authorize_access(s)
        self.logger.info(f"IP {ip_address} was successfully authorized")

    def delip(self, ip_address: str):
        """Add ip address to the security list"""
        for pair in SecurityPorts:
            s = SecurityRecord(pair[0], pair[1], ip_address)
            self.cli.revoke_access(s)
        self.logger.info(f"IP {ip_address} was successfully removed")

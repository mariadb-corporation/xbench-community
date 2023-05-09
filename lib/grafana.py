import json
import logging
import sys
from datetime import datetime, timezone

from grafana_client import GrafanaApi

SNAPSHOT_EXPIRATION = 31536000  # 1yr retention
# product to dashboard UID mapping
product_dashboards = {
    "xpand": ["xpandstats", "nodeexporter"],
    "mariadb": [
        "mysqlexporterquickstartanddashboard",
        "mysqlinnodbmetrics",
        "nodeexporter",
    ],
    "mysql": [
        "mysqlexporterquickstartanddashboard",
        "mysqlinnodbmetrics",
        "nodeexporter",
    ],
    "aurora-mysql": ["nodeexporter"],
    "aurora-postgres": ["nodeexporter"],
    "postgres": ["postgresqldatabase", "nodeexporter"],
    "xgres": ["nodeexporter"],
}


class Grafana:
    def __init__(self, auth, host, port=3000, verify=False):
        self.logger = logging.getLogger(__name__)
        self.host_url = f"{host}:{port}"
        self.api = GrafanaApi(auth, host=host, port=port, verify=verify)
        self.api.url = self.host_url  # GrafanaAPI never sets this
        self.logger.debug(self.api.connect())

    def update_var_template(self, dashboard, var_name, var_value):
        for index, variable in enumerate(dashboard["templating"]["list"]):
            if variable["name"] == var_name:
                dashboard["templating"]["list"][index]["current"] = {
                    "selected": True,
                    "text": var_value,
                    "value": var_value,
                }
                dashboard["templating"]["list"][index]["options"] = [
                    dashboard["templating"]["list"][index]["current"]
                ]
                dashboard["templating"]["list"][index]["type"] = "custom"
                dashboard["templating"]["list"][index]["query"] = var_value

    def create_snapshot(self, cluster, time_from, time_to):
        snapshot_urls = []
        # Convert to UTC in case method was called with local TZ timestamps
        utc_from = datetime.strptime(time_from, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        utc_to = datetime.strptime(time_to, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        iso_from = utc_from.isoformat()
        iso_to = utc_to.isoformat()
        from_string = utc_from.strftime("%y%m%d.%H%M%S")
        to_string = utc_to.strftime("%y%m%d.%H%M%S")
        if cluster.bt.product in product_dashboards.keys():
            for dashboard_name in product_dashboards[cluster.bt.product]:
                dashboard = self.api.dashboard.get_dashboard(dashboard_name)[
                    "dashboard"
                ]
                dashboard["time"] = {
                    "from": iso_from,
                    "raw": {"from": iso_from, "to": iso_to},
                    "to": iso_to,
                }
                dashboard["refresh"] = ""
                self.update_var_template(dashboard, "cluster", cluster.cluster_name)
                if dashboard_name == "nodeexporter":
                    node_names = [
                        group[0].name.split(",")[0]  # Get first node in each group
                        for group in cluster.level_order_group_cluster_members()
                    ]
                    for node_name in node_names:
                        if cluster.members.get(node_name).vm.managed:
                            self.update_var_template(dashboard, "node", node_name)
                            snapshot_name = f"{cluster.cluster_name}_{dashboard_name}_{node_name}_{from_string}-{to_string}"
                            snapshot = self.api.snapshots.create_new_snapshot(
                                dashboard,
                                name=snapshot_name,
                                expires=SNAPSHOT_EXPIRATION,
                                key=snapshot_name,
                                delete_key=snapshot_name,
                            )
                            snapshot_url = snapshot["url"]
                            snapshot_url = snapshot_url.replace(
                                "localhost:3000", self.host_url
                            )
                            snapshot_urls.append(snapshot_url)
                else:
                    # Assuming other backend dashboards if not nodeexporter
                    node = cluster.get_backend_nodes()[0].vm
                    if node.managed:
                        self.update_var_template(dashboard, "node", node.name)
                        snapshot_name = f"{cluster.cluster_name}_{dashboard_name}_{from_string}-{to_string}"
                        snapshot = self.api.snapshots.create_new_snapshot(
                            dashboard,
                            name=snapshot_name,
                            expires=SNAPSHOT_EXPIRATION,
                            key=snapshot_name,
                            delete_key=snapshot_name,
                        )
                        snapshot_url = snapshot["url"]
                        snapshot_url = snapshot_url.replace(
                            "localhost:3000", self.host_url
                        )
                        snapshot_urls.append(snapshot_url)
        else:
            self.logger.warning(f"No dashboards exist for {cluster.bt.product}")
        return snapshot_urls

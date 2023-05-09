from enum import Enum


class SkySQLDeployment(str, Enum):
    xpand = "Distributed Transactions"
    standalone_mariadb = "Single Node Transactions"
    replicated_mariadb = "Replicated Transactions"
    columnstore = "Multi-Node Analytics"
    standalone_columnstore = "Single Node Analytics"

    def __repr__(self):
        return self.value


SKYSQL_DB_IS_UP_AND_RUNNING = "Installed"
SKYSQL_DB_IS_INSTALLING = "Pending Install"
SKYSQL_DB_IS_BUSY = ("In Maintenance", "Pending Repair", "Retired")


SKYSQL_SERVICES_DEPLOYMENT_MAP: dict[str, SkySQLDeployment] = {
    "xpand": SkySQLDeployment.xpand,
    "mariadb": SkySQLDeployment.standalone_mariadb,
    "mariadb_replicated": SkySQLDeployment.replicated_mariadb,
    "columnstore": SkySQLDeployment.standalone_columnstore,
    "columnstore_replicated": SkySQLDeployment.columnstore,
}

SKYSQL_DEPLOY_2_RELEASE_MAP: dict[str, str] = {
    "xpand": "xpand",
    "mariadb": "enterprise server"
}

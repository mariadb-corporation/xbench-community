from enum import Enum


class BackendProduct(str, Enum):
    mariadb = "mariadb"
    mysql = "mysql"
    aurora_mysql = "aurora-mysql"
    aurora_postgres = "aurora-postgres"
    alloydb = "postgres"
    xpand = "xpand"
    postgres = "postgres"
    tidb = "tidb"
    xgres = "xgres"

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return str(self.value)

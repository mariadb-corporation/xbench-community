from enum import Enum


class BackendDialect(str, Enum):
    pgsql = "pgsql"
    mysql = "mysql"

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return str(self.value)

from dataclasses import asdict, dataclass, field
from typing import Mapping

from .backend_dialect import BackendDialect
from .backend_product import BackendProduct

from .backend_dialect import BackendDialect
from .backend_product import BackendProduct


@dataclass
class BackendTarget:
    """Represents a backend target as proxy or backend"""

    host: str  # = "127.0.0.1"  # or could be multiple ip addresess
    user: str  # = "sysbench"
    password: str  # = "sysbench"
    database: str  # = "sysbench", This is the database schema
    port: int  # = 5001
    ssl: dict = field(default_factory=dict)
    dialect: BackendDialect = field(default=BackendDialect.mysql)
    product: BackendProduct = field(default=BackendProduct.mariadb)
    connect_timeout: int = 5
    read_timeout: int = 5

    def as_dict(self):
        return {
            name: value
            if isinstance(value, int) or isinstance(value, dict)
            else str(value)
            for name, value in vars(self).items()
        }

    def get_backup_type(self):
        backup_map = {
            "xpand": "xpand",
            "mariadb": "mariabackup",
            "aurora-mysql": "mysqldump",
            "aurora-postgres": "pg_dump",
            "postgres": "pg_dump",
        }
        try:
            backup_type = backup_map[self.product]
        except KeyError:
            backup_type = None
        return backup_type

    def update(self, new: Mapping):
        for key, value in new.items():
            if hasattr(self, key):
                setattr(self, key, value)

from dataclasses import dataclass

from compute import BackendTarget


@dataclass
class SkySQLConfig:
    db: BackendTarget
    globals: dict

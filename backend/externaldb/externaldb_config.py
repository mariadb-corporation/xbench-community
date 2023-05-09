from dataclasses import dataclass
from backend.base_backend import BackendConfig



@dataclass
class ExternalDBConfig(BackendConfig):
    """Represents Xpand Config"""

    globals: dict

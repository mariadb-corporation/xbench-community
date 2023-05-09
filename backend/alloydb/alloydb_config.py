from dataclasses import dataclass
from backend.base_backend import BackendConfig

@dataclass
class AlloyDBConfig(BackendConfig):
    """Represents Xpand Config"""

    foo: str

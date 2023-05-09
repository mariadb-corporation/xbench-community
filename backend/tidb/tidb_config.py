from dataclasses import dataclass
from typing import Optional


from ..base_backend import BackendConfig


@dataclass
class TiDBConfig(BackendConfig):
    """Represents Xpand Config"""

    globals: Optional[dict]

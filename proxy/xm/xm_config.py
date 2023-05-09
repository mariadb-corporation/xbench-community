from dataclasses import dataclass

from compute import BackendTarget

@dataclass
class XmConfig:
    """Represents Xm Config"""

    git_token: str
    commit: str
    mode: str
    skip: int

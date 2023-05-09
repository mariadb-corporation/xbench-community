from dataclasses import dataclass


@dataclass
class MetricsServerConfig:
    data_dir: str
    grafana_user: str
    grafana_password: str

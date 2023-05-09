from common import json_pretty_please


class MetricsTarget:
    """
    Defines the prometheus consumable metrics scraping target file and filenames
    """

    def __init__(self, service_name: str, labels: dict, hostname: str, port: int):
        self.service_name = service_name # node
        self.labels = labels
        self.hostname = hostname
        self.port = port

    def target(self) -> str:
        t = [
            {
                "labels": self.labels,
                "targets": [
                    f"{self.hostname}:{self.port}",
                ],
            }
        ]

        return json_pretty_please(t)

    def target_name(self) -> str:
        return f"{self.labels.get('cluster_name')}-{self.labels.get('name')}-{self.service_name}-exporter.json"

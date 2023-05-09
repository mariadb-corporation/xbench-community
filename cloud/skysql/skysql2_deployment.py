from collections import defaultdict

XBENCH_2_SKY_MAP: dict[str, dict] = {
    "xpand": {
        "product_name": "xpand",
        "topology": "xpand-direct",
        "service_type": "transactional",
    },
    "mariadb": {
        "product_name": "server",
        "topology": "standalone",
        "service_type": "transactional",
    },
    "xgres": {
        "product_name": "xgres",
        "topology": "xpand-pg",
        "service_type": "transactional",
    },
}

XBENCH_2_SKY_ARCH_MAP = defaultdict(lambda: "amd64")
XBENCH_2_SKY_ARCH_MAP["aarch64"] = "arm64"

import asyncio
import concurrent.futures
import logging
from multiprocessing import cpu_count
from typing import Dict, List, Optional, cast

from cloud import VirtualMachine, VirtualStorage
from cloud.abstract_storage import AbstractStorage
from cloud.cloud_types import CloudTypeEnum
from cloud.exceptions import CloudException
from cloud.storage_factory import StorageFactory
from compute import Node
from metrics import MetricsServer

from ..abstract_cloud import AbstractCloud
from .exceptions import GcpCloudException
from .gcp_cli import GcpCli
from .gcp_compute import GcpCompute


class GcpCloud(AbstractCloud[GcpCli, GcpCompute]):
    def cloud_type(self) -> CloudTypeEnum:
        return CloudTypeEnum.GCP

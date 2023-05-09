# -*- coding: utf-8 -*-
# Copyright (C) 2021 dvolkov


from mariadb_client import MariaDbClient, MariaDbClientException, NoDataFoundException
from mysql_client.mysql_client import MySqlClient
from .memoize import Memoized


class XpandMonitor(MySqlClient):
    def __init__(self, name, **kwargs):
        super(XpandMonitor, self).__init__(**kwargs)
        self.name = name

        self.gather_list = [self.system_stats, self.seconds_slave_behind]
        self.connect()
        self.gather()

    def gather(self):
        for statfunction in self.gather_list:
            statfunction()

    @Memoized()
    def seconds_slave_behind(self):
        try:
            query = "select Seconds_Behind_Master as slv_sec_behind, Last_Error as last_error from system.mysql_slave_status"
            return (self.name, self.select_one_row(query))
        except NoDataFoundException as e:
            return (self.name, {"slv_sec_behind": 0, "last_error": "NA"})

    @Memoized(rate_metrics=["qps", "tps"])
    def system_stats(self):
        query = (
            "select sum(case when name = 'statements_total' then value else 0 end)"
            "as qps, sum(case when name = 'transactions_total' then value else 0 end) as tps from system.global_stats"
        )
        system_stats = self.select_one_row(query)
        return (self.name, system_stats)

    @Memoized(cumsum_metrics=["cpu_busy", "cpu_total"])
    def cpu_utilization(self):
        query = (
            "select sum(user+nice+system+irq+softirq+steal_time+guest) as cpu_busy,"
            "sum(user+nice+system+iowait+irq+softirq+steal_time+guest+idle) as cpu_total"
            " from system.proc_cpu"
        )

        return (self.name, self.select_one_row(query))

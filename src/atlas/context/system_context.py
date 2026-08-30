import time

import psutil

from atlas.context.models import SystemContext


class SystemContextProvider:

    def collect(self) -> SystemContext:

        memory = psutil.virtual_memory()

        network = psutil.net_io_counters()

        boot_time = psutil.boot_time()

        uptime_seconds = max(
            0.0,
            time.time() - boot_time,
        )

        return SystemContext(
            cpu_percent=psutil.cpu_percent(
                interval=None
            ),

            memory_percent=memory.percent,

            memory_available_gb=round(
                memory.available / (1024 ** 3),
                2,
            ),

            uptime_seconds=round(
                uptime_seconds,
                1,
            ),

            network_bytes_sent=network.bytes_sent,

            network_bytes_received=network.bytes_recv,
        )
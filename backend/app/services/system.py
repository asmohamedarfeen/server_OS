import os
import platform
import shutil
import time
from pathlib import Path
import psutil
from datetime import datetime, timezone

_last_net = psutil.net_io_counters()
_last_net_at = time.monotonic()

def server_metrics():
    global _last_net, _last_net_at
    now = time.monotonic()
    net = psutil.net_io_counters()
    elapsed = max(now - _last_net_at, .1)
    net_rate = {"rx_bytes_sec": max(net.bytes_recv - _last_net.bytes_recv, 0) / elapsed, "tx_bytes_sec": max(net.bytes_sent - _last_net.bytes_sent, 0) / elapsed}
    _last_net, _last_net_at = net, now
    mem, disk, boot = psutil.virtual_memory(), shutil.disk_usage("/host" if os.path.exists("/host/proc") else "/"), psutil.boot_time()
    temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
    readings = [x.current for group in temps.values() for x in group if x.current is not None]
    return {"hostname": platform.node(), "platform": platform.platform(), "uptime_seconds": int(time.time() - boot), "timestamp": datetime.now(timezone.utc).isoformat(), "cpu_percent": psutil.cpu_percent(interval=None), "cpu_count": psutil.cpu_count(), "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else [], "memory": {"total": mem.total, "used": mem.used, "percent": mem.percent}, "disk": {"total": disk.total, "used": disk.used, "free": disk.free, "percent": round(disk.used / disk.total * 100, 1)}, "network": net_rate, "temperature_c": max(readings) if readings else None, "process_count": len(psutil.pids())}

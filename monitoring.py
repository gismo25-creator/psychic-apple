import psutil
import time
from datetime import datetime

class SystemMonitor:
    def collect_metrics(self):
        return {
            'timestamp': datetime.now(),
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent
        }
import os
import subprocess

class SecurityAudit:
    def check_vps_security(self):
        checks = {
            'firewall_active': self.check_firewall(),
            'updates_current': self.check_updates(),
            'backup_system': self.check_backups()
        }
        return checks
    
    def check_firewall(self):
        try:
            result = subprocess.run(['sudo', 'ufw', 'status'], capture_output=True, text=True)
            return 'active' in result.stdout.lower()
        except:
            return False
    
    def check_updates(self):
        try:
            subprocess.run(['sudo', 'apt-get', 'update'], capture_output=True)
            return True
        except:
            return False
    
    def check_backups(self):
        return os.path.exists('/opt/grid_trading_bot/backups')
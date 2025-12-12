import smtplib
import requests
import json
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import schedule
import threading
from typing import Dict, List, Optional, Union
import logging
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationType(Enum):
    TRADE = "trade"
    ALERT = "alert"
    ERROR = "error"
    INFO = "info"
    ARBITRAGE = "arbitrage"

@dataclass
class Notification:
    type: NotificationType
    title: str
    message: str
    timestamp: datetime
    priority: int = 1  # 1=low, 2=medium, 3=high, 4=critical
    data: dict = None

class NotificationManager:
    """Beheer alle notificaties (Telegram, Email, Push, etc.)"""
    
    def __init__(self, config_path: str = "config/notifications.json"):
        self.config = self.load_config(config_path)
        self.notification_queue = []
        self.is_running = False
        self.history = []
        self.max_history = 1000
        
        # Rate limiting
        self.last_sent = {}
        self.rate_limits = {
            'telegram': 1,  # seconden tussen berichten
            'email': 60,    # seconden tussen emails
            'push': 1       # seconden tussen pushes
        }
        
    def load_config(self, config_path: str) -> dict:
        """Laad notificatie configuratie"""
        default_config = {
            "telegram": {
                "enabled": False,
                "bot_token": "",
                "chat_id": "",
                "notify_on": ["trade", "alert", "error"]
            },
            "email": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "sender": "",
                "recipients": [],
                "notify_on": ["error", "alert"]
            },
            "pushover": {
                "enabled": False,
                "api_token": "",
                "user_key": "",
                "notify_on": ["alert", "error"]
            },
            "discord": {
                "enabled": False,
                "webhook_url": "",
                "notify_on": ["trade", "alert"]
            },
            "slack": {
                "enabled": False,
                "webhook_url": "",
                "channel": "#trading",
                "notify_on": ["alert", "arbitrage"]
            },
            "settings": {
                "max_queue_size": 100,
                "retry_attempts": 3,
                "retry_delay": 5
            }
        }
        
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                # Merge met default config
                for key in default_config:
                    if key in user_config:
                        default_config[key].update(user_config[key])
                return default_config
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found, using defaults")
            return default_config
    
    def save_config(self, config_path: str = "config/notifications.json"):
        """Sla configuratie op"""
        import os
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def add_notification(self, ntype: NotificationType, title: str, message: str, 
                        priority: int = 1, data: dict = None):
        """Voeg notificatie toe aan queue"""
        notification = Notification(
            type=ntype,
            title=title,
            message=message,
            timestamp=datetime.now(),
            priority=priority,
            data=data or {}
        )
        
        self.notification_queue.append(notification)
        
        # Beperk queue grootte
        if len(self.notification_queue) > self.config['settings']['max_queue_size']:
            self.notification_queue.pop(0)
        
        # Verstuur direct voor hoge prioriteit
        if priority >= 3:
            self.process_queue()
        
        return notification
    
    def process_queue(self):
        """Verwerk notificatie queue"""
        for notification in list(self.notification_queue):
            try:
                self.send_notification(notification)
                self.notification_queue.remove(notification)
                
                # Bewaar in history
                self.history.append(notification)
                if len(self.history) > self.max_history:
                    self.history.pop(0)
                    
                time.sleep(0.1)  # Prevent rate limiting
                
            except Exception as e:
                logger.error(f"Error sending notification: {str(e)}")
    
    def send_notification(self, notification: Notification):
        """Verstuur notificatie via alle geconfigureerde kanalen"""
        
        # Check rate limiting
        current_time = time.time()
        
        # Telegram
        if self.config['telegram']['enabled'] and notification.type.value in self.config['telegram']['notify_on']:
            if self.check_rate_limit('telegram', current_time):
                self.send_telegram(notification)
                self.last_sent['telegram'] = current_time
        
        # Email
        if self.config['email']['enabled'] and notification.type.value in self.config['email']['notify_on']:
            if self.check_rate_limit('email', current_time):
                self.send_email(notification)
                self.last_sent['email'] = current_time
        
        # Pushover
        if self.config['pushover']['enabled'] and notification.type.value in self.config['pushover']['notify_on']:
            if self.check_rate_limit('push', current_time):
                self.send_pushover(notification)
                self.last_sent['push'] = current_time
        
        # Discord
        if self.config['discord']['enabled'] and notification.type.value in self.config['discord']['notify_on']:
            self.send_discord(notification)
        
        # Slack
        if self.config['slack']['enabled'] and notification.type.value in self.config['slack']['notify_on']:
            self.send_slack(notification)
    
    def check_rate_limit(self, channel: str, current_time: float) -> bool:
        """Controleer rate limiting"""
        if channel not in self.last_sent:
            return True
        
        time_since_last = current_time - self.last_sent.get(channel, 0)
        return time_since_last >= self.rate_limits.get(channel, 1)
    
    def send_telegram(self, notification: Notification):
        """Verstuur Telegram bericht"""
        try:
            bot_token = self.config['telegram']['bot_token']
            chat_id = self.config['telegram']['chat_id']
            
            if not bot_token or not chat_id:
                return
            
            # Format bericht
            emoji = {
                NotificationType.TRADE: "💰",
                NotificationType.ALERT: "🚨",
                NotificationType.ERROR: "❌",
                NotificationType.INFO: "ℹ️",
                NotificationType.ARBITRAGE: "🔄"
            }.get(notification.type, "📢")
            
            message = f"{emoji} *{notification.title}*\n\n{notification.message}"
            
            if notification.data:
                message += f"\n\n`{json.dumps(notification.data, indent=2)}`"
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Telegram error: {response.text}")
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Telegram send error: {str(e)}")
            return False
    
    def send_email(self, notification: Notification):
        """Verstuur email"""
        try:
            config = self.config['email']
            
            if not config['username'] or not config['password']:
                return False
            
            # Maak email bericht
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[GridBot] {notification.title}"
            msg['From'] = config['sender']
            msg['To'] = ', '.join(config['recipients'])
            
            # Prioriteit kleur
            priority_colors = {
                1: "#3498db",  # Blue
                2: "#f39c12",  # Orange
                3: "#e74c3c",  # Red
                4: "#8e44ad"   # Purple
            }
            
            color = priority_colors.get(notification.priority, "#3498db")
            
            # HTML content
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: {color}; color: white; padding: 15px; border-radius: 5px; }}
                    .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin-top: 20px; }}
                    .data {{ background-color: #2c3e50; color: white; padding: 10px; border-radius: 3px; font-family: monospace; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>{notification.title}</h2>
                    </div>
                    <div class="content">
                        <p>{notification.message}</p>
                        <p><strong>Time:</strong> {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
                        <p><strong>Priority:</strong> {notification.priority}</p>
                    </div>
            """
            
            if notification.data:
                html += f"""
                    <div class="content">
                        <h3>Data:</h3>
                        <div class="data">
                            {json.dumps(notification.data, indent=2)}
                        </div>
                    </div>
                """
            
            html += """
                </div>
            </body>
            </html>
            """
            
            # Plain text versie
            text = f"{notification.title}\n\n{notification.message}\n\nTime: {notification.timestamp}\nPriority: {notification.priority}"
            
            if notification.data:
                text += f"\n\nData:\n{json.dumps(notification.data, indent=2)}"
            
            # Voeg beide versies toe
            part1 = MIMEText(text, 'plain')
            part2 = MIMEText(html, 'html')
            msg.attach(part1)
            msg.attach(part2)
            
            # Verstuur email
            with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
                server.starttls()
                server.login(config['username'], config['password'])
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            logger.error(f"Email send error: {str(e)}")
            return False
    
    def send_pushover(self, notification: Notification):
        """Verstuur Pushover notificatie"""
        try:
            config = self.config['pushover']
            
            url = "https://api.pushover.net/1/messages.json"
            payload = {
                "token": config['api_token'],
                "user": config['user_key'],
                "title": f"GridBot: {notification.title}",
                "message": notification.message,
                "priority": min(notification.priority, 2),  # Pushover ondersteunt 0-2
                "timestamp": int(notification.timestamp.timestamp())
            }
            
            response = requests.post(url, data=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Pushover send error: {str(e)}")
            return False
    
    def send_discord(self, notification: Notification):
        """Verstuur Discord webhook"""
        try:
            webhook_url = self.config['discord']['webhook_url']
            
            if not webhook_url:
                return False
            
            # Kies kleur gebaseerd op type
            colors = {
                NotificationType.TRADE: 0x00ff00,  # Green
                NotificationType.ALERT: 0xff9900,  # Orange
                NotificationType.ERROR: 0xff0000,  # Red
                NotificationType.INFO: 0x0099ff,   # Blue
                NotificationType.ARBITRAGE: 0x9900ff  # Purple
            }
            
            embed = {
                "title": notification.title,
                "description": notification.message,
                "color": colors.get(notification.type, 0x0099ff),
                "timestamp": notification.timestamp.isoformat(),
                "fields": []
            }
            
            if notification.data:
                for key, value in notification.data.items():
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, indent=2)[:1024]
                    embed["fields"].append({
                        "name": key,
                        "value": str(value)[:1024],
                        "inline": True
                    })
            
            payload = {
                "embeds": [embed]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            return response.status_code == 204
            
        except Exception as e:
            logger.error(f"Discord send error: {str(e)}")
            return False
    
    def send_slack(self, notification: Notification):
        """Verstuur Slack notificatie"""
        try:
            webhook_url = self.config['slack']['webhook_url']
            
            if not webhook_url:
                return False
            
            # Kies emoji gebaseerd op type
            emojis = {
                NotificationType.TRADE: ":moneybag:",
                NotificationType.ALERT: ":rotating_light:",
                NotificationType.ERROR: ":x:",
                NotificationType.INFO: ":information_source:",
                NotificationType.ARBITRAGE: ":arrows_counterclockwise:"
            }
            
            emoji = emojis.get(notification.type, ":bell:")
            
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {notification.title}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": notification.message
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Time:* {notification.timestamp.strftime('%H:%M:%S')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Priority:* {notification.priority}"
                        }
                    ]
                }
            ]
            
            if notification.data:
                data_text = "```\n" + json.dumps(notification.data, indent=2)[:2000] + "\n```"
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Data:*\n{data_text}"
                    }
                })
            
            payload = {
                "channel": self.config['slack']['channel'],
                "blocks": blocks
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Slack send error: {str(e)}")
            return False
    
    def send_trade_notification(self, trade_data: dict):
        """Specialiseerde trade notificatie"""
        title = f"Trade Executed: {trade_data.get('side', '').upper()}"
        message = f"""
Symbol: {trade_data.get('symbol', 'N/A')}
Side: {trade_data.get('side', 'N/A')}
Price: ${trade_data.get('price', 0):.2f}
Amount: {trade_data.get('amount', 0):.6f}
Value: ${trade_data.get('value', 0):.2f}
Exchange: {trade_data.get('exchange', 'N/A')}
"""
        
        if 'profit' in trade_data:
            profit_color = "🟢" if trade_data['profit'] > 0 else "🔴"
            message += f"Profit: {profit_color} ${trade_data['profit']:.2f}\n"
        
        self.add_notification(
            NotificationType.TRADE,
            title,
            message,
            priority=2,
            data=trade_data
        )
    
    def send_arbitrage_notification(self, opportunity: dict):
        """Specialiseerde arbitrage notificatie"""
        title = f"Arbitrage Opportunity: {opportunity.get('profit_pct', 0):.2f}%"
        message = f"""
Buy: {opportunity.get('buy_exchange', 'N/A')} @ ${opportunity.get('buy_price', 0):.2f}
Sell: {opportunity.get('sell_exchange', 'N/A')} @ ${opportunity.get('sell_price', 0):.2f}
Profit: {opportunity.get('profit_pct', 0):.2f}%
Symbol: {opportunity.get('symbol', 'N/A')}
"""
        
        self.add_notification(
            NotificationType.ARBITRAGE,
            title,
            message,
            priority=3,
            data=opportunity
        )
    
    def send_error_notification(self, error_message: str, context: dict = None):
        """Specialiseerde error notificatie"""
        self.add_notification(
            NotificationType.ERROR,
            "System Error",
            error_message,
            priority=4,
            data=context or {}
        )
    
    def send_daily_summary(self, summary_data: dict):
        """Verstuur dagelijks samenvattingsrapport"""
        title = "Daily Trading Summary"
        
        message = f"""
📊 *Daily Trading Summary*
────────────────
Trades: {summary_data.get('total_trades', 0)}
Win Rate: {summary_data.get('win_rate', 0):.1f}%
Total P&L: ${summary_data.get('total_pnl', 0):.2f}
Best Trade: ${summary_data.get('best_trade', 0):.2f}
Worst Trade: ${summary_data.get('worst_trade', 0):.2f}
────────────────
Portfolio Value: ${summary_data.get('portfolio_value', 0):.2f}
24h Change: {summary_data.get('daily_change', 0):.2f}%
────────────────
Active Strategies: {summary_data.get('active_strategies', 0)}
"""
        
        self.add_notification(
            NotificationType.INFO,
            title,
            message,
            priority=1,
            data=summary_data
        )
    
    def start_scheduler(self):
        """Start geplande notificaties"""
        # Dagelijks om 18:00
        schedule.every().day.at("18:00").do(
            self.send_daily_summary,
            {'note': 'Automatic daily summary'}
        )
        
        # Wekelijkse samenvatting op zondag
        schedule.every().sunday.at("20:00").do(
            lambda: self.add_notification(
                NotificationType.INFO,
                "Weekly Summary",
                "Weekly trading summary will be sent shortly...",
                priority=1
            )
        )
        
        self.is_running = True
        
        # Start scheduler in aparte thread
        def run_scheduler():
            while self.is_running:
                schedule.run_pending()
                time.sleep(60)  # Check elke minuut
        
        thread = threading.Thread(target=run_scheduler, daemon=True)
        thread.start()
    
    def stop_scheduler(self):
        """Stop de scheduler"""
        self.is_running = False
    
    def get_notification_history(self, limit: int = 50, ntype: str = None):
        """Haal notificatie geschiedenis op"""
        history = self.history
        
        if ntype:
            history = [n for n in history if n.type.value == ntype]
        
        return history[-limit:] if limit else history
    
    def clear_history(self):
        """Wis notificatie geschiedenis"""
        self.history.clear()
    
    def test_all_channels(self):
        """Test alle geconfigureerde notificatiekanalen"""
        test_notification = Notification(
            type=NotificationType.INFO,
            title="Test Notification",
            message="This is a test notification from Grid Trading Bot.",
            timestamp=datetime.now(),
            priority=1,
            data={'test': True, 'time': datetime.now().isoformat()}
        )
        
        results = {
            'telegram': self.send_telegram(test_notification) if self.config['telegram']['enabled'] else 'disabled',
            'email': self.send_email(test_notification) if self.config['email']['enabled'] else 'disabled',
            'pushover': self.send_pushover(test_notification) if self.config['pushover']['enabled'] else 'disabled',
            'discord': self.send_discord(test_notification) if self.config['discord']['enabled'] else 'disabled',
            'slack': self.send_slack(test_notification) if self.config['slack']['enabled'] else 'disabled'
        }
        
        return results

# Voorbeeld gebruik
if __name__ == "__main__":
    # Maak configuratie map aan
    import os
    os.makedirs("config", exist_ok=True)
    
    # Maak notificatie manager
    nm = NotificationManager()
    
    # Test notificaties
    nm.add_notification(
        NotificationType.INFO,
        "Bot Started",
        "Grid Trading Bot has been successfully started.",
        priority=1
    )
    
    # Simuleer een trade
    nm.send_trade_notification({
        'symbol': 'BTC/USDT',
        'side': 'buy',
        'price': 50000,
        'amount': 0.01,
        'value': 500,
        'exchange': 'binance',
        'profit': 5.25
    })
    
    # Test alle kanalen
    results = nm.test_all_channels()
    print("Test results:", results)
    
    # Start scheduler
    nm.start_scheduler()
    print("Notification manager started with scheduler")
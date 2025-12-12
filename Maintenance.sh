#!/bin/bash
echo "=== Grid Trading Bot Maintenance ==="
echo "Date: $(date)"
cd /opt/grid_trading_bot
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart grid-trading-bot
echo "✅ Maintenance complete!"
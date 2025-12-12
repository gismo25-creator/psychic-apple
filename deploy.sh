#!/bin/bash
set -e

echo "🚀 Grid Trading Bot VPS Deployment"
echo "=================================="

echo "📦 Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

echo "🐍 Installing Python and pip..."
sudo apt-get install -y python3 python3-pip python3-venv git nginx

echo "📚 Installing system dependencies..."
sudo apt-get install -y libpq-dev python3-dev build-essential

echo "📁 Creating application directory..."
APP_DIR="/opt/grid_trading_bot"
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR

echo "📥 Setting up application files..."
cd $APP_DIR

echo "🔧 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install streamlit pandas numpy plotly ccxt yfinance python-dotenv

echo "🔐 Creating environment configuration..."
cat > .env << EOF
BINANCE_API_KEY=""
BINANCE_API_SECRET=""
DEFAULT_SYMBOL="BTC/USDT"
INITIAL_CAPITAL=10000
STREAMLIT_PORT=8501
EOF

echo "🗄️ Creating data directories..."
mkdir -p $APP_DIR/data $APP_DIR/logs $APP_DIR/backups

echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/grid-trading-bot.service > /dev/null << EOF
[Unit]
Description=Grid Trading Bot Streamlit App
After=network.target

[Service]
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/streamlit run app_streamlit.py --server.port=8501 --server.address=0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "🚀 Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable grid-trading-bot
sudo systemctl start grid-trading-bot

echo "✅ Deployment complete!"
echo "App URL: http://$(curl -s ifconfig.me):8501"
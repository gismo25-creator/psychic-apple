import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta
import ccxt
import threading
import json
import pickle
from pathlib import Path
import sys
import warnings
warnings.filterwarnings('ignore')

# Voeg custom modules toe
sys.path.append('.')
from grid_trading_system import GridTradingSystem
from backtester import Backtester

# Pagina configuratie
st.set_page_config(
    page_title="Grid Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .stButton button {
        width: 100%;
        background-color: #1E88E5;
        color: white;
        font-weight: bold;
    }
    .trade-buy {
        color: #00C853 !important;
        font-weight: bold;
    }
    .trade-sell {
        color: #FF5252 !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialiseer session state
if 'trading_system' not in st.session_state:
    st.session_state.trading_system = GridTradingSystem(mode='simulation')
    st.session_state.backtester = Backtester()
    st.session_state.is_running = False
    st.session_state.results = None
    st.session_state.orders = []
    st.session_state.trades = []
    st.session_state.equity_curve = []
    st.session_state.update_counter = 0

def main():
    """Hoofdpagina van de applicatie"""
    
    # Header
    st.markdown('<h1 class="main-header">🤖 Grid Trading Dashboard</h1>', 
                unsafe_allow_html=True)
    
    # Sidebar voor configuratie
    with st.sidebar:
        st.header("⚙️ Configuratie")
        
        # Trading mode selector
        mode = st.selectbox(
            "Trading Mode",
            ["Simulatie", "Backtest", "Live Trading"],
            index=0
        )
        
        # Symbol selector
        symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
        symbol = st.selectbox("Trading Pair", symbols)
        
        # Grid parameters
        st.subheader("Grid Parameters")
        
        col1, col2 = st.columns(2)
        with col1:
            grid_type = st.selectbox(
                "Grid Type",
                ["Linear", "Geometric", "Fibonacci"],
                index=0
            )
            num_grids = st.slider("Aantal Grids", 5, 50, 20)
            
        with col2:
            grid_range = st.slider("Grid Range (%)", 1.0, 20.0, 10.0, 0.5)
            order_size = st.number_input("Order Size (USDT)", 10.0, 1000.0, 100.0)
        
        # Risk management
        st.subheader("Risk Management")
        stop_loss = st.slider("Stop Loss (%)", 1.0, 20.0, 5.0, 0.5)
        take_profit = st.slider("Take Profit (%)", 0.5, 10.0, 2.0, 0.5)
        
        # Start/Stop controls
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🚀 Start", use_container_width=True):
                start_trading(mode, symbol, grid_type.lower(), 
                            num_grids, grid_range/100, order_size)
        
        with col2:
            if st.button("⏸️ Pause", use_container_width=True):
                st.session_state.is_running = False
        
        with col3:
            if st.button("⏹️ Stop", use_container_width=True):
                stop_trading()
        
        # Download results
        if st.session_state.results:
            st.download_button(
                label="📥 Download Results",
                data=json.dumps(st.session_state.results, indent=2, default=str),
                file_name=f"grid_trading_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
        
        # Status indicator
        st.subheader("📊 Status")
        status_color = "🟢" if st.session_state.is_running else "🔴"
        st.markdown(f"**Status:** {status_color} {'Running' if st.session_state.is_running else 'Stopped'}")
        
        if st.session_state.trades:
            st.markdown(f"**Total Trades:** {len(st.session_state.trades)}")
        
        # Live update interval
        update_interval = st.slider("Update Interval (s)", 1, 10, 3)
        
        # Auto-refresh
        if st.session_state.is_running:
            time.sleep(update_interval)
            st.session_state.update_counter += 1
            st.rerun()
    
    # Main content area
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Dashboard", 
        "📊 Performance", 
        "📋 Trades & Orders", 
        "🔧 Backtesting"
    ])
    
    with tab1:
        display_dashboard()
    
    with tab2:
        display_performance()
    
    with tab3:
        display_trades_orders()
    
    with tab4:
        display_backtesting()

def start_trading(mode, symbol, grid_type, num_grids, grid_range, order_size):
    """Start trading strategie"""
    st.session_state.is_running = True
    
    # Update trading system
    trading_system = st.session_state.trading_system
    trading_system.symbol = symbol
    
    # Set mode
    if mode == "Simulatie":
        trading_system.mode = 'simulation'
    elif mode == "Live Trading":
        trading_system.mode = 'live'
        # Hier zou je API keys moeten configureren
    else:
        trading_system.mode = 'backtest'
    
    # Run strategy in background thread
    params = {
        'grid_type': grid_type,
        'num_grids': num_grids,
        'grid_range_pct': grid_range,
        'order_size': order_size
    }
    
    # Start in thread om UI niet te blokkeren
    def run_strategy():
        results = trading_system.run_strategy(params)
        st.session_state.results = results
        if 'equity_curve' in results:
            st.session_state.equity_curve = results['equity_curve']
        if 'trades' in results:
            st.session_state.trades = results['trades']
    
    thread = threading.Thread(target=run_strategy, daemon=True)
    thread.start()
    
    st.success(f"Strategy started in {mode} mode!")

def stop_trading():
    """Stop trading"""
    st.session_state.is_running = False
    st.session_state.trading_system = GridTradingSystem(mode='simulation')
    st.success("Trading stopped and system reset!")

def display_dashboard():
    """Display hoofd dashboard"""
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📊 Market Overview")
        
        # Prijs chart met grid levels
        if st.session_state.trading_system.grid_levels:
            fig = create_price_grid_chart()
            st.plotly_chart(fig, use_container_width=True, key="price_chart")
        else:
            st.info("Start trading to see market overview")
        
        # Portfolio overview
        st.subheader("💰 Portfolio Overview")
        
        if st.session_state.trading_system.portfolio:
            portfolio = st.session_state.trading_system.portfolio
            
            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            with col_p1:
                st.metric("Cash", f"${portfolio.get('cash', 0):.2f}")
            with col_p2:
                st.metric("Positions", f"{portfolio.get('positions', 0):.6f}")
            with col_p3:
                total_value = portfolio.get('total_value', 0)
                st.metric("Total Value", f"${total_value:.2f}")
            with col_p4:
                pnl = total_value - 10000
                st.metric("P&L", f"${pnl:.2f}", 
                         delta=f"{(pnl/10000*100):.2f}%" if pnl != 0 else "0%")
    
    with col2:
        st.subheader("⚡ Real-time Metrics")
        
        # Quick metrics
        metrics = st.session_state.trading_system.performance_metrics
        
        if metrics:
            st.metric("Total Return", f"{metrics.get('total_return', 0):.2f}%")
            st.metric("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.2f}")
            st.metric("Max Drawdown", f"{metrics.get('max_drawdown', 0):.2f}%")
            st.metric("Win Rate", f"{metrics.get('win_rate', 0):.2f}%")
            st.metric("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
            st.metric("Total Trades", f"{metrics.get('total_trades', 0)}")
        
        # Current price
        st.subheader("💵 Current Price")
        if hasattr(st.session_state.trading_system, 'current_sim_price'):
            current_price = st.session_state.trading_system.current_sim_price
            st.metric("BTC/USDT", f"${current_price:,.2f}")
        
        # Grid levels
        st.subheader("🎯 Grid Levels")
        if st.session_state.trading_system.grid_levels:
            grid_df = pd.DataFrame({
                'Level': range(1, len(st.session_state.trading_system.grid_levels) + 1),
                'Price': st.session_state.trading_system.grid_levels
            })
            st.dataframe(grid_df.style.format({'Price': '${:,.2f}'}), 
                        height=300, use_container_width=True)

def create_price_grid_chart():
    """Maak prijs chart met grid levels"""
    trading_system = st.session_state.trading_system
    
    # Genereer simulatie data
    dates = pd.date_range(end=datetime.now(), periods=100, freq='1min')
    current_price = getattr(trading_system, 'current_sim_price', 50000)
    prices = current_price * (1 + np.random.normal(0, 0.001, 100).cumsum())
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=('Price with Grid Levels', 'Buy/Sell Signals'),
        row_heights=[0.7, 0.3]
    )
    
    # Prijs lijn
    fig.add_trace(
        go.Scatter(
            x=dates, y=prices,
            mode='lines',
            name='Price',
            line=dict(color='blue', width=2)
        ),
        row=1, col=1
    )
    
    # Grid levels als horizontale lijnen
    if trading_system.grid_levels:
        for price in trading_system.grid_levels:
            fig.add_hline(
                y=price,
                line_dash="dash",
                line_color="gray",
                opacity=0.3,
                row=1, col=1
            )
    
    # Trade signals
    if st.session_state.trades:
        trades_df = pd.DataFrame(st.session_state.trades[-10:])  # Laatste 10 trades
        buy_trades = trades_df[trades_df['side'] == 'buy']
        sell_trades = trades_df[trades_df['side'] == 'sell']
        
        if not buy_trades.empty:
            fig.add_trace(
                go.Scatter(
                    x=buy_trades['timestamp'],
                    y=buy_trades['price'],
                    mode='markers',
                    name='Buy',
                    marker=dict(color='green', size=10, symbol='triangle-up')
                ),
                row=2, col=1
            )
        
        if not sell_trades.empty:
            fig.add_trace(
                go.Scatter(
                    x=sell_trades['timestamp'],
                    y=sell_trades['price'],
                    mode='markers',
                    name='Sell',
                    marker=dict(color='red', size=10, symbol='triangle-down')
                ),
                row=2, col=1
            )
    
    fig.update_layout(height=600, showlegend=True)
    return fig

def display_performance():
    """Display performance metrics en charts"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Equity Curve")
        
        if st.session_state.equity_curve:
            eq_df = pd.DataFrame(st.session_state.equity_curve)
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=eq_df['timestamp'],
                y=eq_df['value'],
                mode='lines',
                name='Portfolio Value',
                line=dict(color='green', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 0, 0.1)'
            ))
            
            fig.update_layout(
                xaxis_title="Time",
                yaxis_title="Value (USDT)",
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Run strategy to see equity curve")
    
    with col2:
        st.subheader("📊 Performance Metrics")
        
        metrics = st.session_state.trading_system.performance_metrics
        
        if metrics:
            # Gauge charts
            fig = make_subplots(
                rows=2, cols=2,
                specs=[[{'type': 'indicator'}, {'type': 'indicator'}],
                       [{'type': 'indicator'}, {'type': 'indicator'}]],
                subplot_titles=('Total Return', 'Win Rate', 
                              'Sharpe Ratio', 'Max Drawdown')
            )
            
            # Total Return gauge
            fig.add_trace(
                go.Indicator(
                    mode="gauge+number",
                    value=metrics.get('total_return', 0),
                    title={'text': "Return %"},
                    gauge={'axis': {'range': [-20, 20]},
                          'bar': {'color': "darkblue"},
                          'steps': [
                              {'range': [-20, 0], 'color': "red"},
                              {'range': [0, 20], 'color': "green"}
                          ]}
                ),
                row=1, col=1
            )
            
            # Win Rate gauge
            fig.add_trace(
                go.Indicator(
                    mode="gauge+number",
                    value=metrics.get('win_rate', 0),
                    title={'text': "Win Rate %"},
                    gauge={'axis': {'range': [0, 100]},
                          'bar': {'color': "darkblue"}}
                ),
                row=1, col=2
            )
            
            # Sharpe Ratio
            fig.add_trace(
                go.Indicator(
                    mode="number",
                    value=metrics.get('sharpe_ratio', 0),
                    title={'text': "Sharpe Ratio"}
                ),
                row=2, col=1
            )
            
            # Max Drawdown
            fig.add_trace(
                go.Indicator(
                    mode="gauge+number",
                    value=abs(metrics.get('max_drawdown', 0)),
                    title={'text': "Max DD %"},
                    gauge={'axis': {'range': [0, 50]},
                          'bar': {'color': "orange"}}
                ),
                row=2, col=2
            )
            
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
    
    # Drawdown chart
    st.subheader("📉 Drawdown Analysis")
    
    if st.session_state.equity_curve:
        eq_df = pd.DataFrame(st.session_state.equity_curve)
        
        # Calculate drawdown
        eq_df['peak'] = eq_df['value'].expanding().max()
        eq_df['drawdown'] = (eq_df['value'] - eq_df['peak']) / eq_df['peak'] * 100
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=eq_df['timestamp'],
            y=eq_df['drawdown'],
            mode='lines',
            name='Drawdown %',
            line=dict(color='red', width=2),
            fill='tozeroy',
            fillcolor='rgba(255, 0, 0, 0.1)'
        ))
        
        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Drawdown %",
            height=300
        )
        
        st.plotly_chart(fig, use_container_width=True)

def display_trades_orders():
    """Display trades en orders"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 Recent Orders")
        
        if st.session_state.trading_system.orders:
            orders_df = pd.DataFrame(st.session_state.trading_system.orders[-20:])  # Laatste 20 orders
            
            # Format timestamp
            if 'timestamp' in orders_df.columns:
                orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp']).dt.strftime('%H:%M:%S')
            
            # Styling voor side column
            def color_side(val):
                color = 'green' if val == 'buy' else 'red'
                return f'color: {color}; font-weight: bold'
            
            st.dataframe(
                orders_df.style.applymap(color_side, subset=['side']).format({
                    'price': '${:,.2f}',
                    'amount': '{:.6f}'
                }),
                height=400,
                use_container_width=True
            )
        else:
            st.info("No orders yet")
    
    with col2:
        st.subheader("💰 Recent Trades")
        
        if st.session_state.trades:
            trades_df = pd.DataFrame(st.session_state.trades[-20:])  # Laatste 20 trades
            
            # Bereken profit/loss
            if 'price' in trades_df.columns and 'amount' in trades_df.columns:
                trades_df['value'] = trades_df['price'] * trades_df['amount']
            
            # Format timestamp
            if 'timestamp' in trades_df.columns:
                trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp']).dt.strftime('%H:%M:%S')
            
            st.dataframe(
                trades_df.style.applymap(color_side, subset=['side']).format({
                    'price': '${:,.2f}',
                    'amount': '{:.6f}',
                    'value': '${:,.2f}',
                    'fee': '${:,.4f}'
                }),
                height=400,
                use_container_width=True
            )
            
            # Trade statistics
            st.subheader("📊 Trade Statistics")
            
            if not trades_df.empty:
                total_trades = len(trades_df)
                buy_trades = len(trades_df[trades_df['side'] == 'buy'])
                sell_trades = len(trades_df[trades_df['side'] == 'sell'])
                
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.metric("Total Trades", total_trades)
                with col_s2:
                    st.metric("Buy Trades", buy_trades)
                with col_s3:
                    st.metric("Sell Trades", sell_trades)
        else:
            st.info("No trades yet")

def display_backtesting():
    """Display backtesting interface"""
    
    st.subheader("🔧 Backtesting Parameters")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime.now() - timedelta(days=30)
        )
        
        initial_capital = st.number_input(
            "Initial Capital (USDT)",
            min_value=100.0,
            max_value=100000.0,
            value=10000.0,
            step=1000.0
        )
    
    with col2:
        end_date = st.date_input(
            "End Date",
            value=datetime.now()
        )
        
        fee_rate = st.slider(
            "Fee Rate (%)",
            min_value=0.01,
            max_value=0.5,
            value=0.1,
            step=0.01
        ) / 100
    
    with col3:
        interval = st.selectbox(
            "Data Interval",
            ["1m", "5m", "15m", "1h", "4h", "1d"],
            index=3
        )
        
        symbol_backtest = st.selectbox(
            "Symbol for Backtest",
            ["BTC-USD", "ETH-USD", "BNB-USD"],
            index=0
        )
    
    # Parameter grid voor optimalisatie
    st.subheader("🎯 Strategy Parameters")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        grid_range_min = st.slider("Grid Range Min %", 5.0, 30.0, 5.0, 1.0)
        grid_range_max = st.slider("Grid Range Max %", 5.0, 30.0, 15.0, 1.0)
    
    with col_p2:
        num_grids_min = st.slider("Min Grids", 5, 30, 10, 1)
        num_grids_max = st.slider("Max Grids", 10, 50, 25, 1)
    
    with col_p3:
        order_size_min = st.slider("Min Order Size", 10.0, 500.0, 50.0, 10.0)
        order_size_max = st.slider("Max Order Size", 100.0, 1000.0, 200.0, 10.0)
    
    # Run backtest button
    if st.button("▶️ Run Backtest", use_container_width=True):
        with st.spinner("Running backtest..."):
            try:
                backtester = st.session_state.backtester
                
                # Haal historische data op
                data = backtester.fetch_historical_data(
                    symbol=symbol_backtest,
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d'),
                    interval=interval
                )
                
                # Voer backtest uit
                strategy_params = {
                    'grid_range_pct': (grid_range_min + grid_range_max) / 200,
                    'num_grids': (num_grids_min + num_grids_max) // 2,
                    'order_size': (order_size_min + order_size_max) / 2,
                    'fee_rate': fee_rate
                }
                
                results = backtester.backtest_grid_strategy(data, strategy_params)
                
                # Toon resultaten
                st.subheader("📊 Backtest Results")
                
                metrics = results['metrics']
                
                col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                with col_r1:
                    st.metric("Total Return", f"{metrics.get('total_return_pct', 0):.2f}%")
                with col_r2:
                    st.metric("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.2f}")
                with col_r3:
                    st.metric("Max Drawdown", f"{metrics.get('max_drawdown_pct', 0):.2f}%")
                with col_r4:
                    st.metric("Win Rate", f"{metrics.get('win_rate_pct', 0):.2f}%")
                
                # Equity curve
                fig = go.Figure()
                equity_df = pd.DataFrame(results['equity_curve'])
                fig.add_trace(go.Scatter(
                    x=equity_df['timestamp'],
                    y=equity_df['value'],
                    mode='lines',
                    name='Portfolio Value',
                    line=dict(color='blue', width=2)
                ))
                
                fig.update_layout(
                    title="Backtest Equity Curve",
                    xaxis_title="Date",
                    yaxis_title="Portfolio Value (USDT)",
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Backtest failed: {str(e)}")

if __name__ == "__main__":

    main()

import ccxt
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
import json
import pickle
from decimal import Decimal, ROUND_DOWN
import time

warnings.filterwarnings('ignore')

class GridTradingSystem:
    """Hoofdsysteem voor Grid Trading met backtesting, simulatie en dashboard"""
    
    def __init__(self, mode='simulation', exchange='binance', symbol='BTC/USDT'):
        self.mode = mode  # 'live', 'simulation', 'backtest'
        self.symbol = symbol
        self.exchange_name = exchange
        self.grid_levels = []
        self.orders = []
        self.trades = []
        self.portfolio = {
            'cash': 10000,
            'positions': 0,
            'total_value': 10000
        }
        self.performance_metrics = {}
        
        if mode == 'live':
            self.setup_live_exchange()
        elif mode == 'simulation':
            self.setup_simulation()
        elif mode == 'backtest':
            self.setup_backtest()
    
    def setup_live_exchange(self, api_key=None, api_secret=None):
        """Setup voor live trading"""
        if api_key and api_secret:
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {'defaultType': 'future'},
                'enableRateLimit': True
            })
        else:
            print("Running in demo mode - no real orders")
            self.exchange = None
    
    def setup_simulation(self):
        """Setup voor simulatie met mock data"""
        self.sim_data = self.generate_market_data()
        self.current_sim_price = self.sim_data['close'].iloc[0]
        self.sim_time = 0
    
    def setup_backtest(self):
        """Setup voor backtesting"""
        self.historical_data = None
        self.backtest_results = {}
    
    def generate_market_data(self, days=30, volatility=0.02):
        """Genereer simulatie data"""
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=days*24*60, freq='1min')
        base_price = 50000
        
        # Random walk met trend
        returns = np.random.normal(0, volatility, len(dates)) / np.sqrt(24*60)
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Voeg wat mean reversion toe
        for i in range(1, len(prices)):
            if prices[i] > base_price * 1.1:
                prices[i] = prices[i-1] * 0.999
            elif prices[i] < base_price * 0.9:
                prices[i] = prices[i-1] * 1.001
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices * 0.999,
            'high': prices * 1.001,
            'low': prices * 0.998,
            'close': prices,
            'volume': np.random.uniform(100, 1000, len(dates))
        })
        
        return df
    
    def calculate_grid(self, current_price, lower_bound, upper_bound, num_grids, grid_type='linear'):
        """Bereken grid niveaus"""
        if grid_type == 'linear':
            self.grid_levels = np.linspace(lower_bound, upper_bound, num_grids)
        elif grid_type == 'geometric':
            self.grid_levels = np.geomspace(lower_bound, upper_bound, num_grids)
        elif grid_type == 'fibonacci':
            fib_ratios = self.generate_fibonacci_ratios(num_grids)
            price_range = upper_bound - lower_bound
            self.grid_levels = [lower_bound + ratio * price_range for ratio in fib_ratios]
        
        return self.grid_levels
    
    def generate_fibonacci_ratios(self, n):
        """Genereer Fibonacci ratios voor grid spacing"""
        fib = [0, 1]
        for i in range(2, n):
            fib.append(fib[-1] + fib[-2])
        
        max_fib = max(fib)
        return [f/max_fib for f in fib]
    
    def place_order(self, price, amount, side, order_type='limit'):
        """Plaats een order (live of simulatie)"""
        order = {
            'id': len(self.orders) + 1,
            'timestamp': datetime.now(),
            'price': price,
            'amount': amount,
            'side': side,
            'type': order_type,
            'status': 'open'
        }
        
        if self.mode == 'simulation':
            # Simuleer order matching
            order['status'] = 'filled'
            self.execute_trade(order)
        elif self.mode == 'live' and self.exchange:
            try:
                if order_type == 'limit':
                    exchange_order = self.exchange.create_order(
                        symbol=self.symbol,
                        type='LIMIT',
                        side=side,
                        amount=amount,
                        price=price,
                        params={'timeInForce': 'GTC'}
                    )
                    order['exchange_id'] = exchange_order['id']
            except Exception as e:
                print(f"Order error: {e}")
                order['status'] = 'rejected'
        
        self.orders.append(order)
        return order
    
    def execute_trade(self, order):
        """Voer een trade uit en update portfolio"""
        trade = {
            'order_id': order['id'],
            'timestamp': datetime.now(),
            'price': order['price'],
            'amount': order['amount'],
            'side': order['side'],
            'fee': order['price'] * order['amount'] * 0.001
        }
        
        if order['side'] == 'buy':
            cost = order['price'] * order['amount'] + trade['fee']
            if self.portfolio['cash'] >= cost:
                self.portfolio['cash'] -= cost
                self.portfolio['positions'] += order['amount']
        else:  # sell
            if self.portfolio['positions'] >= order['amount']:
                revenue = order['price'] * order['amount'] - trade['fee']
                self.portfolio['cash'] += revenue
                self.portfolio['positions'] -= order['amount']
        
        self.trades.append(trade)
        self.update_portfolio_value(order['price'])
        return trade
    
    def update_portfolio_value(self, current_price):
        """Update totale portefeuille waarde"""
        self.portfolio['total_value'] = (
            self.portfolio['cash'] + 
            self.portfolio['positions'] * current_price
        )
    
    def run_strategy(self, strategy_params):
        """Voer grid trading strategie uit"""
        if self.mode == 'simulation':
            return self.run_simulation(strategy_params)
        elif self.mode == 'backtest':
            return self.run_backtest(strategy_params)
        elif self.mode == 'live':
            return self.run_live(strategy_params)
    
    def run_simulation(self, params, duration_hours=24):
        """Run simulatie"""
        results = {
            'equity_curve': [],
            'trades': [],
            'metrics': {}
        }
        
        # Setup grid
        current_price = self.sim_data['close'].iloc[0]
        lower = current_price * (1 - params['grid_range_pct'])
        upper = current_price * (1 + params['grid_range_pct'])
        
        self.calculate_grid(current_price, lower, upper, 
                          params['num_grids'], params['grid_type'])
        
        # Run simulatie
        for i in range(min(len(self.sim_data), duration_hours * 60)):
            self.current_sim_price = self.sim_data['close'].iloc[i]
            self.sim_time = i
            
            # Check for grid hits
            for grid_price in self.grid_levels:
                price_diff = abs(self.current_sim_price - grid_price) / grid_price
                
                if price_diff < 0.001:  # 0.1% tolerance
                    # Place order at this grid level
                    amount = params['order_size'] / grid_price
                    
                    if self.current_sim_price <= grid_price:
                        self.place_order(grid_price, amount, 'buy')
                    else:
                        if self.portfolio['positions'] > 0:
                            self.place_order(grid_price, amount, 'sell')
            
            # Update equity curve
            self.update_portfolio_value(self.current_sim_price)
            results['equity_curve'].append({
                'timestamp': self.sim_data['timestamp'].iloc[i],
                'value': self.portfolio['total_value'],
                'price': self.current_sim_price
            })
        
        # Calculate metrics
        results['metrics'] = self.calculate_performance_metrics(results['equity_curve'])
        results['trades'] = self.trades.copy()
        
        self.simulation_results = results
        return results
    
    def run_backtest(self, params, start_date=None, end_date=None):
        """Backtest strategie op historische data"""
        from backtester import Backtester
        backtester = Backtester()
        
        if start_date is None:
            start_date = (datetime.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        data = backtester.fetch_historical_data(
            self.symbol.replace('/', '-'),
            start_date,
            end_date,
            interval='1h'
        )
        
        results = backtester.backtest_grid_strategy(data, params)
        self.backtest_results = results
        return results
    
    def run_live(self, params):
        """Run live trading"""
        # Live trading logica
        print("Live trading started with params:", params)
        return {"status": "live_trading_started"}
    
    def calculate_performance_metrics(self, equity_curve):
        """Bereken prestatiemetrics"""
        if not equity_curve:
            return {}
        
        df = pd.DataFrame(equity_curve)
        returns = df['value'].pct_change().dropna()
        
        metrics = {
            'total_return': (df['value'].iloc[-1] / df['value'].iloc[0] - 1) * 100,
            'sharpe_ratio': self.calculate_sharpe_ratio(returns),
            'max_drawdown': self.calculate_max_drawdown(df['value']),
            'win_rate': self.calculate_win_rate(),
            'profit_factor': self.calculate_profit_factor(),
            'total_trades': len(self.trades),
            'avg_trade': np.mean([t.get('profit', 0) for t in self.trades if 'profit' in t]) 
                         if self.trades else 0
        }
        
        self.performance_metrics = metrics
        return metrics
    
    def calculate_sharpe_ratio(self, returns, risk_free_rate=0.02):
        """Bereken Sharpe ratio"""
        if len(returns) < 2:
            return 0
        excess_returns = returns - risk_free_rate/252
        return np.sqrt(252) * excess_returns.mean() / returns.std() if returns.std() != 0 else 0
    
    def calculate_max_drawdown(self, values):
        """Bereken maximale drawdown"""
        peak = values.expanding(min_periods=1).max()
        drawdown = (values - peak) / peak
        return drawdown.min() * 100
    
    def calculate_win_rate(self):
        """Bereken win percentage"""
        if not self.trades:
            return 0
        
        profitable_trades = sum(1 for t in self.trades if t.get('profit', 0) > 0)
        return (profitable_trades / len(self.trades)) * 100 if self.trades else 0
    
    def calculate_profit_factor(self):
        """Bereken profit factor"""
        if not self.trades:
            return 0
        
        gross_profit = sum(t.get('profit', 0) for t in self.trades if t.get('profit', 0) > 0)
        gross_loss = abs(sum(t.get('profit', 0) for t in self.trades if t.get('profit', 0) < 0))
        
        return gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    def get_realtime_data(self):
        """Haal real-time data op voor dashboard"""
        if self.mode == 'simulation':
            return {
                'price': self.current_sim_price,
                'portfolio': self.portfolio.copy(),
                'grid_levels': self.grid_levels,
                'orders': self.orders[-10:],
                'trades': self.trades[-10:],
                'metrics': self.performance_metrics
            }
        elif self.mode == 'live':
            try:
                ticker = self.exchange.fetch_ticker(self.symbol)
                return {
                    'price': ticker['last'],
                    'portfolio': self.portfolio,
                    'grid_levels': self.grid_levels,
                    'orders': self.orders[-10:],
                    'trades': self.trades[-10:],
                    'metrics': self.performance_metrics
                }
            except:
                return {
                    'price': 50000,
                    'portfolio': self.portfolio,
                    'grid_levels': self.grid_levels,
                    'orders': self.orders[-10:],
                    'trades': self.trades[-10:],
                    'metrics': self.performance_metrics
                }
        return {}
    
    def save_results(self, filename):
        """Sla resultaten op"""
        with open(filename, 'wb') as f:
            pickle.dump({
                'trades': self.trades,
                'portfolio': self.portfolio,
                'metrics': self.performance_metrics
            }, f)
    
    def load_results(self, filename):
        """Laad opgeslagen resultaten"""
        with open(filename, 'rb') as f:
            data = pickle.load(f)
            self.trades = data['trades']
            self.portfolio = data['portfolio']
            self.performance_metrics = data['metrics']

if __name__ == "__main__":
    # Voorbeeld gebruik
    bot = GridTradingSystem(mode='simulation')
    params = {
        'grid_type': 'linear',
        'num_grids': 20,
        'grid_range_pct': 0.10,
        'order_size': 100
    }
    results = bot.run_strategy(params)
    print(f"Simulatie voltooid: {len(results.get('trades', []))} trades")
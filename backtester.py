import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

class Backtester:
    """Backtesting framework voor Grid Trading strategieën"""
    
    def __init__(self, initial_capital=10000):
        self.initial_capital = initial_capital
        self.results = {}
        self.comparisons = {}
    
    def fetch_historical_data(self, symbol, start_date, end_date, interval='1h'):
        """Haal historische data op van Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval=interval)
            
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            return df
        except Exception as e:
            print(f"Error fetching data: {e}")
            return self.generate_test_data(start_date, end_date)
    
    def generate_test_data(self, start_date, end_date, base_price=50000):
        """Genereer test data voor backtesting"""
        dates = pd.date_range(start=start_date, end=end_date, freq='1H')
        n_periods = len(dates)
        
        np.random.seed(42)
        returns = np.random.normal(0.0001, 0.02, n_periods)
        prices = base_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices * 0.999,
            'high': prices * 1.005,
            'low': prices * 0.995,
            'close': prices,
            'volume': np.random.lognormal(8, 1, n_periods)
        })
        
        df.set_index('timestamp', inplace=True)
        return df
    
    def backtest_grid_strategy(self, data, strategy_params):
        """Backtest een grid trading strategie"""
        df = data.copy()
        
        # Strategy parameters
        grid_range_pct = strategy_params.get('grid_range_pct', 0.10)
        num_grids = strategy_params.get('num_grids', 20)
        order_size_usdt = strategy_params.get('order_size', 100)
        fee_rate = strategy_params.get('fee_rate', 0.001)
        
        # Initialiseer portfolio
        portfolio = {
            'cash': self.initial_capital,
            'positions': 0,
            'total_value': self.initial_capital
        }
        
        trades = []
        equity_curve = []
        
        # Voor elke tijdsstap
        for i in range(len(df)):
            current_price = df['close'].iloc[i]
            
            # Bereken grid rond huidige prijs
            lower = current_price * (1 - grid_range_pct)
            upper = current_price * (1 + grid_range_pct)
            grid_levels = np.linspace(lower, upper, num_grids)
            
            # Check voor grid hits
            for grid_price in grid_levels:
                # Simuleer order matching
                if abs(current_price - grid_price) / grid_price < 0.001:
                    
                    if current_price <= grid_price:
                        # Buy order
                        amount = order_size_usdt / grid_price
                        cost = amount * grid_price * (1 + fee_rate)
                        
                        if portfolio['cash'] >= cost:
                            portfolio['cash'] -= cost
                            portfolio['positions'] += amount
                            
                            trades.append({
                                'timestamp': df.index[i],
                                'side': 'buy',
                                'price': grid_price,
                                'amount': amount,
                                'fee': amount * grid_price * fee_rate,
                                'profit': 0
                            })
                    
                    else:
                        # Sell order
                        if portfolio['positions'] > 0:
                            sell_amount = min(portfolio['positions'], order_size_usdt / grid_price)
                            revenue = sell_amount * grid_price * (1 - fee_rate)
                            portfolio['cash'] += revenue
                            portfolio['positions'] -= sell_amount
                            
                            # Bereken profit (vereenvoudigd)
                            avg_buy_price = sum([t['price'] for t in trades if t['side'] == 'buy']) / len([t for t in trades if t['side'] == 'buy']) if any(t['side'] == 'buy' for t in trades) else grid_price
                            profit = (grid_price - avg_buy_price) * sell_amount
                            
                            trades.append({
                                'timestamp': df.index[i],
                                'side': 'sell',
                                'price': grid_price,
                                'amount': sell_amount,
                                'fee': sell_amount * grid_price * fee_rate,
                                'profit': profit
                            })
            
            # Update portfolio waarde
            portfolio_value = portfolio['cash'] + portfolio['positions'] * current_price
            equity_curve.append({
                'timestamp': df.index[i],
                'value': portfolio_value,
                'price': current_price
            })
        
        # Bereken metrics
        results = self.calculate_metrics(pd.DataFrame(equity_curve), trades)
        
        return {
            'equity_curve': equity_curve,
            'trades': trades,
            'portfolio': portfolio,
            'metrics': results
        }
    
    def calculate_metrics(self, equity_curve_df, trades):
        """Bereken prestatiemetrics"""
        if len(equity_curve_df) < 2:
            return {}
        
        returns = equity_curve_df['value'].pct_change().dropna()
        
        # Basis metrics
        total_return = (equity_curve_df['value'].iloc[-1] / equity_curve_df['value'].iloc[0] - 1) * 100
        
        # Sharpe ratio
        sharpe = 0
        if len(returns) > 1 and returns.std() != 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(365*24)
        
        # Max drawdown
        rolling_max = equity_curve_df['value'].expanding().max()
        drawdown = (equity_curve_df['value'] - rolling_max) / rolling_max
        max_dd = drawdown.min() * 100
        
        # Trade metrics
        if trades:
            trades_df = pd.DataFrame(trades)
            if 'profit' in trades_df.columns:
                win_rate = (trades_df['profit'] > 0).mean() * 100
                profit_factor = abs(trades_df[trades_df['profit'] > 0]['profit'].sum() / trades_df[trades_df['profit'] < 0]['profit'].sum()) if trades_df[trades_df['profit'] < 0]['profit'].sum() != 0 else float('inf')
            else:
                win_rate = profit_factor = 0
        else:
            win_rate = profit_factor = 0
        
        return {
            'total_return_pct': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd,
            'win_rate_pct': win_rate,
            'profit_factor': profit_factor,
            'total_trades': len(trades)
        }
    
    def optimize_parameters(self, data, param_grid):
        """Voer parameter optimalisatie uit"""
        best_params = None
        best_metric = -np.inf
        results = []
        
        for params in self.param_generator(param_grid):
            result = self.backtest_grid_strategy(data, params)
            metric = result['metrics'].get('sharpe_ratio', 0)
            
            results.append({
                'params': params,
                'metrics': result['metrics']
            })
            
            if metric > best_metric:
                best_metric = metric
                best_params = params
        
        return best_params, results
    
    def param_generator(self, param_grid):
        """Genereer parameter combinaties"""
        from itertools import product
        
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        
        for combination in product(*values):
            yield dict(zip(keys, combination))

# Voorbeeld gebruik
if __name__ == "__main__":
    backtester = Backtester()
    data = backtester.fetch_historical_data("BTC-USD", "2024-01-01", "2024-03-01")
    
    params = {
        'grid_range_pct': 0.10,
        'num_grids': 20,
        'order_size': 100,
        'fee_rate': 0.001
    }
    
    results = backtester.backtest_grid_strategy(data, params)
    print(f"Backtest result: {results['metrics']}")
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import hashlib
import hmac
import time
import json
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

class ExchangeManager:
    """Beheer meerdere cryptocurrency exchanges"""
    
    SUPPORTED_EXCHANGES = {
        'binance': {
            'spot': True,
            'futures': True,
            'margin': True,
            'requires': ['api_key', 'api_secret'],
            'class': ccxt.binance
        },
        'bybit': {
            'spot': True,
            'futures': True,
            'margin': False,
            'requires': ['api_key', 'api_secret'],
            'class': ccxt.bybit
        },
        'kucoin': {
            'spot': True,
            'futures': True,
            'margin': True,
            'requires': ['api_key', 'api_secret', 'password'],
            'class': ccxt.kucoin
        },
        'okx': {
            'spot': True,
            'futures': True,
            'margin': True,
            'requires': ['api_key', 'api_secret', 'password'],
            'class': ccxt.okx
        },
        'coinbase': {
            'spot': True,
            'futures': False,
            'margin': False,
            'requires': ['api_key', 'api_secret'],
            'class': ccxt.coinbase
        },
        'huobi': {
            'spot': True,
            'futures': True,
            'margin': True,
            'requires': ['api_key', 'api_secret'],
            'class': ccxt.huobi
        },
        'gateio': {
            'spot': True,
            'futures': True,
            'margin': True,
            'requires': ['api_key', 'api_secret'],
            'class': ccxt.gateio
        },
        'mexc': {
            'spot': True,
            'futures': True,
            'margin': True,
            'requires': ['api_key', 'api_secret'],
            'class': ccxt.mexc
        }
    }
    
    def __init__(self):
        self.exchanges = {}
        self.active_exchange = None
        self.balances = {}
        self.positions = {}
        
    def add_exchange(self, exchange_name: str, credentials: dict, exchange_type: str = 'spot'):
        """Voeg een exchange toe met credentials"""
        if exchange_name not in self.SUPPORTED_EXCHANGES:
            raise ValueError(f"Exchange {exchange_name} niet ondersteund")
        
        exchange_info = self.SUPPORTED_EXCHANGES[exchange_name]
        
        # Controleer vereiste credentials
        for req in exchange_info['requires']:
            if req not in credentials:
                raise ValueError(f"{req} is vereist voor {exchange_name}")
        
        try:
            # Maak exchange instance
            exchange_class = exchange_info['class']
            
            config = {
                'apiKey': credentials.get('api_key'),
                'secret': credentials.get('api_secret'),
                'password': credentials.get('password'),
                'enableRateLimit': True
            }
            
            if exchange_type == 'futures' and exchange_info['futures']:
                config['options'] = {'defaultType': 'future'}
            elif exchange_type == 'margin' and exchange_info['margin']:
                config['options'] = {'defaultType': 'margin'}
            
            exchange = exchange_class(config)
            
            # Test connectie
            exchange.fetch_time()
            
            self.exchanges[exchange_name] = {
                'instance': exchange,
                'type': exchange_type,
                'credentials': credentials
            }
            
            self.active_exchange = exchange_name
            
            print(f"✅ Exchange {exchange_name} succesvol toegevoegd")
            return True
            
        except Exception as e:
            print(f"❌ Fout bij toevoegen {exchange_name}: {str(e)}")
            return False
    
    def remove_exchange(self, exchange_name: str):
        """Verwijder een exchange"""
        if exchange_name in self.exchanges:
            del self.exchanges[exchange_name]
            if self.active_exchange == exchange_name:
                self.active_exchange = list(self.exchanges.keys())[0] if self.exchanges else None
            return True
        return False
    
    def switch_exchange(self, exchange_name: str):
        """Wissel naar een andere exchange"""
        if exchange_name in self.exchanges:
            self.active_exchange = exchange_name
            return True
        return False
    
    def get_active_exchange(self):
        """Haal actieve exchange op"""
        if self.active_exchange:
            return self.exchanges[self.active_exchange]['instance']
        return None
    
    def fetch_balance(self, exchange_name: str = None):
        """Haal balans op van een specifieke exchange"""
        exchange_name = exchange_name or self.active_exchange
        
        if exchange_name not in self.exchanges:
            return None
        
        try:
            exchange = self.exchanges[exchange_name]['instance']
            balance = exchange.fetch_balance()
            
            # Format balans
            formatted_balance = {
                'total': balance.get('total', {}),
                'free': balance.get('free', {}),
                'used': balance.get('used', {}),
                'timestamp': datetime.now().isoformat()
            }
            
            self.balances[exchange_name] = formatted_balance
            return formatted_balance
            
        except Exception as e:
            print(f"Fout bij ophalen balans van {exchange_name}: {str(e)}")
            return None
    
    def fetch_all_balances(self):
        """Haal balansen op van alle exchanges"""
        all_balances = {}
        
        for exchange_name in self.exchanges:
            balance = self.fetch_balance(exchange_name)
            if balance:
                all_balances[exchange_name] = balance
        
        return all_balances
    
    def get_total_portfolio_value(self, quote_currency='USDT'):
        """Bereken totale portefeuille waarde over alle exchanges"""
        total_value = 0
        portfolio_details = {}
        
        for exchange_name, balance in self.balances.items():
            exchange_value = 0
            exchange_details = []
            
            for currency, amount in balance['total'].items():
                if amount > 0:
                    try:
                        # Haal ticker op voor prijsconversie
                        if currency != quote_currency:
                            symbol = f"{currency}/{quote_currency}"
                            ticker = self.fetch_ticker(symbol, exchange_name)
                            if ticker:
                                value = amount * ticker['last']
                                exchange_value += value
                                exchange_details.append({
                                    'currency': currency,
                                    'amount': amount,
                                    'price': ticker['last'],
                                    'value': value
                                })
                        else:
                            exchange_value += amount
                            exchange_details.append({
                                'currency': currency,
                                'amount': amount,
                                'price': 1,
                                'value': amount
                            })
                    except:
                        continue
            
            portfolio_details[exchange_name] = {
                'value': exchange_value,
                'details': exchange_details
            }
            total_value += exchange_value
        
        return {
            'total_value': total_value,
            'breakdown': portfolio_details,
            'quote_currency': quote_currency
        }
    
    def fetch_ticker(self, symbol: str, exchange_name: str = None):
        """Haal ticker informatie op"""
        exchange_name = exchange_name or self.active_exchange
        
        if exchange_name not in self.exchanges:
            return None
        
        try:
            exchange = self.exchanges[exchange_name]['instance']
            ticker = exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Fout bij ophalen ticker {symbol} van {exchange_name}: {str(e)}")
            return None
    
    def create_order(self, symbol: str, order_type: str, side: str, amount: float, 
                    price: float = None, exchange_name: str = None, params: dict = None):
        """Plaats een order op een exchange"""
        exchange_name = exchange_name or self.active_exchange
        
        if exchange_name not in self.exchanges:
            return None
        
        try:
            exchange = self.exchanges[exchange_name]['instance']
            
            order_params = params or {}
            
            if self.exchanges[exchange_name]['type'] == 'futures':
                order_params['type'] = 'future'
            
            order = exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price,
                params=order_params
            )
            
            return order
            
        except Exception as e:
            print(f"Fout bij plaatsen order op {exchange_name}: {str(e)}")
            return None
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', 
                   limit: int = 100, exchange_name: str = None):
        """Haal OHLCV data op"""
        exchange_name = exchange_name or self.active_exchange
        
        if exchange_name not in self.exchanges:
            return None
        
        try:
            exchange = self.exchanges[exchange_name]['instance']
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            return df
            
        except Exception as e:
            print(f"Fout bij ophalen OHLCV van {exchange_name}: {str(e)}")
            return None
    
    def get_exchange_info(self, exchange_name: str):
        """Haal exchange informatie op"""
        if exchange_name not in self.exchanges:
            return None
        
        exchange = self.exchanges[exchange_name]['instance']
        info = {
            'name': exchange_name,
            'type': self.exchanges[exchange_name]['type'],
            'has': exchange.has,
            'rateLimit': exchange.rateLimit,
            'timeframes': exchange.timeframes if hasattr(exchange, 'timeframes') else {},
            'markets': list(exchange.markets.keys())[:10] if hasattr(exchange, 'markets') else []
        }
        
        return info
    
    def compare_prices(self, symbol: str):
        """Vergelijk prijzen tussen alle exchanges"""
        prices = {}
        
        for exchange_name in self.exchanges:
            ticker = self.fetch_ticker(symbol, exchange_name)
            if ticker:
                prices[exchange_name] = {
                    'bid': ticker['bid'],
                    'ask': ticker['ask'],
                    'last': ticker['last'],
                    'spread': (ticker['ask'] - ticker['bid']) / ticker['bid'] * 100 if ticker['bid'] else 0
                }
        
        return prices
    
    def find_arbitrage_opportunities(self, symbol: str, min_profit_pct: float = 0.5):
        """Zoek arbitrage mogelijkheden tussen exchanges"""
        prices = self.compare_prices(symbol)
        
        opportunities = []
        
        exchanges = list(prices.keys())
        for i in range(len(exchanges)):
            for j in range(i+1, len(exchanges)):
                exch1 = exchanges[i]
                exch2 = exchanges[j]
                
                # Check voor arbitrage: kopen op laagste ask, verkopen op hoogste bid
                if prices[exch1]['ask'] < prices[exch2]['bid']:
                    profit_pct = (prices[exch2]['bid'] - prices[exch1]['ask']) / prices[exch1]['ask'] * 100
                    
                    if profit_pct > min_profit_pct:
                        opportunities.append({
                            'buy_exchange': exch1,
                            'sell_exchange': exch2,
                            'buy_price': prices[exch1]['ask'],
                            'sell_price': prices[exch2]['bid'],
                            'profit_pct': profit_pct,
                            'symbol': symbol
                        })
                
                # Omgekeerde richting
                if prices[exch2]['ask'] < prices[exch1]['bid']:
                    profit_pct = (prices[exch1]['bid'] - prices[exch2]['ask']) / prices[exch2]['ask'] * 100
                    
                    if profit_pct > min_profit_pct:
                        opportunities.append({
                            'buy_exchange': exch2,
                            'sell_exchange': exch1,
                            'buy_price': prices[exch2]['ask'],
                            'sell_price': prices[exch1]['bid'],
                            'profit_pct': profit_pct,
                            'symbol': symbol
                        })
        
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)
    
    def execute_arbitrage(self, opportunity: dict, amount: float):
        """Voer arbitrage trade uit"""
        try:
            # Stap 1: Koop op eerste exchange
            buy_order = self.create_order(
                symbol=opportunity['symbol'],
                order_type='market',
                side='buy',
                amount=amount,
                exchange_name=opportunity['buy_exchange']
            )
            
            if not buy_order:
                return None
            
            # Wacht op uitvoering
            time.sleep(2)
            
            # Stap 2: Verkoop op tweede exchange
            sell_order = self.create_order(
                symbol=opportunity['symbol'],
                order_type='market',
                side='sell',
                amount=amount,
                exchange_name=opportunity['sell_exchange']
            )
            
            if not sell_order:
                return None
            
            # Bereken resultaat
            profit = (sell_order['price'] - buy_order['price']) * amount
            fee_estimate = (buy_order['price'] + sell_order['price']) * amount * 0.001  # 0.1% fee schatting
            net_profit = profit - fee_estimate
            
            return {
                'buy_order': buy_order,
                'sell_order': sell_order,
                'profit': profit,
                'fees': fee_estimate,
                'net_profit': net_profit,
                'profit_pct': (sell_order['price'] - buy_order['price']) / buy_order['price'] * 100
            }
            
        except Exception as e:
            print(f"Fout bij arbitrage uitvoering: {str(e)}")
            return None
    
    def sync_orders_across_exchanges(self, symbol: str, grid_levels: list, 
                                   order_size: float, side: str = 'buy'):
        """Plaats grid orders op meerdere exchanges tegelijk"""
        results = {}
        
        for exchange_name in self.exchanges:
            orders = []
            
            for price in grid_levels:
                try:
                    amount = order_size / price
                    
                    order = self.create_order(
                        symbol=symbol,
                        order_type='limit',
                        side=side,
                        amount=amount,
                        price=price,
                        exchange_name=exchange_name,
                        params={'timeInForce': 'GTC'}
                    )
                    
                    if order:
                        orders.append(order)
                        
                except Exception as e:
                    print(f"Fout bij plaatsen order op {exchange_name} voor prijs {price}: {str(e)}")
            
            results[exchange_name] = {
                'orders': orders,
                'count': len(orders)
            }
        
        return results
    
    def cancel_all_orders(self, symbol: str = None, exchange_name: str = None):
        """Cancel alle orders op een exchange"""
        exchange_name = exchange_name or self.active_exchange
        
        if exchange_name not in self.exchanges:
            return False
        
        try:
            exchange = self.exchanges[exchange_name]['instance']
            
            if symbol:
                exchange.cancel_all_orders(symbol)
            else:
                exchange.cancel_all_orders()
            
            return True
            
        except Exception as e:
            print(f"Fout bij cancellen orders op {exchange_name}: {str(e)}")
            return False
    
    def get_fee_structure(self, exchange_name: str):
        """Haal fee structuur op van exchange"""
        fee_structures = {
            'binance': {
                'maker': 0.001,  # 0.1%
                'taker': 0.001,  # 0.1%
                'discount_tiers': True
            },
            'bybit': {
                'maker': 0.0001,  # 0.01%
                'taker': 0.0006,  # 0.06%
                'discount_tiers': True
            },
            'kucoin': {
                'maker': 0.001,
                'taker': 0.001,
                'discount_tiers': True
            },
            'okx': {
                'maker': 0.0008,
                'taker': 0.001,
                'discount_tiers': True
            }
        }
        
        return fee_structures.get(exchange_name, {'maker': 0.002, 'taker': 0.002})
    
    def calculate_slippage(self, symbol: str, amount: float, 
                          side: str = 'buy', exchange_name: str = None):
        """Bereken slippage voor een trade"""
        exchange_name = exchange_name or self.active_exchange
        
        ticker = self.fetch_ticker(symbol, exchange_name)
        if not ticker:
            return None
        
        order_book = self.get_order_book(symbol, exchange_name)
        if not order_book:
            return None
        
        total_cost = 0
        remaining = amount
        
        if side == 'buy':
            for price, volume in order_book['asks']:
                if remaining <= 0:
                    break
                fill_amount = min(remaining, volume)
                total_cost += fill_amount * price
                remaining -= fill_amount
        else:
            for price, volume in order_book['bids']:
                if remaining <= 0:
                    break
                fill_amount = min(remaining, volume)
                total_cost += fill_amount * price
                remaining -= fill_amount
        
        if remaining > 0:
            return None  # Niet genoeg volume
        
        avg_price = total_cost / amount
        market_price = ticker['last']
        slippage = (avg_price - market_price) / market_price * 100
        
        return {
            'avg_price': avg_price,
            'market_price': market_price,
            'slippage_pct': slippage,
            'estimated_cost': total_cost
        }

# Voorbeeld gebruik
if __name__ == "__main__":
    manager = ExchangeManager()
    
    # Voeg exchanges toe
    manager.add_exchange('binance', {
        'api_key': 'YOUR_API_KEY',
        'api_secret': 'YOUR_API_SECRET'
    })
    
    manager.add_exchange('bybit', {
        'api_key': 'YOUR_API_KEY',
        'api_secret': 'YOUR_API_SECRET'
    }, exchange_type='futures')
    
    # Haal balansen op
    balances = manager.fetch_all_balances()
    print("Balances:", json.dumps(balances, indent=2))
    
    # Vergelijk prijzen
    prices = manager.compare_prices('BTC/USDT')
    print("Price comparison:", prices)
    
    # Zoek arbitrage mogelijkheden
    opportunities = manager.find_arbitrage_opportunities('BTC/USDT', 0.3)
    print("Arbitrage opportunities:", opportunities)
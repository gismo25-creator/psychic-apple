from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import asyncio
import uuid
import jwt
from enum import Enum
import uvicorn

from grid_trading_system import GridTradingSystem
from exchange_manager import ExchangeManager
from notification_manager import NotificationManager, NotificationType

# JWT configuratie
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 uur

# Database models (vereenvoudigd - gebruik SQLAlchemy in productie)
class User(BaseModel):
    id: str
    username: str
    email: str
    hashed_password: str
    is_active: bool = True
    created_at: datetime = datetime.now()

class Trade(BaseModel):
    id: str
    user_id: str
    symbol: str
    side: str
    price: float
    amount: float
    exchange: str
    timestamp: datetime
    profit: Optional[float] = None

class GridStrategy(BaseModel):
    id: str
    user_id: str
    name: str
    symbol: str
    grid_type: str
    num_grids: int
    grid_range_pct: float
    order_size: float
    is_active: bool
    created_at: datetime
    last_updated: datetime

# Request/Response models
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str

class TradeCreate(BaseModel):
    symbol: str = "BTC/USDT"
    side: str = "buy"
    amount: float = Field(..., gt=0)
    price: Optional[float] = None
    exchange: str = "binance"

class GridStrategyCreate(BaseModel):
    name: str
    symbol: str = "BTC/USDT"
    grid_type: str = "linear"
    num_grids: int = Field(20, ge=5, le=100)
    grid_range_pct: float = Field(10.0, ge=1.0, le=50.0)
    order_size: float = Field(100.0, ge=10.0, le=10000.0)

class WebhookPayload(BaseModel):
    event: str
    data: Dict[str, Any]
    timestamp: str = datetime.now().isoformat()

# Initialize app
app = FastAPI(
    title="Grid Trading Bot API",
    description="Mobile API for Grid Trading Bot",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuratie voor mobile apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Beperk dit in productie
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# State
active_users = {}
user_sessions = {}
websocket_connections = []

# Initialize managers
exchange_manager = ExchangeManager()
notification_manager = NotificationManager()
trading_systems = {}

# Mock database (vervang met echte database)
users_db = {}
trades_db = {}
strategies_db = {}

# Helper functies
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Maak JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifieer JWT token"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id not in users_db:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# API Endpoints
@app.post("/api/auth/register", response_model=Token)
async def register(user: UserCreate):
    """Registreer nieuwe gebruiker"""
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user_id = str(uuid.uuid4())
    hashed_password = f"hashed_{user.password}"  # Gebruik bcrypt in productie
    
    new_user = User(
        id=user_id,
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    
    users_db[user_id] = new_user
    users_db[user.username] = new_user
    
    # Maak access token
    access_token = create_access_token(data={"sub": user_id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user_id
    }

@app.post("/api/auth/login", response_model=Token)
async def login(user: UserLogin):
    """Login gebruiker"""
    # Zoek gebruiker
    found_user = None
    for u in users_db.values():
        if isinstance(u, User) and u.username == user.username:
            found_user = u
            break
    
    if not found_user or found_user.hashed_password != f"hashed_{user.password}":
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Maak token
    access_token = create_access_token(data={"sub": found_user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": found_user.id
    }

@app.get("/api/user/profile")
async def get_profile(user_id: str = Depends(verify_token)):
    """Haal gebruikersprofiel op"""
    user = users_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
        "is_active": user.is_active
    }

@app.get("/api/exchanges")
async def get_exchanges(user_id: str = Depends(verify_token)):
    """Haal ondersteunde exchanges op"""
    exchanges = list(exchange_manager.SUPPORTED_EXCHANGES.keys())
    
    return {
        "exchanges": exchanges,
        "count": len(exchanges)
    }

@app.post("/api/exchanges/{exchange_name}/connect")
async def connect_exchange(
    exchange_name: str,
    credentials: Dict[str, str],
    user_id: str = Depends(verify_token)
):
    """Verbinden met exchange"""
    try:
        success = exchange_manager.add_exchange(exchange_name, credentials)
        
        if success:
            # Stuur notificatie
            notification_manager.add_notification(
                NotificationType.INFO,
                f"Exchange Connected",
                f"Successfully connected to {exchange_name}",
                priority=2,
                data={"exchange": exchange_name, "user_id": user_id}
            )
            
            return {"success": True, "message": f"Connected to {exchange_name}"}
        else:
            raise HTTPException(status_code=400, detail=f"Failed to connect to {exchange_name}")
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/portfolio")
async def get_portfolio(user_id: str = Depends(verify_token)):
    """Haal portefeuille op"""
    try:
        balances = exchange_manager.fetch_all_balances()
        portfolio = exchange_manager.get_total_portfolio_value()
        
        return {
            "balances": balances,
            "portfolio": portfolio,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/{symbol}/price")
async def get_market_price(symbol: str, user_id: str = Depends(verify_token)):
    """Haal marktprijs op"""
    ticker = exchange_manager.fetch_ticker(symbol)
    
    if not ticker:
        raise HTTPException(status_code=404, detail="Symbol not found")
    
    return {
        "symbol": symbol,
        "bid": ticker.get('bid'),
        "ask": ticker.get('ask'),
        "last": ticker.get('last'),
        "high": ticker.get('high'),
        "low": ticker.get('low'),
        "volume": ticker.get('volume'),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/trade")
async def execute_trade(
    trade: TradeCreate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token)
):
    """Voer een trade uit"""
    try:
        # Plaats order
        order = exchange_manager.create_order(
            symbol=trade.symbol,
            order_type='market' if not trade.price else 'limit',
            side=trade.side,
            amount=trade.amount,
            price=trade.price,
            exchange_name=trade.exchange
        )
        
        if not order:
            raise HTTPException(status_code=400, detail="Trade failed")
        
        # Sla trade op
        trade_id = str(uuid.uuid4())
        trade_record = Trade(
            id=trade_id,
            user_id=user_id,
            symbol=trade.symbol,
            side=trade.side,
            price=order.get('price', trade.price or 0),
            amount=trade.amount,
            exchange=trade.exchange,
            timestamp=datetime.now()
        )
        
        trades_db[trade_id] = trade_record
        
        # Stuur notificatie
        background_tasks.add_task(
            notification_manager.send_trade_notification,
            {
                'symbol': trade.symbol,
                'side': trade.side,
                'price': trade_record.price,
                'amount': trade.amount,
                'value': trade_record.price * trade.amount,
                'exchange': trade.exchange,
                'order_id': order.get('id')
            }
        )
        
        return {
            "success": True,
            "trade_id": trade_id,
            "order": order,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/trades")
async def get_trades(
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(verify_token)
):
    """Haal trade geschiedenis op"""
    user_trades = [
        trade for trade in trades_db.values() 
        if trade.user_id == user_id
    ]
    
    # Sorteer op timestamp
    user_trades.sort(key=lambda x: x.timestamp, reverse=True)
    
    # Pagination
    paginated_trades = user_trades[offset:offset + limit]
    
    return {
        "trades": [
            {
                "id": trade.id,
                "symbol": trade.symbol,
                "side": trade.side,
                "price": trade.price,
                "amount": trade.amount,
                "exchange": trade.exchange,
                "timestamp": trade.timestamp.isoformat(),
                "profit": trade.profit
            }
            for trade in paginated_trades
        ],
        "total": len(user_trades),
        "limit": limit,
        "offset": offset
    }

@app.post("/api/strategies")
async def create_strategy(
    strategy: GridStrategyCreate,
    user_id: str = Depends(verify_token)
):
    """Maak nieuwe grid strategie"""
    strategy_id = str(uuid.uuid4())
    
    new_strategy = GridStrategy(
        id=strategy_id,
        user_id=user_id,
        name=strategy.name,
        symbol=strategy.symbol,
        grid_type=strategy.grid_type,
        num_grids=strategy.num_grids,
        grid_range_pct=strategy.grid_range_pct,
        order_size=strategy.order_size,
        is_active=False,
        created_at=datetime.now(),
        last_updated=datetime.now()
    )
    
    strategies_db[strategy_id] = new_strategy
    
    # Initialize trading system voor deze strategie
    trading_system = GridTradingSystem(mode='simulation', symbol=strategy.symbol)
    trading_systems[strategy_id] = trading_system
    
    return {
        "success": True,
        "strategy_id": strategy_id,
        "strategy": new_strategy
    }

@app.put("/api/strategies/{strategy_id}/activate")
async def activate_strategy(
    strategy_id: str,
    user_id: str = Depends(verify_token)
):
    """Activeer een strategie"""
    strategy = strategies_db.get(strategy_id)
    
    if not strategy or strategy.user_id != user_id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    strategy.is_active = True
    strategy.last_updated = datetime.now()
    
    # Start trading strategie
    trading_system = trading_systems.get(strategy_id)
    if trading_system:
        params = {
            'grid_type': strategy.grid_type,
            'num_grids': strategy.num_grids,
            'grid_range_pct': strategy.grid_range_pct / 100,
            'order_size': strategy.order_size
        }
        
        # Start in background
        import threading
        thread = threading.Thread(
            target=trading_system.run_strategy,
            args=(params,),
            daemon=True
        )
        thread.start()
    
    # Stuur notificatie
    notification_manager.add_notification(
        NotificationType.INFO,
        "Strategy Activated",
        f"Strategy '{strategy.name}' has been activated",
        priority=2,
        data={"strategy_id": strategy_id, "user_id": user_id}
    )
    
    return {"success": True, "message": "Strategy activated"}

@app.get("/api/strategies")
async def get_strategies(user_id: str = Depends(verify_token)):
    """Haal alle strategieën op"""
    user_strategies = [
        strategy for strategy in strategies_db.values()
        if strategy.user_id == user_id
    ]
    
    return {
        "strategies": [
            {
                "id": s.id,
                "name": s.name,
                "symbol": s.symbol,
                "grid_type": s.grid_type,
                "num_grids": s.num_grids,
                "grid_range_pct": s.grid_range_pct,
                "order_size": s.order_size,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat(),
                "last_updated": s.last_updated.isoformat()
            }
            for s in user_strategies
        ]
    }

@app.get("/api/strategies/{strategy_id}/performance")
async def get_strategy_performance(
    strategy_id: str,
    user_id: str = Depends(verify_token)
):
    """Haal strategie performance op"""
    strategy = strategies_db.get(strategy_id)
    
    if not strategy or strategy.user_id != user_id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    trading_system = trading_systems.get(strategy_id)
    
    if not trading_system:
        return {"performance": {}, "message": "No performance data available"}
    
    return {
        "performance": trading_system.performance_metrics,
        "portfolio": trading_system.portfolio,
        "total_trades": len(trading_system.trades)
    }

@app.get("/api/notifications")
async def get_notifications(
    limit: int = 20,
    user_id: str = Depends(verify_token)
):
    """Haal notificaties op"""
    history = notification_manager.get_notification_history(limit=limit)
    
    return {
        "notifications": [
            {
                "type": n.type.value,
                "title": n.title,
                "message": n.message,
                "timestamp": n.timestamp.isoformat(),
                "priority": n.priority,
                "data": n.data
            }
            for n in history
        ]
    }

@app.post("/api/webhook/{exchange}")
async def webhook_receiver(
    exchange: str,
    payload: WebhookPayload,
    user_id: str = Depends(verify_token)
):
    """Ontvang webhooks van exchanges"""
    # Log webhook
    print(f"Webhook received from {exchange}: {payload.event}")
    
    # Verwerk webhook gebaseerd op event type
    if payload.event == "order_filled":
        # Update trade status
        pass
    elif payload.event == "balance_updated":
        # Update portfolio
        pass
    
    # Stuur notificatie
    notification_manager.add_notification(
        NotificationType.INFO,
        f"Webhook: {payload.event}",
        f"Webhook received from {exchange}",
        priority=1,
        data=payload.data
    )
    
    return {"success": True, "message": "Webhook processed"}

@app.get("/api/arbitrage/opportunities")
async def get_arbitrage_opportunities(
    symbol: str = "BTC/USDT",
    min_profit: float = 0.3,
    user_id: str = Depends(verify_token)
):
    """Zoek arbitrage mogelijkheden"""
    try:
        opportunities = exchange_manager.find_arbitrage_opportunities(
            symbol=symbol,
            min_profit_pct=min_profit
        )
        
        return {
            "opportunities": opportunities,
            "count": len(opportunities),
            "symbol": symbol,
            "min_profit_pct": min_profit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket voor real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket voor real-time updates"""
    await manager.connect(websocket)
    
    try:
        while True:
            # Ontvang bericht van client
            data = await websocket.receive_text()
            
            # Verwerk bericht
            try:
                message = json.loads(data)
                action = message.get("action")
                
                if action == "subscribe_price":
                    symbol = message.get("symbol", "BTC/USDT")
                    # Start price updates
                    asyncio.create_task(send_price_updates(websocket, symbol))
                
                elif action == "subscribe_portfolio":
                    # Start portfolio updates
                    asyncio.create_task(send_portfolio_updates(websocket))
                
                elif action == "unsubscribe":
                    # Stop updates
                    pass
                    
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def send_price_updates(websocket: WebSocket, symbol: str):
    """Stuur real-time price updates"""
    while True:
        try:
            ticker = exchange_manager.fetch_ticker(symbol)
            if ticker:
                update = {
                    "type": "price_update",
                    "symbol": symbol,
                    "price": ticker['last'],
                    "bid": ticker['bid'],
                    "ask": ticker['ask'],
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send_text(json.dumps(update))
            
            await asyncio.sleep(1)  # Update elke seconde
            
        except:
            break

async def send_portfolio_updates(websocket: WebSocket):
    """Stuur portfolio updates"""
    while True:
        try:
            portfolio = exchange_manager.get_total_portfolio_value()
            update = {
                "type": "portfolio_update",
                "total_value": portfolio['total_value'],
                "breakdown": portfolio['breakdown'],
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send_text(json.dumps(update))
            
            await asyncio.sleep(5)  # Update elke 5 seconden
            
        except:
            break

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "services": {
            "exchange_manager": len(exchange_manager.exchanges) > 0,
            "notification_manager": True,
            "api": True
        }
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialiseer bij startup"""
    print("🚀 Grid Trading Bot API starting...")
    
    # Start notification scheduler
    notification_manager.start_scheduler()
    
    # Stuur startup notificatie
    notification_manager.add_notification(
        NotificationType.INFO,
        "API Started",
        "Grid Trading Bot API has been started successfully",
        priority=1
    )

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup bij shutdown"""
    notification_manager.stop_scheduler()
    print("🛑 Grid Trading Bot API shutting down...")

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
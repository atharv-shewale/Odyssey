"""
Odyssey v2 - Gateway API Server
FastAPI REST + WebSocket bridge between frontend and backend services
Reads from Redis/QuestDB to serve real-time trading data

Usage:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from pydantic import BaseModel
import prometheus_client
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import shared libs
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

SHARED_PYTHON = os.path.join(PROJECT_ROOT, "shared", "python")
sys.path.insert(0, SHARED_PYTHON)
sys.path.insert(0, CURRENT_DIR)  # needed so 'engine' sub-module resolves

from redis_client import RedisClient
from questdb_client import QuestDBClient
from logger import OdysseyLogger

# Pre-import the engine at startup to catch issues early
try:
    from engine.financial_analysis_engine import FinancialAnalysisEngine as _FAE
    _fae_available = True
except Exception as _e:
    _fae_available = False
    print(f"[WARN] FinancialAnalysisEngine unavailable: {_e}")

logger = OdysseyLogger('gateway')

# ===========================================
# SECURITY SETUP
# ===========================================
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback_secret_for_dev_only")
ALGORITHM = "HS256"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def verify_token(token: str = Depends(oauth2_scheme)):
    """Dependency to check JWT validity on protected routes"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return True

# ===========================================
# APP SETUP
# ===========================================
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Odyssey v2 Gateway",
    description="REST + WebSocket API for the Odyssey trading platform",
    version="2.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-init connections (avoid crash if Redis/QuestDB not running)
_redis: Optional[RedisClient] = None
_qdb: Optional[QuestDBClient] = None


def get_redis() -> Optional[RedisClient]:
    global _redis
    if _redis is None:
        try:
            _redis = RedisClient()
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
    return _redis


def get_qdb() -> Optional[QuestDBClient]:
    global _qdb
    if _qdb is None:
        try:
            _qdb = QuestDBClient()
        except Exception as e:
            logger.error(f"QuestDB connection failed: {e}")
    return _qdb


# ===========================================
# AUTH ROUTES
# ===========================================

class UserRegister(BaseModel):
    username: str
    password: str

@app.post("/api/auth/register")
@limiter.limit("5/minute")
async def register_user(request: Request, user_data: UserRegister):
    r = get_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    if len(user_data.password) < 4:
        raise HTTPException(status_code=400, detail="Password too short")
        
    user_key = f"user:{user_data.username}"
    if r.get_cache(user_key):
        raise HTTPException(status_code=400, detail="Username already exists")
        
    hashed_pw = pwd_context.hash(user_data.password)
    r.set_cache(user_key, {"password_hash": hashed_pw})
    
    return {"status": "success", "message": "User registered successfully"}

@app.post("/api/auth/token")
@limiter.limit("10/minute")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    username = form_data.username
    password = form_data.password
    
    r = get_redis()
    user_record = r.get_cache(f"user:{username}") if r else None
    
    is_valid = False
    if user_record and "password_hash" in user_record:
        is_valid = verify_password(password, user_record["password_hash"])
    elif username == "admin":
        admin_hash = pwd_context.hash(ADMIN_PASSWORD)
        is_valid = verify_password(password, admin_hash)
        
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": username})
    return {"access_token": access_token, "token_type": "bearer"}

# ===========================================
# REST API (Protected)
# ===========================================

@app.get("/api/health")
@limiter.limit("60/minute")
async def health_check(request: Request):
    """Unprotected route for structural pinging"""
    redis_health = get_redis().ping() if get_redis() else False
    return {"status": "healthy", "redis_connected": redis_health}

@app.get("/api/account")
async def get_account_info(token: bool = Depends(verify_token)):
    r = get_redis()
    if not r:
        return {"error": "Redis unavailable"}

    equity = r.get_cache("account:equity")
    balance = r.get_cache("account:balance")
    profit = r.get_cache("account:profit")

    return {
        "balance": float(balance) if balance else 100000.0,
        "equity": float(equity) if equity else 100000.0,
        "profit": float(profit) if profit else 0.0,
        "currency": "USD",
        "updated_at": datetime.utcnow().isoformat(),
    }


# ===========================================
# SIGNALS
# ===========================================
@app.get("/api/signals")
async def get_ml_signals(token: bool = Depends(verify_token)):
    r = get_redis()
    if not r: return {"signals": {}}
    
    signals = {}
    for symbol in ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY']:
        data = r.get_cache(f"predictions:{symbol}:latest")
        if data:
            signals[symbol] = data
            
    return {"signals": signals}


# ===========================================
# PREDICTIONS
# ===========================================
@app.get("/api/predictions/{symbol}")
async def get_prediction(symbol: str):
    r = get_redis()
    if not r:
        return {"error": "Redis unavailable"}

    pred = r.get_prediction(symbol)
    if pred:
        pred['symbol'] = symbol
        return pred
    return {"symbol": symbol, "prediction": None}


# ===========================================
# POSITIONS
# ===========================================
@app.get("/api/positions")
async def get_positions(token: bool = Depends(verify_token)):
    r = get_redis()
    if not r:
        return {"positions": [], "count": 0}

    # Read from mock broker's synced Redis key
    mock_positions = r.get_cache("mock:positions:live")
    if mock_positions:
        return {"positions": mock_positions, "count": len(mock_positions)}

    # Fallback: scan old execution keys
    positions = []
    ALL_SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDINR', 'NIFTY50', 'SENSEX', 'RELIANCE', 'INFY']
    for symbol in ALL_SYMBOLS:
        exec_result = r.get_cache(f"executions:{symbol}:latest")
        if exec_result and exec_result.get('status') == 'FILLED':
            positions.append({
                'symbol': symbol,
                'action': exec_result.get('action', 'BUY'),
                'volume': exec_result.get('volume', 0),
                'entry_price': exec_result.get('price', 0),
                'pnl': 0.0,
                'status': 'OPEN',
            })

    return {"positions": positions, "count": len(positions)}


@app.get("/api/trades/history")
async def get_trade_history(token: bool = Depends(verify_token), limit: int = 50):
    """Return closed trade history from the mock broker ledger."""
    r = get_redis()
    if not r:
        # Fallback: read directly from JSON file
        import os, json
        state_file = os.path.join(PROJECT_ROOT, "mock_account_state.json")
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state = json.load(f)
            history = list(reversed(state.get('history', [])[-limit:]))
            return {"trades": history, "count": len(history)}
        return {"trades": [], "count": 0}

    history = r.get_cache("mock:trade_history") or []
    return {"trades": history[:limit], "count": len(history)}


# ===========================================
# SENTIMENT
# ===========================================
@app.get("/api/sentiment")
async def get_sentiment():
    r = get_redis()
    if not r:
        return {"error": "Redis unavailable"}

    summary = r.get_cache("sentiment:summary")
    if summary:
        return summary
    return {"currencies": {}, "pairs": {}, "headlines_processed": 0}


@app.get("/api/risk/rejections")
async def get_risk_rejections():
    r = get_redis()
    if not r:
        return {"rejections": []}

    rejections = []
    for symbol in ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY']:
        rej = r.get_cache(f"risk:rejections:{symbol}:latest")
        if rej:
            rejections.append(rej)
    return {"rejections": rejections}


# ===========================================
# MARKET DATA
# ===========================================
@app.get("/api/market/{symbol}")
async def get_market_data(symbol: str, token: bool = Depends(verify_token)):
    """Fetch real-time historical candles from QuestDB with a mock failover."""
    from datetime import timedelta
    import random
    
    # 1. Attempt to fetch from QuestDB
    q = get_qdb()
    if q:
        try:
            # Force symbols to upper case for QuestDB matching
            search_symbol = symbol.upper()
            
            # Get latest 100 minutes of data
            candles = q.get_recent_candles(search_symbol, limit=100)
            if candles and len(candles) > 0:
                # Format for frontend (sort chronologically)
                history = []
                for c in sorted(candles, key=lambda x: x['timestamp']):
                    history.append({
                        "time": c['timestamp'].isoformat() if hasattr(c['timestamp'], 'isoformat') else str(c['timestamp']),
                        "open": float(c['open']),
                        "high": float(c['high']),
                        "low": float(c['low']),
                        "close": float(c['close']),
                        "volume": float(c.get('volume', 0))
                    })
                logger.info(f"Served {len(history)} real candles from QuestDB for {symbol}.")
                return {"symbol": symbol, "history": history, "source": "QuestDB"}
        except Exception as e:
            logger.error(f"QuestDB candle fetch failed: {e}")
    
    # 2. Failover: Generate dummy data if QuestDB is empty or offline
    logger.warning(f"QuestDB empty or offline. Serving mock simulation for {symbol}.")
    base_price = 1950.0 if 'XAU' in symbol else 1.0850 if 'EUR' in symbol else 75.0
    volatility = 2.5 if 'XAU' in symbol else 0.0015
    
    history = []
    current_time = datetime.utcnow() - timedelta(minutes=100)
    current_price = base_price
    
    for _ in range(100):
        open_p = current_price
        close_p = open_p + random.uniform(-volatility, volatility)
        high_p = max(open_p, close_p) + random.uniform(0, volatility/2)
        low_p = min(open_p, close_p) - random.uniform(0, volatility/2)
        
        history.append({
            "time": current_time.isoformat(),
            "open": round(open_p, 5),
            "high": round(high_p, 5),
            "low": round(low_p, 5),
            "close": round(close_p, 5)
        })
        
        current_price = close_p
        current_time += timedelta(minutes=1)
        
    return {"symbol": symbol, "history": history, "source": "MockSimulator"}


# ===========================================
# RISK METRICS
# ===========================================
@app.get("/api/risk")
async def get_risk():
    r = get_redis()
    if not r:
        return {"error": "Redis unavailable"}

    metrics = r.get_all_risk_metrics("default")
    pos_count = r.get_cache("positions:count")

    return {
        "max_drawdown": metrics.get("max_drawdown", 0.0),
        "daily_pnl": metrics.get("daily_pnl", 0.0),
        "var_95": metrics.get("var_95", 0.0),
        "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
        "exposure": metrics.get("exposure", 0.0),
        "open_positions": int(pos_count) if pos_count else 0,
        "max_positions": 5,
    }


# ===========================================
# FEATURES
# ===========================================
@app.get("/api/features/{symbol}")
async def get_features(symbol: str):
    r = get_redis()
    if not r:
        return {"error": "Redis unavailable"}

    features = r.get_latest_features(symbol)
    return {"symbol": symbol, "features": features}


# ===========================================
# WEBSOCKET â€” live streaming
# ===========================================
# ===========================================
# FINANCIAL ANALYSIS (NEW)
# ===========================================
@app.get("/api/analysis/detail/{symbol}")
async def get_analysis_detail(symbol: str, token: bool = Depends(verify_token)):
    r = get_redis()
    if not r: return {"error": "Redis unavailable"}
    
    signal = r.get_cache(f"predictions:{symbol}:latest")
    sentiment = r.get_cache("sentiment:summary")
    
    if not signal:
        # Fallback to allow modal to render offline/without live ML predictions
        signal = {'action': 'HOLD', 'confidence': 0.5, 'percentile': 50, 'z_score': 0, 'regime_cluster': 0}
        
    try:
        from engine.financial_analysis_engine import FinancialAnalysisEngine
        engine = FinancialAnalysisEngine()
        detail = engine.generate_deep_dive(symbol, signal, sentiment)
        return detail
    except ImportError as e:
        return {"error": f"Engine module missing: {e}"}


@app.get("/api/market/mood")
async def get_market_mood():
    r = get_redis()
    if not r: return {"mood": "Offline"}
    
    # Check if AI model is still downloading/loading
    status = r.get_cache("sentiment:status")
    if status == "LOADING":
        return {"mood": "Model Synchronizing..."}
    
    sentiment = r.get_cache("sentiment:summary")
    if not sentiment: return {"mood": "Neutral / Awaiting Data"}
    
    try:
        from engine.financial_analysis_engine import FinancialAnalysisEngine
        return {"mood": FinancialAnalysisEngine.get_market_mood(sentiment)}
    except Exception:
        return {"mood": "Neutral / Live"}


@app.get("/api/market/macro")
async def get_market_macro():
    """Fetch AlphaVantage Macro Intelligence from Redis."""
    r = get_redis()
    if not r: return {"error": "Redis Offline"}
    
    status = r.get_cache("macro:market_status")
    sectors = r.get_cache("macro:sector_performance")
    
    # High-quality fallback for UI if Enricher hasn't run yet
    if not status:
        status = {
            "global_mood": "Neutral / Live",
            "spy_change": 0.05,
            "timestamp": datetime.now().isoformat(),
            "source": "Terminal Cache"
        }
    if not sectors:
        sectors = {
            "Technology": "0.15%",
            "Energy": "-0.05%",
            "Financials": "0.02%",
            "Healthcare": "0.11%"
        }
    
    return {
        "status": status,
        "sectors": sectors
    }


# ===========================================
# BACKTESTING (RESEARCH GRADE)
# ===========================================
@app.post("/api/backtest/run")
async def run_backtest(
    symbol: str = "EURUSD",
    timeframe: str = "D1",
    period_days: int = 365,
    wfo_splits: int = 5,
    token: bool = Depends(verify_token)
):
    """Trigger a full WFO + statistical backtest. Runs async."""
    import asyncio
    import sys
    import os

    # Run in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()

    def _run():
        try:
            bt_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backtesting'))
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
            from backtesting.backtester import SimpleBacktester
            
            # AUTO-DISCOVERY: Check if requested timeframe exists, otherwise fallback to any available
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'historical')
            available = [f for f in os.listdir(data_dir) if symbol in f and f.endswith('.csv')]
            
            final_tf = timeframe
            if not any(f"_{timeframe}.csv" in f for f in available):
                if any("_H1.csv" in f for f in available): final_tf = "H1"
                elif any("_M1.csv" in f for f in available): final_tf = "M1"
                elif any("_M5.csv" in f for f in available): final_tf = "M5"
                logger.info(f"Backtest: {symbol}_{timeframe} not found. Auto-adjusting to {final_tf}.")

            bt = SimpleBacktester()
            result = bt.run_full(
                symbol=symbol, timeframe=final_tf,
                period_days=period_days, wfo_splits=wfo_splits
            )
            return result
        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return {"error": str(e)}

    result = await loop.run_in_executor(None, _run)

    # Strip non-serializable keys
    clean = {k: v for k, v in result.items() if k not in ('_trade_returns', 'report_path')}
    return {"status": "complete", "symbol": symbol, "timeframe": timeframe, "metrics": clean}


@app.get("/api/backtest/latest/{symbol}")
async def get_backtest_latest(symbol: str):
    """Return the most recent backtest JSON for the dashboard panel."""
    import os, json

    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backtesting', 'reports'))
    metrics_path = os.path.join(reports_dir, f'latest_{symbol}.json')
    stats_path = os.path.join(reports_dir, f'stats_{symbol}.json')

    if not os.path.exists(metrics_path):
        return {"error": f"No backtest results found for {symbol}. Run a backtest first."}

    with open(metrics_path) as f:
        metrics = json.load(f)

    stats = {}
    if os.path.exists(stats_path):
        with open(stats_path) as f:
            stats = json.load(f)

    return {"symbol": symbol, "metrics": metrics, "statistical_validation": stats}


@app.get("/api/backtest/reports")
async def list_backtest_reports():
    """List all available backtest report files."""
    import os
    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backtesting', 'reports'))
    if not os.path.exists(reports_dir):
        return {"reports": []}
    files = [f for f in os.listdir(reports_dir) if f.endswith('.html')]
    return {"reports": sorted(files, reverse=True)[:20]}


# ===========================================
# WEBSOCKET — live streaming (Enhanced Dual-Market)
# ===========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                pass


ws_manager = ConnectionManager()


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            r = get_redis()
            if not r:
                await asyncio.sleep(2)
                continue

            # Categorized symbols
            forex_sym = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY']
            india_sym = ['USDINR', 'NIFTY50', 'SENSEX', 'BANKNIFTY', 'RELIANCE.NS', 'INFY.NS']
            all_sym = forex_sym + india_sym

            update = {"type": "update", "timestamp": datetime.utcnow().isoformat()}

            # 1. Signals grouped by Market
            signals_forex = []
            signals_india = []
            for symbol in all_sym:
                sig = r.get_cache(f"predictions:{symbol}:latest")
                if sig:
                    sig['symbol'] = symbol
                    if symbol in forex_sym: signals_forex.append(sig)
                    else: signals_india.append(sig)
            
            update["markets"] = {
                "forex": {"signals": signals_forex},
                "india": {"signals": signals_india}
            }

            # 2. Account State
            equity = r.get_cache("account:equity") or 100000.0
            balance = r.get_cache("account:balance") or 100000.0
            update["account"] = {
                "balance": float(balance),
                "equity": float(equity),
                "profit": float(r.get_cache("account:profit") or 0.0),
                "margin_free": float(r.get_cache("account:margin_free") or balance)
            }

            # 3. Sentiment & Market Mood
            sentiment = r.get_cache("sentiment:summary")
            if sentiment:
                update["sentiment"] = sentiment
                try:
                    from engine.financial_analysis_engine import FinancialAnalysisEngine
                    update["market_mood"] = FinancialAnalysisEngine.get_market_mood(sentiment)
                except Exception:
                    update["market_mood"] = "Neutral / Scanning"
            else:
                update["market_mood"] = "Awaiting Sentiment Feed"

            # 4. Risk & Performance
            risk_data = r.get_all_risk_metrics("default")
            update["risk"] = {
                "daily_pnl": float(risk_data.get("daily_pnl", 0.0)),
                "var_99": float(risk_data.get("mc_var_99", 0.0)),
                "exposure": float(risk_data.get("exposure", 0.0))
            }

            # 5. LIVE TICK STREAM (Professional Chart Patching)
            live_ticks = {}
            for s in all_sym:
                tick = r.get_cache(f"ticks:{s}")
                if tick:
                    live_ticks[s] = tick
            update["ticks"] = live_ticks

            # 6. POSITIONS & TRADE LEDGER (Mock Broker Sync)
            mock_positions = r.get_cache("mock:positions:live")
            if mock_positions:
                update["positions"] = mock_positions
            
            trade_history = r.get_cache("mock:trade_history")
            if trade_history:
                update["trade_history"] = trade_history[:10]  # Last 10 for WS

            await websocket.send_json(update)
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# ===========================================
# STARTUP
# ===========================================
@app.on_event("startup")
async def startup():
    logger.info("Odyssey v2 Gateway starting on port 8000...")
    logger.info("Endpoints: /api/health, /api/account, /api/signals, /api/positions, /api/trades/history, /api/market/{symbol}, /api/risk, /ws/live")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

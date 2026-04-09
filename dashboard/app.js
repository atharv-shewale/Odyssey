/**
 * ODYSSEY v2 — Command Center Dashboard
 * Real-time WebSocket-driven trading terminal
 */

const WS_URL = 'ws://localhost:8000/ws/live';
const API_URL = 'http://localhost:8000/api';
const SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY'];
const CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'XAU'];

let ws = null;
let reconnectTimer = null;
let tradeLog = [];
const MAX_TRADES = 50;

let eventStudyMode = false;
document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('event-study-toggle');
    if (toggle) {
        toggle.addEventListener('click', (e) => {
            eventStudyMode = !eventStudyMode;
            e.target.innerText = eventStudyMode ? "DISABLE EVENT-STUDY" : "ENABLE EVENT-STUDY MODE";
            e.target.style.background = eventStudyMode ? "#38bdf8" : "#1e293b";
            e.target.style.color = eventStudyMode ? "#0f172a" : "#38bdf8";
        });
    }
});

// ============ CLOCK ============
function updateClock() {
    const now = new Date();
    const utc = now.toISOString().slice(11, 19);
    document.getElementById('clock').textContent = `UTC ${utc}`;
}
setInterval(updateClock, 1000);
updateClock();

// ============ FORMATTING ============
function fmtMoney(val) {
    const n = parseFloat(val) || 0;
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(val) {
    return (parseFloat(val) * 100).toFixed(2) + '%';
}

// ============ WEBSOCKET ============
function connectWS() {
    if (ws && ws.readyState <= 1) return;

    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        setStatus('LIVE', 'connected');
        activateServices();
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleUpdate(data);
            document.getElementById('lastUpdate').textContent =
                'Last: ' + new Date().toISOString().slice(11, 19);
        } catch (e) { console.error('Parse error:', e); }
    };

    ws.onclose = () => {
        setStatus('RECONNECTING', '');
        reconnectTimer = setTimeout(connectWS, 3000);
    };

    ws.onerror = () => {
        setStatus('OFFLINE', 'error');
    };
}

function setStatus(text, dotClass) {
    const el = document.getElementById('systemStatus');
    el.querySelector('span:last-child').textContent = text;
    const dot = el.querySelector('.status-dot');
    dot.className = 'status-dot' + (dotClass ? ' ' + dotClass : '');
}

function activateServices() {
    ['svcData', 'svcSentiment', 'svcML', 'svcStrategy', 'svcRisk', 'svcExecutor'].forEach(id => {
        document.getElementById(id).classList.add('active');
    });
}

// ============ DATA HANDLER ============
function handleUpdate(data) {
    if (data.account) updateAccount(data.account);
    if (data.signals) {
        updateSignals(data.signals);
        updateXAI(data.signals);
    }
    if (data.sentiment) updateSentiment(data.sentiment);
    if (data.risk_rejections) updateRejections(data.risk_rejections);
    updateRiskGauges(data);
}

// ============ ACCOUNT ============
function updateAccount(acc) {
    const balEl = document.getElementById('accountBalance');
    const eqEl = document.getElementById('accountEquity');
    const pnlEl = document.getElementById('accountPnl');

    balEl.textContent = fmtMoney(acc.balance);
    eqEl.textContent = fmtMoney(acc.equity);

    const pnl = parseFloat(acc.profit) || 0;
    pnlEl.textContent = (pnl >= 0 ? '+' : '') + fmtMoney(pnl);
    pnlEl.className = 'metric-value ' + (pnl >= 0 ? 'positive' : 'negative');
}

// ============ SIGNALS ============
function updateSignals(signals) {
    const grid = document.getElementById('signalGrid');
    grid.innerHTML = '';

    if (Array.isArray(signals)) {
        signals.forEach(sig => renderSignalCard(grid, sig));
    } else {
        // Initial load with no data — show placeholders
        SYMBOLS.forEach(sym => {
            renderSignalCard(grid, {
                symbol: sym, action: 'HOLD', confidence: 0,
                raw_prediction: 0, model_version: 'waiting...'
            });
        });
    }
}

function renderSignalCard(container, sig) {
    const action = (sig.action || 'HOLD').toUpperCase();
    const actionClass = action === 'BUY' ? 'buy' : action === 'SELL' ? 'sell' : 'hold';
    const conf = parseFloat(sig.confidence || 0);
    const pred = parseFloat(sig.raw_prediction || 0);
    const model = sig.model_version || 'odyssey_lstm_v1.0';

    const card = document.createElement('div');
    card.className = `signal-card ${actionClass}`;
    card.innerHTML = `
        <div class="signal-symbol">${sig.symbol || '---'}</div>
        <div class="signal-action ${actionClass}">${action}</div>
        <div class="signal-details">
            <div class="signal-detail-item">CONF: <span>${(conf * 100).toFixed(1)}%</span></div>
            <div class="signal-detail-item" title="Bayesian Uncertainty (MC Dropout StdDev)">PRED: <span>${pred >= 0 ? '+' : ''}${pred.toFixed(4)} ±${(parseFloat(sig.uncertainty_std || 0)).toFixed(4)}</span></div>
            <div class="signal-detail-item">MODEL: <span>${model.split('_').pop()}</span></div>
        </div>
    `;
    container.appendChild(card);

    // Add to trade blotter if actionable
    if (action !== 'HOLD') {
        addTradeEntry(sig);
    }
}

// ============ EXPLAINABLE AI (XAI) ============
function updateXAI(signals) {
    if (!signals || signals.length === 0) return;
    
    // Find the strongest signal to explain
    let topSignal = signals.reduce((prev, current) => 
        (parseFloat(current.signal_strength || 0) > parseFloat(prev.signal_strength || 0)) ? current : prev
    );
    
    if (!topSignal || !topSignal.feature_importance) return;
    
    document.getElementById('xaiSymbolHeader').textContent = 
        `${topSignal.symbol} — ${topSignal.action} (Conf: ${(topSignal.confidence*100).toFixed(1)}%)`;
        
    const barsContainer = document.getElementById('xaiBars');
    barsContainer.innerHTML = '';
    
    // Convert dict to array and sort by absolute importance
    const d = topSignal.feature_importance;
    let feats = Object.keys(d).map(k => ({ name: k, val: d[k] }));
    feats.sort((a, b) => Math.abs(b.val) - Math.abs(a.val));
    
    // Take top 8
    feats.slice(0, 8).forEach(f => {
        const pct = (f.val * 100).toFixed(1);
        const w = Math.min(Math.abs(f.val) * 100 * 2, 100); // Scale for visibility
        
        const el = document.createElement('div');
        el.className = 'xai-feature';
        el.innerHTML = `
            <div style="display:flex; justify-content:space-between">
                <span class="xai-label">${f.name.toUpperCase()}</span>
                <span class="xai-val">${pct}%</span>
            </div>
            <div class="xai-bar-out">
                <div class="xai-bar-in" style="width:${w}%"></div>
            </div>
        `;
        barsContainer.appendChild(el);
    });
}


// ============ RISK ============
function updateRiskGauges(data) {
    const acc = data.account || {};
    const balance = parseFloat(acc.balance) || 100000;
    const equity = parseFloat(acc.equity) || 100000;
    const drawdown = balance > 0 ? Math.max(0, (balance - equity) / balance) : 0;

    // Drawdown gauge
    const ddPct = Math.min(drawdown * 100, 100);
    document.getElementById('ddGauge').style.width = (ddPct / 10 * 100) + '%';
    document.getElementById('ddValue').textContent = fmtPct(drawdown);

    // Circuit breaker level
    const cbEl = document.getElementById('circuitBreakerLevel');
    if (drawdown >= 0.10) {
        cbEl.textContent = 'LEVEL 3 — HALT';
        cbEl.className = 'panel-badge risk-badge danger';
    } else if (drawdown >= 0.06) {
        cbEl.textContent = 'LEVEL 2 — RESTRICTED';
        cbEl.className = 'panel-badge risk-badge danger';
    } else if (drawdown >= 0.03) {
        cbEl.textContent = 'LEVEL 1 — CAUTION';
        cbEl.className = 'panel-badge risk-badge warning';
    } else {
        cbEl.textContent = 'NORMAL';
        cbEl.className = 'panel-badge risk-badge';
    }
}

function updateRejections(rejections) {
    const container = document.getElementById('riskRejections');
    container.innerHTML = '';

    if (!rejections || rejections.length === 0) return;

    rejections.forEach(rej => {
        const el = document.createElement('div');
        el.className = 'rejection-alert';
        el.textContent = `⛔ ${rej.symbol}: ${rej.reason || 'Risk check failed'}`;
        container.appendChild(el);
    });
}

// ============ SENTIMENT ============
function updateSentiment(sentiment) {
    const ccyContainer = document.getElementById('sentimentCurrencies');
    const pairContainer = document.getElementById('sentimentPairs');

    // Headlines count
    const countEl = document.getElementById('headlineCount');
    countEl.textContent = (sentiment.headlines_processed || 0) + ' headlines';

    // Currency bars
    ccyContainer.innerHTML = '';
    const currencies = sentiment.currencies || {};

    CURRENCIES.forEach(ccy => {
        const data = currencies[ccy] || { score: 0, count: 0 };
        const score = parseFloat(data.score) || 0;
        const isPositive = score >= 0;
        const absScore = Math.min(Math.abs(score), 1);

        const row = document.createElement('div');
        row.className = 'sentiment-row';

        const barWidth = absScore * 50; // max 50% of bar width
        const barLeft = isPositive ? 50 : 50 - barWidth;

        row.innerHTML = `
            <div class="sentiment-ccy">${ccy}</div>
            <div class="sentiment-bar-container">
                <div class="sentiment-bar-center"></div>
                <div class="sentiment-bar-fill ${isPositive ? 'positive' : 'negative'}"
                     style="left:${barLeft}%; width:${barWidth}%"></div>
            </div>
            <div class="sentiment-score ${score > 0.05 ? 'positive' : score < -0.05 ? 'negative' : 'neutral'}">
                ${score >= 0 ? '+' : ''}${score.toFixed(3)}
            </div>
        `;
        ccyContainer.appendChild(row);
    });

    // Pair sentiments
    pairContainer.innerHTML = '<div class="sentiment-pairs-title">PAIR SENTIMENT</div>';
    const pairs = sentiment.pairs || {};

    Object.entries(pairs).forEach(([pair, score]) => {
        const s = parseFloat(score) || 0;
        const isPositive = s >= 0;
        const absScore = Math.min(Math.abs(s), 1);
        const barWidth = absScore * 50;
        const barLeft = isPositive ? 50 : 50 - barWidth;

        const row = document.createElement('div');
        row.className = 'sentiment-row';
        row.innerHTML = `
            <div class="sentiment-ccy" style="min-width:56px; font-size:11px">${pair}</div>
            <div class="sentiment-bar-container">
                <div class="sentiment-bar-center"></div>
                <div class="sentiment-bar-fill ${isPositive ? 'positive' : 'negative'}"
                     style="left:${barLeft}%; width:${barWidth}%"></div>
            </div>
            <div class="sentiment-score ${s > 0.05 ? 'positive' : s < -0.05 ? 'negative' : 'neutral'}">
                ${s >= 0 ? '+' : ''}${s.toFixed(3)}
            </div>
        `;
        pairContainer.appendChild(row);
    });

    // Event-Study Mode: Highlight NLP extremities on blotter
    if (eventStudyMode) {
        const usdSent = Math.abs(parseFloat(currencies.USD?.score || 0));
        if (usdSent > 0.65) {
            const now = new Date().toISOString().slice(11, 19);
            const lastEvent = tradeLog.find(t => t.status === 'EVENT-STUDY');
            if (!lastEvent || (Date.now() - lastEvent._ts > 60000)) {
                tradeLog.unshift({
                    time: now,
                    symbol: 'USD_MACRO',
                    action: 'NLP_EVENT',
                    volume: '-',
                    price: currencies.USD.score.toFixed(3),
                    model: 'FinBERT',
                    status: 'EVENT-STUDY',
                    _ts: Date.now(),
                });
                renderBlotter();
            }
        }
    }
}

// ============ TRADE BLOTTER ============
function addTradeEntry(signal) {
    const now = new Date().toISOString().slice(11, 19);
    const action = (signal.action || 'HOLD').toUpperCase();

    // Dedupe: don't add same symbol+action within 3 seconds
    const lastSame = tradeLog.find(t => t.symbol === signal.symbol && t.action === action);
    if (lastSame && (Date.now() - lastSame._ts) < 3000) return;

    tradeLog.unshift({
        time: now,
        symbol: signal.symbol,
        action: action,
        volume: parseFloat(signal.volume || signal.signal_strength || 0.01).toFixed(2),
        price: parseFloat(signal.raw_prediction || 0).toFixed(5),
        model: (signal.model_version || 'lstm').split('_').pop(),
        status: 'SIGNAL',
        _ts: Date.now(),
    });

    if (tradeLog.length > MAX_TRADES) tradeLog = tradeLog.slice(0, MAX_TRADES);

    renderBlotter();
}

function renderBlotter() {
    const tbody = document.getElementById('blotterBody');
    const countEl = document.getElementById('blotterCount');
    countEl.textContent = tradeLog.length + ' trades';

    tbody.innerHTML = tradeLog.map(t => `
        <tr style="${t.status === 'EVENT-STUDY' ? 'background: #0ea5e922; border-left: 2px solid #38bdf8;' : ''}">
            <td>${t.time}</td>
            <td style="color:var(--text-primary);font-weight:600">${t.symbol}</td>
            <td class="${t.action === 'BUY' ? 'buy-cell' : t.action === 'SELL' ? 'sell-cell' : 'hold-cell'}" style="${t.action === 'NLP_EVENT' ? 'color:#38bdf8;' : ''}">${t.action}</td>
            <td>${t.volume}</td>
            <td>${t.price}</td>
            <td>${t.model}</td>
            <td class="${t.status === 'FILLED' ? 'filled-cell' : t.status === 'REJECTED' ? 'rejected-cell' : ''}" style="${t.status==='EVENT-STUDY' ? 'color:#38bdf8; font-weight:bold;' : ''}">${t.status}</td>
        </tr>
    `).join('');
}

// ============ INITIAL STATE ============
function renderInitialState() {
    // Signal placeholders
    updateSignals(null);

    // Sentiment placeholders
    const ccyContainer = document.getElementById('sentimentCurrencies');
    CURRENCIES.forEach(ccy => {
        const row = document.createElement('div');
        row.className = 'sentiment-row';
        row.innerHTML = `
            <div class="sentiment-ccy">${ccy}</div>
            <div class="sentiment-bar-container">
                <div class="sentiment-bar-center"></div>
            </div>
            <div class="sentiment-score neutral">0.000</div>
        `;
        ccyContainer.appendChild(row);
    });
}

// ============ BOOT ============
renderInitialState();
connectWS();

// Reconnect on visibility change
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && (!ws || ws.readyState > 1)) {
        connectWS();
    }
});

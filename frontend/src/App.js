import React, { useState, useEffect, useRef, useCallback } from 'react';
import Login from './Login';
import CandlestickChart from './CandlestickChart';
import AnalysisModal from './AnalysisModal';
import './BloombergTerminal.css';

const API_BASE = '';

function TerminalPanel({ title, children, flex = 1, style = {}, id }) {
  return (
    <div className="panel" style={{ flex, ...style }} id={id}>
      <div className="panel-header">
        <span>{title}</span>
        <span style={{ color: '#555' }}>ODSY-V2</span>
      </div>
      <div className="panel-content">
        {children}
      </div>
    </div>
  );
}

function StatRow({ label, value, color = '#ffb900', subValue = "" }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '13px' }}>
      <span style={{ color: '#555', fontWeight: 'bold' }}>{label}</span>
      <div style={{ textAlign: 'right' }}>
        <div style={{ color, fontWeight: 'bold' }}>{value}</div>
        {subValue && <div style={{ fontSize: '10px', color: '#333' }}>{subValue}</div>}
      </div>
    </div>
  );
}

function ProgressBar({ label, value, color = '#00ffff' }) {
    return (
        <div style={{ marginBottom: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#888', marginBottom: '2px' }}>
                <span>{label.toUpperCase()}</span>
                <span style={{ color }}>{(value * 100).toFixed(1)}%</span>
            </div>
            <div style={{ height: '4px', background: '#111', width: '100%' }}>
                <div style={{ height: '100%', width: `${value * 100}%`, background: color, transition: 'width 0.5s' }}></div>
            </div>
        </div>
    );
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('odyssey_token'));
  const [account, setAccount] = useState({ balance: 100000.0, equity: 100000.0, margin_free: 100000.0, profit: 0.0 });
  const [positions, setPositions] = useState([]);
  const [marketData, setMarketData] = useState({ forex: { signals: [] }, india: { signals: [] } });
  const [risk, setRisk] = useState({ daily_pnl: 0.0, var_99: 0.0, exposure: 0.0 });
  const [sentiment, setSentiment] = useState({ summary: {}, recent_headlines: [] });
  const [activeSymbol, setActiveSymbol] = useState('XAUUSD');
  const [activeMarket] = useState('forex'); // Fixed to forex as requested
  const [analysisSymbol, setAnalysisSymbol] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [marketMood, setMarketMood] = useState("Neutral / Scanning Data");
  const [backtestData, setBacktestData] = useState(null);
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [macroData, setMacroData] = useState({ status: {}, sectors: {} });
  const [chartData, setChartData] = useState([]);
  const [tradeHistory, setTradeHistory] = useState([]);
  
  const wsRef = useRef(null);
  const activeSymbolRef = useRef(activeSymbol);
  
  useEffect(() => {
    activeSymbolRef.current = activeSymbol;
  }, [activeSymbol]);

  const getAuthHeaders = useCallback(() => {
    return { 'Authorization': `Bearer ${token}` };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsProtocol}://${window.location.hostname}:8000/ws/live?token=${token}`;

    function connect() {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => setWsConnected(true);
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.account) setAccount(data.account);
        if (data.positions) setPositions(data.positions);
        if (data.markets) setMarketData(data.markets);
        if (data.sentiment) setSentiment(data.sentiment);
        if (data.risk) setRisk(data.risk);
        if (data.market_mood) setMarketMood(data.market_mood);
        if (data.trade_history) setTradeHistory(data.trade_history);
        
        // --- LIVE CHART PATCHING ---
        if (data.ticks && data.ticks[activeSymbolRef.current]) {
          const tickPrice = data.ticks[activeSymbolRef.current];
          setChartData(prev => {
            if (!prev || prev.length === 0) return prev;
            const lastIdx = prev.length - 1;
            const lastCandle = { ...prev[lastIdx] };
            
            // Only patch if price actually changed
            if (lastCandle.close === tickPrice) return prev;
            
            lastCandle.close = tickPrice;
            if (tickPrice > lastCandle.high) lastCandle.high = tickPrice;
            if (tickPrice < lastCandle.low) lastCandle.low = tickPrice;
            
            const newHistory = [...prev];
            newHistory[lastIdx] = lastCandle;
            return newHistory;
          });
        }
      };
      ws.onclose = () => {
        setWsConnected(false);
        setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
    }
    connect();
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, [token]);

  const runBacktest = async (symbol) => {
    setBacktestRunning(true);
    try {
      const res = await fetch(
        `/api/backtest/run?symbol=${symbol}&timeframe=H1&period_days=365&wfo_splits=5`,
        { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await res.json();
      if (data.metrics) setBacktestData({ symbol, ...data.metrics, statistical_validation: data.metrics.statistical_validation });
    } catch (e) {
      console.error('Backtest error:', e);
    }
    setBacktestRunning(false);
  };

  const loadBacktest = async (symbol) => {
    try {
      const res = await fetch(`/api/backtest/latest/${symbol}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (!data.error) setBacktestData({ symbol, ...data.metrics, statistical_validation: data.statistical_validation });
    } catch (e) {}
  };

  useEffect(() => {
    if (!token) return;
    const fetchMacro = async () => {
      try {
        const res = await fetch('/api/market/macro', { headers: { 'Authorization': `Bearer ${token}` } });
        const data = await res.json();
        setMacroData(data);
      } catch (e) {}
    };
    fetchMacro();
    const interval = setInterval(fetchMacro, 300000); // 5 minutes
    return () => clearInterval(interval);
  }, [token]);

  useEffect(() => {
    if (!token || !activeSymbol) return;
    const fetchChartData = async () => {
      try {
        const res = await fetch(`/api/market/${activeSymbol}`, { headers: { 'Authorization': `Bearer ${token}` } });
        const data = await res.json();
        if (data.history) setChartData(data.history);
      } catch (e) {}
    };
    fetchChartData();
    const interval = setInterval(fetchChartData, 10000); // 10s poll for "live" feel
    return () => clearInterval(interval);
  }, [token, activeSymbol]);

  // Fetch trade history on mount
  useEffect(() => {
    if (!token) return;
    const fetchHistory = async () => {
      try {
        const res = await fetch('/api/trades/history', { headers: { 'Authorization': `Bearer ${token}` } });
        const data = await res.json();
        if (data.trades) setTradeHistory(data.trades);
      } catch (e) {}
    };
    fetchHistory();
  }, [token]);

  if (!token) return <Login setToken={setToken} />;

  const handleLogout = () => {
    localStorage.removeItem('odyssey_token');
    setToken(null);
  };

  const pnlColor = (account.profit || 0) >= 0 ? '#00ff00' : '#ff3e3e';
  const activeSignals = marketData[activeMarket]?.signals || [];

  return (
    <div className="terminal-container">
      {/* Top Bar - Bloomberg Style */}
      <div className="top-bar">
        <div className="top-bar-left">
          <span>ODYSSEY-V2 QUANTITATIVE TERMINAL</span>
          <span style={{ color: wsConnected ? '#00ff00' : '#ff3e3e' }}>
             [{wsConnected ? 'LIVE' : 'OFFLINE'}]
          </span>
          <span style={{ color: '#555' }}>MOOD: {marketMood.toUpperCase()}</span>
        </div>
        <div className="top-bar-right">
          <span>NAV: <span style={{ color: '#00ffff' }}>{(account.equity || 0).toLocaleString()}</span></span>
          <span>PNL: <span style={{ color: pnlColor }}>{(account.profit || 0).toFixed(2)}</span></span>
          <button className="close-btn" style={{ marginLeft: '10px' }} onClick={handleLogout}>LOGOUT</button>
        </div>
      </div>

      {/* Main Grid Layout */}
      <div className="main-grid">
        
        {/* Left Column: Assets & Intelligence */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', overflowY: 'auto', minHeight: 0 }}>
          <div className="market-tabs">
            <div className={`market-tab active`}>FOREX & GLOBAL (ACTIVE)</div>
          </div>

          <TerminalPanel title={`Focus: FOREX & GLOBAL`} id="panel-assets">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
              {['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'DAX40', 'SPX500'].map(sym => (
                <button 
                    key={sym} 
                    className={`asset-pill ${activeSymbol === sym ? 'active' : ''}`}
                    onClick={() => setActiveSymbol(sym)}
                >
                    {sym}
                </button>
              ))}
            </div>
          </TerminalPanel>

          <TerminalPanel title="Intelligence: Macro Multiplier" flex={1.5} id="panel-macro">
            <div style={{ marginBottom: '8px' }}>
              <div style={{ fontSize: '10px', color: '#555', marginBottom: '4px' }}>GLOBAL CONTEXT (ALPHAVANTAGE)</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#0a0a0a', padding: '6px', border: '1px solid #1a1a1a' }}>
                <span style={{ fontSize: '12px', fontWeight: 'bold', color: macroData.status?.spy_change >= 0 ? '#00ff00' : '#ff3e3e' }}>
                  {macroData.status?.global_mood?.toUpperCase() || 'SCANNING...'}
                </span>
                <span style={{ fontSize: '10px', color: '#00ffff' }}>
                  SPY: {macroData.status?.spy_change > 0 ? '+' : ''}{macroData.status?.spy_change || 0}%
                </span>
              </div>
            </div>
            <div style={{ fontSize: '10px', color: '#555', marginBottom: '4px' }}>SECTOR ROTATION (REAL-TIME)</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px' }}>
              {Object.entries(macroData.sectors || {}).slice(0, 4).map(([name, perf]) => (
                <div key={name} style={{ background: '#0a0a0a', padding: '4px', fontSize: '9px', borderLeft: `2px solid ${parseFloat(perf) >= 0 ? '#00ff00' : '#ff3e3e'}` }}>
                  <div style={{ color: '#444', overflow: 'hidden', whiteSpace: 'nowrap' }}>{name.toUpperCase()}</div>
                  <div style={{ color: parseFloat(perf) >= 0 ? '#00ff00' : '#ff3e3e' }}>{perf}</div>
                </div>
              ))}
            </div>
          </TerminalPanel>

          <TerminalPanel title="Intelligence: Signals & Research" flex={3} id="panel-signals">
            {activeSignals.length === 0 && <div style={{ color: '#333' }}>&gt;&gt; SCANNING {activeMarket.toUpperCase()} FOR ALPHA...</div>}
            {activeSignals.map((s, i) => (
              <div key={i} className="signal-card" onClick={() => setAnalysisSymbol(s.symbol)} style={{ cursor: 'pointer' }}>
                <div className="signal-header">
                  <span style={{ color: '#ffb900' }}>{s.symbol}</span>
                  <span style={{ color: s.action === 'BUY' ? '#00ff00' : s.action === 'SELL' ? '#ff3e3e' : '#555' }}>
                    {s.action} [{s.type || 'P-VAL'}]
                  </span>
                </div>
                <div className="signal-meta">
                  <span>CONF: {(s.confidence*100).toFixed(1)}%</span>
                  <span style={{ color: '#00ffff' }}>DEEP DIVE [CLI]</span>
                </div>
              </div>
            ))}
          </TerminalPanel>
        </div>

        {/* Center Column: Visualization */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minHeight: 0 }}>
          <TerminalPanel title={`Visualization: ${activeSymbol}`} style={{ flex: 3 }} id="panel-chart">
            <CandlestickChart symbol={activeSymbol} data={chartData} />
          </TerminalPanel>
          
          <TerminalPanel title="Execution: Global Ledger" style={{ flex: 1.5 }} id="panel-executions">
            <div style={{ fontSize: '10px', color: '#555', marginBottom: '4px' }}>OPEN POSITIONS</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>SYMBOL</th>
                  <th>SIDE</th>
                  <th style={{ textAlign: 'right' }}>VOL</th>
                  <th style={{ textAlign: 'right' }}>ENTRY</th>
                  <th style={{ textAlign: 'right' }}>P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 && <tr><td colSpan="5" style={{ textAlign: 'center', color: '#222', padding: '12px' }}>&gt;&gt; NO ACTIVE EXECUTIONS</td></tr>}
                {positions.map((p, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 'bold' }}>{p.symbol}</td>
                    <td style={{ color: p.action === 'BUY' ? '#00ff00' : '#ff3e3e' }}>{p.action}</td>
                    <td style={{ textAlign: 'right' }}>{p.volume}</td>
                    <td style={{ textAlign: 'right', color: '#00ffff', fontSize: '11px' }}>{(p.entry_price || 0).toFixed(2)}</td>
                    <td style={{ textAlign: 'right', color: (p.pnl || 0) >= 0 ? '#00ff00' : '#ff3e3e', fontWeight: 'bold' }}>
                        {(p.pnl || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ fontSize: '10px', color: '#555', marginTop: '10px', marginBottom: '4px', borderTop: '1px solid #111', paddingTop: '6px' }}>TRADE HISTORY (CLOSED)</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>SYMBOL</th>
                  <th>SIDE</th>
                  <th style={{ textAlign: 'right' }}>ENTRY</th>
                  <th style={{ textAlign: 'right' }}>EXIT</th>
                  <th style={{ textAlign: 'right' }}>P&L</th>
                </tr>
              </thead>
              <tbody>
                {(!tradeHistory || tradeHistory.length === 0) && <tr><td colSpan="5" style={{ textAlign: 'center', color: '#222', padding: '8px' }}>&gt;&gt; NO CLOSED TRADES</td></tr>}
                {(tradeHistory || []).map((t, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 'bold' }}>{t.symbol}</td>
                    <td style={{ color: t.action === 'BUY' ? '#00ff00' : '#ff3e3e' }}>{t.action}</td>
                    <td style={{ textAlign: 'right', fontSize: '11px' }}>{(t.entry_price || 0).toFixed(2)}</td>
                    <td style={{ textAlign: 'right', fontSize: '11px' }}>{(t.exit_price || 0).toFixed(2)}</td>
                    <td style={{ textAlign: 'right', color: (t.pnl || 0) >= 0 ? '#00ff00' : '#ff3e3e', fontWeight: 'bold' }}>
                        {(t.pnl || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TerminalPanel>
        </div>

        {/* Right Column: News & Behavioral Social */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', overflowY: 'auto', minHeight: 0 }}>
          <TerminalPanel title="Risk: Portfolio Integrity" id="panel-risk">
            <StatRow label="VAR (99%)" value={`$${(risk.var_99 || 0).toFixed(2)}`} color="#ff3e3e" subValue="Probabilistic Loss" />
            <StatRow label="EXPOSURE" value={`${((risk.exposure || 0) * 100).toFixed(1)}%`} color="#00ffff" />
            <StatRow label="DAILY PNL" value={`$${(risk.daily_pnl || 0).toFixed(2)}`} color={risk.daily_pnl >= 0 ? '#00ff00' : '#ff3e3e'} />
          </TerminalPanel>

          <TerminalPanel title="Research: Backtest Engine" flex={1.5} id="panel-backtest">
            {backtestData ? (() => {
              const sv = backtestData.statistical_validation || {};
              const tt = sv.sharpe_ttest || {};
              const ci = sv.bootstrap_ci || {};
              const sharpe_ci = ci.sharpe_ci || ['—', '—'];
              const isSignificant = tt.significant;
              const pVal = tt.p_value;
              return (
                <div>
                  <div style={{ marginBottom: '8px', fontSize: '10px', color: '#555' }}>
                    {backtestData.symbol} | WFO 5-Fold | D1
                  </div>
                  <StatRow label="SHARPE (ANN)" value={(backtestData.sharpe_ratio||0).toFixed(3)} color="#00ffff" />
                  <StatRow label="SORTINO" value={(backtestData.sortino_ratio||0).toFixed(3)} color="#00ffff" />
                  <StatRow label="MAX DRAWDOWN" value={`${((backtestData.max_drawdown||0)*100).toFixed(2)}%`} color="#ff3e3e" />
                  <StatRow label="WIN RATE" value={`${((backtestData.win_rate||0)*100).toFixed(1)}%`} color="#ffb900" />
                  <div style={{ marginTop: '8px', padding: '6px', background: '#0a0a0a', border: `1px solid ${isSignificant ? '#00ff00' : '#ff3e3e'}` }}>
                    <div style={{ fontSize: '9px', color: '#555', marginBottom: '2px' }}>STAT SIGNIFICANCE</div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: isSignificant ? '#00ff00' : '#ff3e3e', fontWeight: 'bold', fontSize: '11px' }}>
                        {isSignificant ? '✅ VALID' : '⚠️ INCONCLUSIVE'}
                      </span>
                      <span style={{ fontSize: '10px', color: '#555' }}>p={pVal?.toFixed(4)}</span>
                    </div>
                    <div style={{ fontSize: '10px', color: '#555', marginTop: '2px' }}>
                      CI: [{sharpe_ci[0]} — {sharpe_ci[1]}]
                    </div>
                  </div>
                </div>
              );
            })() : (
              <div>
                <div style={{ color: '#333', fontSize: '11px', marginBottom: '10px' }}>&gt;&gt; NO BACKTEST DATA</div>
                <div style={{ fontSize: '10px', color: '#444', marginBottom: '12px' }}>Select a symbol and run a Walk-Forward backtest to see statistical validation results.</div>
              </div>
            )}
            <button 
              onClick={() => runBacktest(activeSymbol)}
              disabled={backtestRunning}
              style={{ 
                width: '100%', marginTop: '8px',
                background: backtestRunning ? '#111' : '#1a1a00',
                border: `1px solid ${backtestRunning ? '#333' : '#ffb900'}`,
                color: backtestRunning ? '#555' : '#ffb900',
                padding: '6px', cursor: backtestRunning ? 'not-allowed' : 'pointer',
                fontSize: '10px', fontFamily: 'inherit', fontWeight: 'bold'
              }}
            >
              {backtestRunning ? '>> RUNNING WFO + STAT VALIDATION...' : `[RUN BACKTEST: ${activeSymbol}]`}
            </button>
          </TerminalPanel>

          <TerminalPanel title="Social & News Integration" flex={3} id="panel-sentiment">
            {sentiment.recent_headlines?.length === 0 && <div style={{ color: '#222' }}>&gt;&gt; AGGREGATING RSS/SOCIAL FEEDS...</div>}
            {sentiment.recent_headlines?.map((h, i) => (
              <div key={i} className="news-item">
                <div className="news-headline">{h.headline}</div>
                <div className="news-footer">
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <span className="source-tag">{h.source?.replace('_', ' ').toUpperCase() || 'FIN-WIRE'}</span>
                    <span style={{ color: h.score > 0.1 ? '#00ff00' : h.score < -0.1 ? '#ff3e3e' : '#555' }}>
                      {h.label}
                    </span>
                  </div>
                  <span style={{ color: '#333' }}>{h.timestamp?.substring(11, 16)}</span>
                </div>
              </div>
            ))}
          </TerminalPanel>
        </div>

      </div>

      {/* Analysis Deep Dive Modal */}
      {analysisSymbol && (
        <AnalysisModal 
          symbol={analysisSymbol} 
          onClose={() => setAnalysisSymbol(null)} 
        />
      )}
    </div>
  );
}





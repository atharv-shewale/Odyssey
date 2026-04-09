"""
Odyssey v2 - Backtest Report Generator (Phase 7 - Research Grade)
Generates HTML tear sheet + LaTeX table with statistical significance sections.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any


class ReportGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, symbol: str, timeframe: str, results: Dict[str, Any],
                 equity_curve: list, trades: list) -> str:
        """Generate static HTML tear sheet with statistical significance section."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_{symbol}_{timeframe}_{timestamp}.html"
        filepath = os.path.join(self.output_dir, filename)

        m = results
        sv = m.get('statistical_validation', {})
        ttest = sv.get('sharpe_ttest', {})
        ci = sv.get('bootstrap_ci', {})
        dsr = sv.get('deflated_sharpe', {})
        perm = sv.get('permutation_test', {})
        verdict = sv.get('overall_verdict', {})

        p_val = ttest.get('p_value', 1.0)
        sig_color = '#10b981' if ttest.get('significant') else '#ef4444'
        sig_label = '✅ SIGNIFICANT' if ttest.get('significant') else '⚠️ NOT SIGNIFICANT'

        sharpe_ci = ci.get('sharpe_ci', ('—', '—'))
        sortino_ci = ci.get('sortino_ci', ('—', '—'))
        dsr_val = dsr.get('dsr', 0.0)
        perm_p = perm.get('p_value', 1.0)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Odyssey v2 Backtest: {symbol} {timeframe}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; }}
        h1 {{ font-family: 'JetBrains Mono', monospace; color: #38bdf8; border-bottom: 1px solid #334155; padding-bottom: 12px; margin-bottom: 24px; font-size: 18px; }}
        h2 {{ font-size: 13px; color: #94a3b8; text-transform: uppercase; letter-spacing: 2px; margin: 28px 0 12px; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
        .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px; }}
        .metric {{ background: #1e293b; padding: 16px; border-radius: 6px; border-left: 4px solid #334155; }}
        .metric.positive {{ border-left-color: #10b981; }}
        .metric.negative {{ border-left-color: #ef4444; }}
        .metric.info {{ border-left-color: #38bdf8; }}
        .label {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 1px; margin-bottom: 6px; }}
        .value {{ font-family: 'JetBrains Mono', monospace; font-size: 20px; font-weight: bold; }}
        .sub {{ font-size: 11px; color: #64748b; margin-top: 3px; }}
        .stat-section {{ background: #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 24px; border: 1px solid #334155; }}
        .sig-badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; background: {sig_color}22; color: {sig_color}; border: 1px solid {sig_color}44; }}
        .verdict {{ font-size: 15px; margin-top: 12px; padding: 12px; background: #0f172a; border-radius: 4px; }}
        .chart-container {{ background: #1e293b; padding: 20px; border-radius: 6px; margin-bottom: 24px; }}
        table {{ width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 11px; }}
        th, td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; text-align: left; }}
        th {{ color: #64748b; text-transform: uppercase; font-size: 10px; letter-spacing: 1px; background: #0f172a; }}
        .buy {{ color: #10b981; }} .sell {{ color: #ef4444; }}
        .profit {{ color: #10b981; }} .loss {{ color: #ef4444; }}
    </style>
</head>
<body>
    <h1>ODYSSEY v2 // RESEARCH BACKTEST // {symbol.upper()} {timeframe}</h1>
    <div style="color:#64748b; font-size:12px; margin-bottom:24px;">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} &nbsp;|&nbsp; WFO Splits: {m.get('wfo_splits', 'N/A')} &nbsp;|&nbsp; Trades: {m.get('total_trades', 0)}</div>

    <h2>Performance Summary</h2>
    <div class="grid">
        <div class="metric {'positive' if m.get('net_profit', 0) > 0 else 'negative'}">
            <div class="label">Net Profit</div>
            <div class="value">${m.get('net_profit', 0):,.2f}</div>
            <div class="sub">{m.get('return_pct', 0)*100:.2f}% total return</div>
        </div>
        <div class="metric {'positive' if m.get('vs_benchmark', 0) > 0 else 'negative'}">
            <div class="label">Alpha vs Buy-Hold</div>
            <div class="value">{m.get('vs_benchmark', 0)*100:+.2f}%</div>
            <div class="sub">B&H: {m.get('bah_return_pct', 0)*100:.2f}%</div>
        </div>
        <div class="metric">
            <div class="label">Win Rate</div>
            <div class="value">{m.get('win_rate', 0)*100:.1f}%</div>
            <div class="sub">Profit Factor: {m.get('profit_factor', 0):.2f}</div>
        </div>
        <div class="metric negative">
            <div class="label">Max Drawdown</div>
            <div class="value">{m.get('max_drawdown', 0)*100:.2f}%</div>
            <div class="sub">${m.get('max_drawdown_usd', 0):,.2f}</div>
        </div>
    </div>

    <h2>Risk-Adjusted Returns</h2>
    <div class="grid">
        <div class="metric info">
            <div class="label">Sharpe Ratio (Ann.)</div>
            <div class="value">{m.get('sharpe_ratio', 0):.3f}</div>
            <div class="sub">CI: [{sharpe_ci[0]} — {sharpe_ci[1]}]</div>
        </div>
        <div class="metric info">
            <div class="label">Sortino Ratio</div>
            <div class="value">{m.get('sortino_ratio', 0):.3f}</div>
            <div class="sub">CI: [{sortino_ci[0]} — {sortino_ci[1]}]</div>
        </div>
        <div class="metric info">
            <div class="label">Calmar Ratio</div>
            <div class="value">{m.get('calmar_ratio', 0):.3f}</div>
            <div class="sub">Return / Max Drawdown</div>
        </div>
        <div class="metric info">
            <div class="label">Recovery Factor</div>
            <div class="value">{m.get('recovery_factor', 0):.3f}</div>
            <div class="sub">Profit / Max DD ($)</div>
        </div>
    </div>

    <h2>Statistical Significance</h2>
    <div class="stat-section">
        <div style="display:flex; gap:16px; align-items:center; margin-bottom:16px;">
            <span class="sig-badge">{sig_label}</span>
            <span style="color:#94a3b8; font-size:13px;">Sharpe t-test: t={ttest.get('t_stat', 0):.3f}, p={p_val:.4f}</span>
        </div>

        <div class="grid-3">
            <div class="metric">
                <div class="label">Sharpe p-value</div>
                <div class="value" style="color:{sig_color}">{p_val:.4f}</div>
                <div class="sub">H0: Sharpe ≤ 0 (one-tailed)</div>
            </div>
            <div class="metric">
                <div class="label">Deflated Sharpe (DSR)</div>
                <div class="value">{dsr_val:.3f}</div>
                <div class="sub">{dsr.get('interpretation', '')[:40]}</div>
            </div>
            <div class="metric">
                <div class="label">Permutation p-value</div>
                <div class="value">{perm_p:.4f}</div>
                <div class="sub">{perm.get('interpretation', '')[:40]}</div>
            </div>
        </div>

        <div class="verdict">{verdict.get('summary', 'Statistical validation not run')}</div>
    </div>

    <h2>Equity Curve</h2>
    <div class="chart-container">
        <svg width="100%" height="200" viewBox="0 0 1000 200" preserveAspectRatio="none" style="margin-top:10px;">
"""
        # Generate SVG equity curve
        if len(equity_curve) > 1:
            mi, ma = min(equity_curve), max(equity_curve)
            rng = ma - mi if ma > mi else 1
            pts = []
            for i, val in enumerate(equity_curve):
                x = (i / (len(equity_curve) - 1)) * 1000
                y = 190 - (((val - mi) / rng) * 180 + 5)
                pts.append(f"{x},{y}")
            path = f"M {pts[0]} " + " ".join([f"L {p}" for p in pts[1:]])
            color = '#10b981' if equity_curve[-1] >= equity_curve[0] else '#ef4444'
            html += f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" />'
            # Zero line
            y0 = 190 - (((self.initial_balance - mi) / rng) * 180 + 5) if hasattr(self, 'initial_balance') else 100
            html += f'<line x1="0" y1="{y0:.0f}" x2="1000" y2="{y0:.0f}" stroke="#334155" stroke-width="1" stroke-dasharray="4"/>'

        html += f"""
        </svg>
    </div>

    <h2>Trade Log (Last 50)</h2>
    <table>
        <tr><th>Entry Time</th><th>Type</th><th>Entry</th><th>Exit</th><th>Conf.</th><th>P&L</th></tr>
"""
        for t in list(reversed(trades))[:50]:
            pnl_class = 'profit' if t['pnl'] >= 0 else 'loss'
            side_class = 'buy' if t['action'] == 'BUY' else 'sell'
            html += f"""
        <tr>
            <td>{t.get('time', '—')}</td>
            <td class="{side_class}">{t['action']}</td>
            <td>{t['entry_price']:.5f}</td>
            <td>{t.get('exit_price', 0):.5f}</td>
            <td>{t.get('confidence', 0)*100:.0f}%</td>
            <td class="{pnl_class}">${t['pnl']:+.2f}</td>
        </tr>"""

        html += """
    </table>
</body>
</html>"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)

        return filepath

    def generate_latex(self, symbol: str, timeframe: str, results: Dict[str, Any],
                       params: Dict[str, Any]) -> str:
        """Generate academic LaTeX tearsheet for paper inclusion."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tearsheet_{symbol}_{timeframe}_{timestamp}.tex"
        filepath = os.path.join(self.output_dir, filename)

        m = results
        sv = m.get('statistical_validation', {})
        ttest = sv.get('sharpe_ttest', {})
        ci = sv.get('bootstrap_ci', {})
        dsr = sv.get('deflated_sharpe', {})
        perm = sv.get('permutation_test', {})
        sharpe_ci = ci.get('sharpe_ci', ('—', '—'))
        is_wfo = "Yes" if m.get('wfo_splits') else "No"
        sig = "Yes ($p < 0.05$)" if ttest.get('significant') else "No ($p \\geq 0.05$)"

        tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{Walk-Forward Backtest Results: {symbol} ({timeframe})}}
\\label{{tab:backtest_{symbol.lower()}}}
\\begin{{tabular}}{{l | r}}
\\hline
\\hline
\\textbf{{Metric}} & \\textbf{{Value}} \\\\
\\hline
\\multicolumn{{2}}{{l}}{{\\textit{{Performance}}}} \\\\
\\hline
Net Profit & \\${m.get('net_profit', 0):,.2f} \\\\
Total Return & {m.get('return_pct', 0)*100:.2f}\\% \\\\
Alpha vs. Buy-and-Hold & {m.get('vs_benchmark', 0)*100:+.2f}\\% \\\\
Win Rate & {m.get('win_rate', 0)*100:.2f}\\% \\\\
Profit Factor & {m.get('profit_factor', 0):.2f} \\\\
Total Trades & {m.get('total_trades', 0)} \\\\
\\hline
\\multicolumn{{2}}{{l}}{{\\textit{{Risk-Adjusted Returns}}}} \\\\
\\hline
Sharpe Ratio (Ann.) & {m.get('sharpe_ratio', 0):.4f} \\\\
Sharpe 95\\% CI & [{sharpe_ci[0]}, {sharpe_ci[1]}] \\\\
Sortino Ratio & {m.get('sortino_ratio', 0):.4f} \\\\
Calmar Ratio & {m.get('calmar_ratio', 0):.4f} \\\\
Max Drawdown & {m.get('max_drawdown', 0)*100:.2f}\\% \\\\
Recovery Factor & {m.get('recovery_factor', 0):.4f} \\\\
\\hline
\\multicolumn{{2}}{{l}}{{\\textit{{Statistical Validation}}}} \\\\
\\hline
Sharpe t-statistic & {ttest.get('t_stat', 0):.4f} \\\\
Sharpe p-value (1-tailed) & {ttest.get('p_value', 1.0):.4f} \\\\
Statistically Significant & {sig} \\\\
Deflated Sharpe Ratio (DSR) & {dsr.get('dsr', 0):.4f} \\\\
Permutation Test p-value & {perm.get('p_value', 1.0):.4f} \\\\
Walk-Forward Optimization & {is_wfo} ({m.get('wfo_splits', 0)} folds) \\\\
\\hline
\\hline
\\end{{tabular}}
\\vspace{{1ex}}
\\flushleft{{\\footnotesize \\textit{{Note:}} Results include bid-ask spread ({params.get('spread_pips', 1.0)} pips), latency-adjusted slippage, and round-trip commission (\\${params.get('commission_per_lot', 3.5):.2f}/lot). Statistical tests: one-tailed Sharpe $t$-test, 10,000-sample bootstrap CI, Bailey \\& Lopez de Prado (2014) DSR, 1,000-permutation Monte Carlo.}}
\\end{{table}}
"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(tex)

        return filepath

import os
import json
from datetime import datetime
from typing import Dict, Any

class ReportGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, symbol: str, timeframe: str, results: Dict[str, Any], equity_curve: list, trades: list) -> str:
        """Generate static HTML report."""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_{symbol}_{timeframe}_{timestamp}.html"
        filepath = os.path.join(self.output_dir, filename)

        m = results
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Odyssey v2 Backtest: {symbol} {timeframe}</title>
            <style>
                body {{ font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
                h1 {{ font-family: 'JetBrains Mono', monospace; color: #38bdf8; border-bottom: 1px solid #334155; padding-bottom: 10px; }}
                .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }}
                .metric {{ background: #1e293b; padding: 15px; border-radius: 6px; border-left: 4px solid #38bdf8; }}
                .metric.positive {{ border-left-color: #10b981; }}
                .metric.negative {{ border-left-color: #ef4444; }}
                .label {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 600; list-style: 1px; margin-bottom: 5px; }}
                .value {{ font-family: 'JetBrains Mono', monospace; font-size: 20px; font-weight: bold; }}
                .chart-container {{ background: #1e293b; padding: 20px; border-radius: 6px; margin-bottom: 30px; height: 300px; }}
                table {{ width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 12px; }}
                th, td {{ padding: 10px; border-bottom: 1px solid #334155; text-align: left; }}
                th {{ color: #94a3b8; font-weight: 600; text-transform: uppercase; }}
                .buy {{ color: #10b981; }} .sell {{ color: #ef4444; }}
                .profit {{ color: #10b981; }} .loss {{ color: #ef4444; }}
            </style>
        </head>
        <body>
            <h1>ODYSSEY v2 // BACKTEST REPORT // {symbol} {timeframe}</h1>
            
            <div class="grid">
                <div class="metric {'positive' if m['net_profit'] > 0 else 'negative'}">
                    <div class="label">Net Profit</div>
                    <div class="value">${m['net_profit']:.2f} ({(m['return_pct']*100):.1f}%)</div>
                </div>
                <div class="metric">
                    <div class="label">Win Rate</div>
                    <div class="value">{(m['win_rate']*100):.1f}%</div>
                </div>
                <div class="metric">
                    <div class="label">Profit Factor</div>
                    <div class="value">{m['profit_factor']:.2f}</div>
                </div>
                <div class="metric negative">
                    <div class="label">Max Drawdown</div>
                    <div class="value">{(m['max_drawdown']*100):.2f}%</div>
                </div>
                <div class="metric">
                    <div class="label">Total Trades</div>
                    <div class="value">{m['total_trades']}</div>
                </div>
                <div class="metric">
                    <div class="label">Sharpe Ratio</div>
                    <div class="value">{m['sharpe_ratio']:.2f}</div>
                </div>
                <div class="metric">
                    <div class="label">Avg Trade</div>
                    <div class="value">${m['average_trade']:.2f}</div>
                </div>
            </div>
            
            <!-- Simple SVG Chart for Equity Curve -->
            <div class="chart-container">
                <div class="label">Equity Curve Overview</div>
                <svg width="100%" height="250" viewBox="0 0 1000 250" preserveAspectRatio="none" style="margin-top: 15px;">
        """
        
        # Generate SVG polygon for equity curve
        if len(equity_curve) > 1:
            mi, ma = min(equity_curve), max(equity_curve)
            rng = ma - mi if ma > mi else 1
            pts = []
            for i, val in enumerate(equity_curve):
                x = (i / (len(equity_curve) - 1)) * 1000
                y = 250 - (((val - mi) / rng) * 230 + 10)
                pts.append(f"{x},{y}")
            
            path_d = f"M {pts[0]} " + " ".join([f"L {p}" for p in pts[1:]])
            html += f'<path d="{path_d}" fill="none" stroke="#38bdf8" stroke-width="2" />'
            
        html += """
                </svg>
            </div>
            
            <h2>Last 100 Trades</h2>
            <table>
                <tr><th>Time</th><th>Type</th><th>Volume</th><th>Entry</th><th>Exit</th><th>P&L</th></tr>
        """
        
        # Add trade history (limit to 100 for report size)
        for t in list(reversed(trades))[:100]:
            pnl_class = 'profit' if t['pnl'] >= 0 else 'loss'
            side_class = 'buy' if t['action'] == 'BUY' else 'sell'
            html += f"""
                <tr>
                    <td>{t.get('exit_time', t.get('time', '---'))}</td>
                    <td class="{side_class}">{t['action']}</td>
                    <td>{t['volume']}</td>
                    <td>{t['entry_price']:.5f}</td>
                    <td>{t['exit_price']:.5f}</td>
                    <td class="{pnl_class}">${t['pnl']:+.2f}</td>
                </tr>
            """
            
        html += """
            </table>
        </body>
        </html>
        """
        
        with open(filepath, 'w') as f:
            f.write(html)
            
        return filepath

    def generate_latex(self, symbol: str, timeframe: str, results: Dict[str, Any], params: Dict[str, Any]) -> str:
        """Generate academic LaTeX tearsheet (table)."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tearsheet_{symbol}_{timeframe}_{timestamp}.tex"
        filepath = os.path.join(self.output_dir, filename)
        
        m = results
        is_wfo = "Yes" if "wfo_splits" in m else "No"
        
        tex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{Backtest Results: {symbol} ({timeframe})}}
\\label{{tab:backtest_{symbol.lower()}}}
\\begin{{tabular}}{{l | r}}
\\hline
\\hline
\\textbf{{Metric}} & \\textbf{{Value}} \\\\
\\hline
Initial Balance & \\${params.get('initial_balance', 100000):,.2f} \\\\
Net Profit & \\${m['net_profit']:,.2f} \\\\
Return on Investment & {(m['return_pct']*100):.2f}\\% \\\\
Win Rate & {(m['win_rate']*100):.2f}\\% \\\\
Profit Factor & {m['profit_factor']:.2f} \\\\
Sharpe Ratio & {m['sharpe_ratio']:.2f} \\\\
Max Drawdown & {(m['max_drawdown']*100):.2f}\\% \\\\
Total Trades & {m['total_trades']} \\\\
Average Trade & \\${m['average_trade']:.2f} \\\\
Walk-Forward Optimization & {is_wfo}  \\\\
\\hline
\\hline
\\end{{tabular}}
\\vspace{{1ex}}
\\flushleft{{\\footnotesize \\textit{{Note:}} Results include estimated transaction costs (slippage/spread). Model used is Odyssey v2 XAI LSTM.}}
\\end{{table}}
"""
        with open(filepath, 'w') as f:
            f.write(tex)
            
        return filepath

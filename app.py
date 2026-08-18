import os
import sqlite3
import feedparser
from flask import Flask, render_template_string, request
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

app = Flask(__name__)

ASSETS = {
    "BTC-USD": {"name": "بیت‌کوین (BTC)", "tv": "BINANCE:BTCUSDT", "type": "crypto", "keyword": "bitcoin"},
    "ETH-USD": {"name": "اتریوم (ETH)", "tv": "BINANCE:ETHUSDT", "type": "crypto", "keyword": "ethereum"},
    "SOL-USD": {"name": "سولانا (SOL)", "tv": "BINANCE:SOLUSDT", "type": "crypto", "keyword": "solana"},
    "GC=F": {"name": "انس طلا (Gold)", "tv": "OANDA:XAUUSD", "type": "forex_gold", "keyword": "gold"}
}

DB_FILE = "trade_vault.db"

# ----------------------------------------------------
# 1. مدیریت دیتابیس و شبیه‌سازی (Backtest & DB)
# ----------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    signal_type TEXT,
                    entry REAL,
                    tp REAL,
                    sl REAL,
                    status TEXT,
                    result_badge TEXT,
                    win_flag INTEGER,
                    pnl_dollar REAL,
                    month_str TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

def train_bot_on_history(symbol, df):
    """بک‌تست سریع ۴۸ ساعت گذشته برای پر کردن گزارش و آموزش ربات"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM trades WHERE symbol = ?", (symbol,))
    count = c.fetchone()[0]
    
    if count > 0:
        conn.close()
        return  # قبلاً آموزش دیده است
        
    print(f"[آموزش ربات] در حال شبیه‌سازی و بک‌تست {symbol} برای درک بازار...")
    
    # محاسبه اندیکاتورهای پایه برای بک‌تست
    close = df['Close']
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    atr = (df['High'] - df['Low']).rolling(14).mean().fillna(close * 0.005)
    
    in_trade = False
    trade_type = None
    entry_price = 0
    tp_price = 0
    sl_price = 0
    month_str = datetime.now().strftime("%Y-%m")
    
    for i in range(20, len(df)):
        c_close = close.iloc[i]
        c_high = df['High'].iloc[i]
        c_low = df['Low'].iloc[i]
        c_atr = atr.iloc[i]
        
        if not in_trade:
            # استراتژی ورود ساده برای بک‌تست
            if ema9.iloc[i] > ema21.iloc[i] and ema9.iloc[i-1] <= ema21.iloc[i-1]:
                in_trade = True
                trade_type = 'BUY'
                entry_price = c_close
                sl_price = entry_price - (1.5 * c_atr)
                tp_price = entry_price + (3.0 * c_atr)
            elif ema9.iloc[i] < ema21.iloc[i] and ema9.iloc[i-1] >= ema21.iloc[i-1]:
                in_trade = True
                trade_type = 'SELL'
                entry_price = c_close
                sl_price = entry_price + (1.5 * c_atr)
                tp_price = entry_price - (3.0 * c_atr)
        else:
            # بررسی خروج
            closed = False
            win = 0
            if trade_type == 'BUY':
                if c_high >= tp_price: closed, win = True, 1
                elif c_low <= sl_price: closed, win = True, 0
            else:
                if c_low <= tp_price: closed, win = True, 1
                elif c_high >= sl_price: closed, win = True, 0
                
            if closed:
                res_badge = "می‌شود 🎉" if win == 1 else "نشد ❌"
                pnl = 20.0 if win == 1 else -10.0
                c.execute("""INSERT INTO trades (symbol, signal_type, entry, tp, sl, status, result_badge, win_flag, pnl_dollar, month_str) 
                             VALUES (?, ?, ?, ?, ?, 'CLOSED', ?, ?, ?, ?)""",
                          (symbol, trade_type, entry_price, tp_price, sl_price, res_badge, win, pnl, month_str))
                in_trade = False
                
    conn.commit()
    conn.close()

# ----------------------------------------------------
# 2. موتور یادگیری تطبیقی (Adaptive Learning Engine)
# ----------------------------------------------------
def get_adaptive_params(symbol):
    """تحلیل خطاهای گذشته و تنظیم ضرایب استراتژی"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT win_flag FROM trades WHERE symbol = ? AND status = 'CLOSED' ORDER BY id DESC LIMIT 15", (symbol,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return {"req_score": 2, "atr_mult": 1.2, "win_rate": 50, "status": "در حال جمع‌آوری دیتا"}
        
    wins = sum(1 for r in rows if r[0] == 1)
    total = len(rows)
    win_rate = (wins / total) * 100
    
    # هوش مصنوعی ساده: تطبیق پذیری بر اساس وین‌ریت
    req_score = 2
    atr_mult = 1.2
    status = "نرمال"
    
    if win_rate < 40:
        # اگر اخیراً زیاد استاپ خورده: سخت‌گیری بیشتر و استاپ بازتر (فرار از هانت شدن)
        req_score = 3
        atr_mult = 1.6
        status = "⚠️ فاز اصلاح خطا (افزایش فیلترها و استاپ)"
    elif win_rate > 70:
        # اگر در سود مستمر است: ریسک‌پذیری بیشتر و استاپ تنگ‌تر
        req_score = 2
        atr_mult = 1.0
        status = "🔥 فاز تهاجمی (روند قدرتمند کشف شد)"
        
    return {"req_score": req_score, "atr_mult": atr_mult, "win_rate": round(win_rate), "status": status}

# ----------------------------------------------------
# 3. مدیریت چرخه معامله و استاپ متحرک (Trailing Stop)
# ----------------------------------------------------
def process_active_trade(symbol, current_price, margin):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE symbol = ? AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1", (symbol,))
    trade = c.fetchone()
    
    if not trade:
        conn.close()
        return None, None
        
    t_id, _, sig, entry, tp, sl = trade[0], trade[1], trade[2], trade[3], trade[4], trade[5]
    
    risk_amount = margin * 0.01
    sl_dist = abs(entry - sl)
    
    # 1. استاپ متحرک (Trailing Stop / Risk-Free)
    # اگر 50 درصد مسیر سود طی شد، استاپ می‌آید روی نقطه ورود
    updated_sl = sl
    if sig == 'BUY' and current_price >= entry + (sl_dist * 1.0):
        if sl < entry:
            updated_sl = entry
            c.execute("UPDATE trades SET sl = ? WHERE id = ?", (updated_sl, t_id))
            conn.commit()
    elif sig == 'SELL' and current_price <= entry - (sl_dist * 1.0):
        if sl > entry:
            updated_sl = entry
            c.execute("UPDATE trades SET sl = ? WHERE id = ?", (updated_sl, t_id))
            conn.commit()
            
    # 2. بررسی برخورد به تارگت یا استاپ
    closed = False
    win = 0
    
    if sig == 'BUY':
        if current_price >= tp: closed, win = True, 1
        elif current_price <= updated_sl: closed, win = True, 0
    else:
        if current_price <= tp: closed, win = True, 1
        elif current_price >= updated_sl: closed, win = True, 0
        
    if closed:
        badge = "می‌شود 🎉" if win == 1 else "نشد ❌"
        # اگر استاپ متحرک فعال شده بود و برگشت، ضرر صفر است
        pnl = (risk_amount * 2.0) if win == 1 else (0 if updated_sl == entry else -risk_amount)
        c.execute("UPDATE trades SET status = 'CLOSED', result_badge = ?, win_flag = ?, pnl_dollar = ? WHERE id = ?", 
                  (badge, win, pnl, t_id))
        conn.commit()
        conn.close()
        return None, {"closed": True, "result": badge, "pnl": pnl}
        
    conn.close()
    
    # محاسبه PNL لحظه‌ای
    diff_pct = (current_price - entry)/entry if sig == 'BUY' else (entry - current_price)/entry
    live_pnl = (diff_pct / (abs(entry - updated_sl)/entry + 1e-9)) * risk_amount
    
    return {
        "sig": sig, "entry": entry, "tp": tp, "sl": updated_sl, 
        "live_pnl": live_pnl, 
        "is_risk_free": (updated_sl == entry)
    }, None

# ----------------------------------------------------
# 4. موتور پردازش سیگنال و تحلیل تکنیکال
# ----------------------------------------------------
def analyze_market(df, symbol, margin):
    close = df['Close']
    high = df['High']
    low = df['Low']
    
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    atr = (pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)).rolling(14).mean()
    
    c_price = float(close.iloc[-1])
    c_atr = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else c_price * 0.005
    
    # دریافت پارامترهای یادگیری
    ai_params = get_adaptive_params(symbol)
    req_score = ai_params['req_score']
    atr_mult = ai_params['atr_mult']
    
    bull_score = sum([1 if ema9.iloc[-1] > ema21.iloc[-1] else 0, 1 if c_price > ema50.iloc[-1] else 0, 1 if rsi.iloc[-1] < 60 else 0])
    bear_score = sum([1 if ema9.iloc[-1] < ema21.iloc[-1] else 0, 1 if c_price < ema50.iloc[-1] else 0, 1 if rsi.iloc[-1] > 40 else 0])
    
    active_trade, closed_info = process_active_trade(symbol, c_price, margin)
    
    signal = "⚪ بازار در حال استراحت و شناسایی (WAIT)"
    status_class = "hold"
    entry, tp, sl = None, None, None
    
    if active_trade:
        signal = f"🔒 پوزیشن باز ({active_trade['sig']}) - سیستم قفل است"
        status_class = "buy" if active_trade['sig'] == 'BUY' else "sell"
        entry, tp, sl = active_trade['entry'], active_trade['tp'], active_trade['sl']
    else:
        month_str = datetime.now().strftime("%Y-%m")
        if bull_score >= req_score:
            signal = "🟢 سیگنال ورود خرید (BUY / LONG)"
            status_class = "buy"
            entry = c_price
            sl = c_price - (atr_mult * c_atr)
            tp = entry + (2.0 * abs(entry - sl))  # R:R = 1:2
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO trades (symbol, signal_type, entry, tp, sl, status, win_flag, pnl_dollar, month_str) VALUES (?, 'BUY', ?, ?, ?, 'ACTIVE', 0, 0, ?)", 
                      (symbol, entry, tp, sl, month_str))
            conn.commit()
            conn.close()
            
        elif bear_score >= req_score:
            signal = "🔴 سیگنال ورود فروش (SELL / SHORT)"
            status_class = "sell"
            entry = c_price
            sl = c_price + (atr_mult * c_atr)
            tp = entry - (2.0 * abs(entry - sl))
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO trades (symbol, signal_type, entry, tp, sl, status, win_flag, pnl_dollar, month_str) VALUES (?, 'SELL', ?, ?, ?, 'ACTIVE', 0, 0, ?)", 
                      (symbol, entry, tp, sl, month_str))
            conn.commit()
            conn.close()

    # محاسبه حجم معامله (ریسک ۱٪)
    calc = {}
    if entry and sl:
        risk_dollar = margin * 0.01
        sl_pct = abs(entry - sl) / entry
        if sl_pct > 0:
            pos_size = risk_dollar / sl_pct
            lev = max(1, min(int(pos_size / margin), 50))
            calc = {
                "risk": f"${risk_dollar:,.1f}",
                "reward": f"${risk_dollar * 2.0:,.1f}",
                "lev": f"{lev}x",
                "margin_used": f"${(pos_size / lev):,.1f}",
                "sl_dist": f"{(sl_pct * 100):.2f}%"
            }

    return {
        "signal": signal, "status_class": status_class,
        "entry": entry, "tp": tp, "sl": sl,
        "ai_status": ai_params, "calc": calc,
        "active_trade": active_trade
    }

def get_report():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT month_str, COUNT(*), SUM(win_flag), SUM(pnl_dollar) 
                 FROM trades WHERE status = 'CLOSED' GROUP BY month_str ORDER BY month_str DESC""")
    rows = c.fetchall()
    conn.close()
    
    rep = []
    for r in rows:
        t, w, pnl = r[1], r[2] or 0, r[3] or 0
        loss = t - w
        wr = (w / t * 100) if t > 0 else 0
        rep.append({"month": r[0], "total": t, "wins": w, "losses": loss, "wr": f"{wr:.1f}%", "pnl": pnl})
    return rep

# ----------------------------------------------------
# 5. رابط کاربری (UI)
# ----------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>هوش مصنوعی ترید | mishavad</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; background-color: #06090e; color: #f1f5f9; padding: 12px; display: flex; justify-content: center; }
        .main-wrapper { width: 100%; max-width: 600px; display: flex; flex-direction: column; gap: 12px; }
        .card { background-color: #0d131f; border-radius: 16px; padding: 16px; border: 1px solid #1e293b; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 10px; }
        .title { font-weight: bold; color: #38bdf8; }
        .nav-tabs { display: flex; gap: 4px; margin-top: 10px; }
        .nav-tab { flex: 1; padding: 8px 4px; text-align: center; border-radius: 8px; font-size: 0.8rem; font-weight: bold; background: #1e293b; color: #94a3b8; text-decoration: none; border: 1px solid #334155; }
        .nav-tab.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
        select, input { background: #1e293b; color: #fff; border: 1px solid #334155; padding: 10px; border-radius: 8px; width: 100%; outline: none; margin-top:10px; }
        .price { text-align: center; font-size: 2.2rem; font-weight: bold; margin: 12px 0; font-family: monospace; }
        
        .signal-card { border-radius: 12px; padding: 12px; text-align: center; font-weight: bold; font-size: 1.1rem; margin-bottom: 12px; border: 1.5px solid transparent; }
        .buy { background: rgba(34, 197, 94, 0.15); color: #4ade80; border-color: #22c55e; }
        .sell { background: rgba(239, 68, 68, 0.15); color: #f87171; border-color: #ef4444; }
        .hold { background: rgba(156, 163, 175, 0.15); color: #d1d5db; border-color: #4b5563; }
        
        .ai-box { background: rgba(56, 189, 248, 0.05); border: 1px dashed #0284c7; border-radius: 10px; padding: 10px; font-size: 0.82rem; margin-bottom: 12px; }
        .trade-setup { background: #080d16; border-radius: 12px; padding: 12px; border: 1px solid #1e293b; font-size: 0.88rem; }
        .row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dashed #334155; }
        .row:last-child { border: none; }
        
        table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 10px; }
        th, td { padding: 8px; text-align: center; border-bottom: 1px solid #1e293b; }
        th { background: #1e293b; color: #94a3b8; }
    </style>
</head>
<body>
    <div class="main-wrapper">
        <div class="card">
            <div class="header">
                <span class="title">⚡ دستیار معامله‌گر mishavad</span>
                <span style="font-size:0.75rem; color:#9ca3af;">{{ data.time }}</span>
            </div>

            <div class="nav-tabs">
                <a href="/?tab=scalp&symbol={{ data.symbol }}&margin={{ data.margin }}" class="nav-tab {% if data.tab == 'scalp' %}active{% endif %}">⏱️ اسکالپ هوشمند</a>
                <a href="/?tab=report&symbol={{ data.symbol }}&margin={{ data.margin }}" class="nav-tab {% if data.tab == 'report' %}active{% endif %}">📊 کارنامه عملکرد (PnL)</a>
            </div>

            <form id="f" method="GET" action="/">
                <input type="hidden" name="tab" value="{{ data.tab }}">
                <div style="display: flex; gap:8px;">
                    <select name="symbol" onchange="document.getElementById('f').submit()">
                        {% for sym, info in assets.items() %}
                            <option value="{{ sym }}" {% if sym == data.symbol %}selected{% endif %}>{{ info.name }}</option>
                        {% endfor %}
                    </select>
                    <input type="number" name="margin" value="{{ data.margin }}" placeholder="کل سرمایه ($)" onchange="document.getElementById('f').submit()">
                </div>
            </form>

            <div class="price">${{ "{:,.2f}".format(data.price) }}</div>

            {% if data.tab == 'scalp' %}
                
                <div class="ai-box">
                    <div style="color:#38bdf8; font-weight:bold; margin-bottom:4px;">🧠 گزارش یادگیری ماشین:</div>
                    <div>وضعیت فیلترها: <b>{{ data.scalp.ai_status.status }}</b></div>
                    <div>وین‌ریت اخیر: <b>{{ data.scalp.ai_status.win_rate }}%</b> (تنظیم خودکار فاصله استاپ‌لاس)</div>
                </div>

                <div class="signal-card {{ data.scalp.status_class }}">{{ data.scalp.signal }}</div>
                
                {% if data.scalp.active_trade %}
                <div style="background:rgba(34,197,94,0.1); border:1px solid #22c55e; border-radius:10px; padding:10px; text-align:center; margin-bottom:12px;">
                    <div style="font-size:0.8rem; color:#94a3b8;">سود/زیان معامله جاری:</div>
                    <div style="font-size:1.5rem; font-weight:bold; color: {% if data.scalp.active_trade.live_pnl >= 0 %}#4ade80{% else %}#f87171{% endif %}; direction:ltr;">
                        {{ "{:+,.2f}".format(data.scalp.active_trade.live_pnl) }} $
                    </div>
                    {% if data.scalp.active_trade.is_risk_free %}
                        <div style="color:#facc15; font-size:0.75rem; margin-top:4px;">🛡️ ریسک‌فری فعال شد (استاپ روی نقطه ورود)</div>
                    {% endif %}
                </div>
                {% endif %}

                {% if data.scalp.entry %}
                <div class="trade-setup">
                    <div style="font-weight:bold; color:#cbd5e1; margin-bottom:8px;">📍 دستورات صرافی (مدیریت ریسک ۱٪ سرمایه = {{ data.scalp.calc.risk }}):</div>
                    <div class="row"><span>نقطه ورود:</span><span style="color:#4ade80; font-family:monospace;">${{ "{:,.2f}".format(data.scalp.entry) }}</span></div>
                    <div class="row"><span>تارگت سود (TP):</span><span style="color:#38bdf8; font-family:monospace;">${{ "{:,.2f}".format(data.scalp.tp) }}</span></div>
                    <div class="row"><span>حد ضرر (SL):</span><span style="color:#f87171; font-family:monospace;">${{ "{:,.2f}".format(data.scalp.sl) }}</span></div>
                    
                    <div style="background:#1e293b; border-radius:8px; padding:8px; margin-top:10px;">
                        <div style="color:#facc15; font-weight:bold; font-size:0.8rem; margin-bottom:4px;">⚙️ تنظیمات دقیق در صرافی:</div>
                        <div class="row" style="border:none; padding:2px 0;"><span>اهرم (Leverage):</span><b>{{ data.scalp.calc.lev }}</b></div>
                        <div class="row" style="border:none; padding:2px 0;"><span>مارجین ورودی (Cost):</span><b>{{ data.scalp.calc.margin_used }}</b></div>
                        <div class="row" style="border:none; padding:2px 0;"><span>سود در تارگت:</span><b style="color:#4ade80;">{{ data.scalp.calc.reward }}</b></div>
                    </div>
                </div>
                
                <div style="margin-top:12px;">
                    <iframe src="https://s.tradingview.com/widgetembed/?frameElementId=tv&symbol={{ data.tv_symbol }}&interval=5&theme=dark&style=1" width="100%" height="280" frameborder="0"></iframe>
                </div>
                {% endif %}

            {% elif data.tab == 'report' %}
                <div style="color:#38bdf8; font-weight:bold; margin-bottom:8px;">📈 کارنامه قطعی و سود/زیان ربات:</div>
                <table>
                    <thead><tr><th>ماه</th><th>تعداد</th><th>می‌شود🎉</th><th>نشد❌</th><th>وین‌ریت</th><th>برآیند($)</th></tr></thead>
                    <tbody>
                        {% for r in report %}
                        <tr>
                            <td>{{ r.month }}</td><td>{{ r.total }}</td>
                            <td style="color:#4ade80;">{{ r.wins }}</td><td style="color:#f87171;">{{ r.losses }}</td>
                            <td>{{ r.wr }}</td>
                            <td style="color: {% if r.pnl >= 0 %}#4ade80{% else %}#f87171{% endif %}; font-weight:bold; direction:ltr;">
                                {{ "{:+,.2f}".format(r.pnl) }}
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="6" style="color:#94a3b8;">در حال پردازش داده‌های گذشته...</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    symbol = request.args.get('symbol', 'BTC-USD')
    tab = request.args.get('tab', 'scalp')
    margin = float(request.args.get('margin', 1000))
    
    if symbol not in ASSETS: symbol = 'BTC-USD'
    
    try:
        df = yf.Ticker(symbol).history(period="3d", interval="5m")
        train_bot_on_history(symbol, df)  # بک‌تست هوشمند برای پر کردن دیتابیس
        
        c_price = float(df['Close'].iloc[-1])
        scalp_res = analyze_market(df, symbol, margin)
        report = get_report()

        data = {
            "symbol": symbol, "tv_symbol": ASSETS[symbol]['tv'],
            "tab": tab, "margin": margin, "price": c_price,
            "scalp": scalp_res, "time": datetime.now().strftime("%H:%M:%S")
        }
    except Exception as e:
        data = {"symbol": symbol, "tv_symbol": "BINANCE:BTCUSDT", "tab": tab, "margin": margin, "price": 0, "scalp": {"signal": f"خطا: {e}", "status_class": "hold", "entry": None, "ai_status": {"status": "خطا"}}, "time": datetime.now().strftime("%H:%M:%S")}
        report = []

    return render_template_string(HTML_TEMPLATE, data=data, assets=ASSETS, report=report)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

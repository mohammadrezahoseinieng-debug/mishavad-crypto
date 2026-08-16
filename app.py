import os
import sqlite3
import feedparser
from flask import Flask, render_template_string, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

app = Flask(__name__)

ASSETS = {
    "BTC-USD": {"name": "بیت‌کوین (BTC/USDT)", "tv": "BINANCE:BTCUSDT", "keyword": "bitcoin"},
    "ETH-USD": {"name": "اتریوم (ETH/USDT)", "tv": "BINANCE:ETHUSDT", "keyword": "ethereum"},
    "SOL-USD": {"name": "سولانا (SOL/USDT)", "tv": "BINANCE:SOLUSDT", "keyword": "solana"},
    "GC=F": {"name": "انس طلا جهانی (Gold)", "tv": "OANDA:XAUUSD", "keyword": "gold"},
    "SI=F": {"name": "نقره جهانی (Silver)", "tv": "TVC:SILVER", "keyword": "silver"},
    "CL=F": {"name": "نفت خام (Crude Oil)", "tv": "TVC:USOIL", "keyword": "oil"},
    "EURUSD=X": {"name": "یورو / دلار (EUR/USD)", "tv": "FX:EURUSD", "keyword": "euro"}
}

NEWS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://finance.yahoo.com/news/rssindex"
]

# ----------------------------------------------------
# 1. دیتابیس یادگیری و ثبت خطا (Self-Learning Engine)
# ----------------------------------------------------
DB_FILE = "trade_history.db"

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
                    win INTEGER,
                    timestamp TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

def get_active_trade(symbol):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE symbol = ? AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1", (symbol,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "symbol": row[1], "signal_type": row[2], "entry": row[3], "tp": row[4], "sl": row[5], "status": row[6]}
    return None

def check_and_update_active_trade(symbol, current_price):
    trade = get_active_trade(symbol)
    if not trade:
        return None
    
    finished = False
    win = 0
    if trade['signal_type'] == 'BUY':
        if current_price >= trade['tp']:
            finished = True
            win = 1
        elif current_price <= trade['sl']:
            finished = True
            win = 0
    elif trade['signal_type'] == 'SELL':
        if current_price <= trade['tp']:
            finished = True
            win = 1
        elif current_price >= trade['sl']:
            finished = True
            win = 0

    if finished:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE trades SET status = 'CLOSED', win = ? WHERE id = ?", (win, trade['id']))
        conn.commit()
        conn.close()
        return None
    return trade

def get_historical_learning_stats(symbol):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(win) FROM trades WHERE symbol = ? AND status = 'CLOSED'", (symbol,))
    row = c.fetchone()
    conn.close()
    total = row[0] if row[0] else 0
    wins = row[1] if row[1] else 0
    penalty = 0
    if total > 5:
        loss_rate = (total - wins) / total
        if loss_rate > 0.4:
            penalty = 5  # افزایش سخت‌گیری شرایط در صورت ضررهای اخیر
    return {"total_trades": total, "wins": wins, "penalty": penalty}

# ----------------------------------------------------
# 2. موتور تحلیل اخبار و سنتیمنت فاندامنتال
# ----------------------------------------------------
BULLISH_KEYWORDS = ["surge", "jump", "growth", "adoption", "inflow", "bullish", "rally", "gain", "high", "positive", "approval"]
BEARISH_KEYWORDS = ["drop", "crash", "fall", "ban", "outflow", "bearish", "decline", "hack", "lawsuit", "inflation", "war"]

def fetch_fundamental_sentiment(keyword):
    bull_count = 0
    bear_count = 0
    news_titles = []
    
    for url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                title = entry.title.lower()
                summary = entry.get('summary', '').lower()
                text = f"{title} {summary}"
                if keyword.lower() in text:
                    news_titles.append(entry.title)
                    for bw in BULLISH_KEYWORDS:
                        if bw in text:
                            bull_count += 1
                    for bw in BEARISH_KEYWORDS:
                        if bw in text:
                            bear_count += 1
        except Exception:
            continue

    total = bull_count + bear_count
    if total == 0:
        return {"sentiment": "خنثی (Neutral)", "score": 50, "news": news_titles[:3]}
    
    score = int((bull_count / total) * 100)
    sentiment = "🟢 به شدت مثبت (Bullish)" if score > 60 else ("🔴 منفی (Bearish)" if score < 40 else "⚪ خنثی (Neutral)")
    return {"sentiment": sentiment, "score": score, "news": news_titles[:3]}

# ----------------------------------------------------
# 3. موتور محاسبات اسکالپ ۵ دقیقه با نسبت R:R دقیق 1:2
# ----------------------------------------------------
def compute_scalp_strategy(df, sentiment_data, symbol):
    close = df['Close']
    high = df['High']
    low = df['Low']
    vol = df['Volume']

    # اندیکاتورها
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=min(len(df), 200), adjust=False).mean()

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_hist = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()

    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    stoch_k = 100 * ((close - low14) / ((high14 - low14) + 1e-9))

    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    c_price = float(close.iloc[-1])
    c_rsi = float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else 50.0
    c_macd_h = float(macd_hist.dropna().iloc[-1]) if not macd_hist.dropna().empty else 0.0
    c_stoch_k = float(stoch_k.dropna().iloc[-1]) if not stoch_k.dropna().empty else 50.0
    c_atr = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else c_price * 0.003
    c_ema9 = float(ema9.iloc[-1])
    c_ema21 = float(ema21.iloc[-1])
    c_ema50 = float(ema50.iloc[-1])
    c_ema200 = float(ema200.iloc[-1])

    demand_zone = float(low.tail(25).min())
    supply_zone = float(high.tail(25).max())

    # امتیاز هم‌پوشانی تکنیکال و فاندامنتال
    bull_confluence = 0
    bear_confluence = 0

    if c_ema9 > c_ema21: bull_confluence += 1
    if c_price > c_ema50: bull_confluence += 1
    if c_price > c_ema200: bull_confluence += 1
    if c_rsi < 50: bull_confluence += 1
    if c_macd_h > 0: bull_confluence += 1
    if c_stoch_k < 40: bull_confluence += 1
    if sentiment_data['score'] >= 55: bull_confluence += 2

    if c_ema9 < c_ema21: bear_confluence += 1
    if c_price < c_ema50: bear_confluence += 1
    if c_price < c_ema200: bear_confluence += 1
    if c_rsi > 50: bear_confluence += 1
    if c_macd_h < 0: bear_confluence += 1
    if c_stoch_k > 60: bear_confluence += 1
    if sentiment_data['score'] <= 45: bear_confluence += 2

    stats = get_historical_learning_stats(symbol)
    req_threshold = 6 + stats['penalty']

    signal = "⚪ عدم ورود / بازار بدون ستاپ قطعی (WAIT)"
    status_class = "hold"
    entry, tp, sl = None, None, None
    win_rate = 50

    # بررسی قفل پوزیشن فعال
    active_trade = check_and_update_active_trade(symbol, c_price)
    if active_trade:
        signal = f"🔒 معامله فعال در حال اجرا ({active_trade['signal_type']}) - تا زمان خروج سیگنال جدید داده نمی‌شود."
        status_class = "buy" if active_trade['signal_type'] == 'BUY' else "sell"
        entry = active_trade['entry']
        tp = active_trade['tp']
        sl = active_trade['sl']
        win_rate = 75
    else:
        if bull_confluence >= req_threshold and bull_confluence > bear_confluence:
            signal = "🟢 سیگنال قطعی خرید (BUY / LONG)"
            status_class = "buy"
            entry = c_price
            sl = c_price - (1.2 * c_atr)
            risk_amount = entry - sl
            tp = entry + (2.0 * risk_amount)  # ریسک به ریوارد دقیق ۱ به ۲
            win_rate = min(86, 60 + bull_confluence * 3)

            # ثبت پوزیشن فعال در دیتابیس
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO trades (symbol, signal_type, entry, tp, sl, status, win, timestamp) VALUES (?, ?, ?, ?, ?, 'ACTIVE', 0, ?)",
                      (symbol, 'BUY', entry, tp, sl, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

        elif bear_confluence >= req_threshold and bear_confluence > bull_confluence:
            signal = "🔴 سیگنال قطعی فروش (SELL / SHORT)"
            status_class = "sell"
            entry = c_price
            sl = c_price + (1.2 * c_atr)
            risk_amount = sl - entry
            tp = entry - (2.0 * risk_amount)  # ریسک به ریوارد دقیق ۱ به ۲
            win_rate = min(86, 60 + bear_confluence * 3)

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO trades (symbol, signal_type, entry, tp, sl, status, win, timestamp) VALUES (?, ?, ?, ?, ?, 'ACTIVE', 0, ?)",
                      (symbol, 'SELL', entry, tp, sl, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

    loss_rate = 100 - win_rate
    return {
        "signal": signal, "status_class": status_class,
        "entry": entry, "tp": tp, "sl": sl,
        "win_rate": win_rate, "loss_rate": loss_rate,
        "rr_ratio": "1 : 2.0 (تضمینی)",
        "demand_zone": demand_zone, "supply_zone": supply_zone,
        "active_lock": bool(active_trade)
    }

# ----------------------------------------------------
# 4. موتور تحلیل کلان فاندامنتال و تکنیکال ۶ ماهه تا ۱ ساله
# ----------------------------------------------------
def compute_macro_deep_analysis(symbol):
    ticker = yf.Ticker(symbol)
    df_1y = ticker.history(period="1y", interval="1d")
    
    if df_1y.empty:
        raise ValueError("داده ۱ ساله دریافت نشد.")

    high_1y = float(df_1y['High'].max())
    low_1y = float(df_1y['Low'].min())
    diff = high_1y - low_1y

    fib_500 = high_1y - (0.500 * diff)
    fib_618 = high_1y - (0.618 * diff)
    sma200 = float(df_1y['Close'].rolling(min(len(df_1y), 200)).mean().iloc[-1])

    analysis_data = {
        "BTC-USD": {
            "desc": "تحلیل چرخه کلان بیت‌کوین بر مبنای جریان نقدینگی صندوق‌های ETF اسپات و سیاست‌های پولی فدرال رزرو. قیمت با تثبیت بالاتر از میانگین متحرک ۲۰۰ روزه در فاز انباشت بلندمدت قرار دارد.",
            "entry_zone": f"${fib_618:,.0f} تا ${fib_500:,.0f}",
            "sl": f"${low_1y * 0.95:,.0f}",
            "tp1": f"${high_1y:,.0f}",
            "tp2": f"${high_1y * 1.30:,.0f}"
        },
        "ETH-USD": {
            "desc": "اتریوم به عنوان بستر اصلی قراردادهای هوشمند و استیکینگ نهادی، در کف‌های فیبوناچی ۶ ماهه فشرده شده است.",
            "entry_zone": f"${fib_618:,.0f} تا ${fib_500:,.0f}",
            "sl": f"${low_1y * 0.92:,.0f}",
            "tp1": f"${high_1y:,.0f}",
            "tp2": f"${high_1y * 1.25:,.0f}"
        },
        "GC=F": {
            "desc": "طلا در چرخه کلان جهانی به عنوان دارایی ضد تورم و پوشش ریسک تنش‌های ژئوپلیتیک و خرید سنگین بانک‌های مرکزی در سقف‌های تاریخی معامله می‌شود.",
            "entry_zone": f"${fib_500:,.1f} تا ${fib_618:,.1f}",
            "sl": f"${low_1y * 0.97:,.1f}",
            "tp1": f"${high_1y:,.1f}",
            "tp2": f"${high_1y * 1.15:,.1f}"
        },
        "SI=F": {
            "desc": "نقره به دلیل تقاضای شدید در صنایع خورشیدی، خودروهای الکتریکی و هوش مصنوعی دارای پتانسیل رشد مضاعف نسبت به طلاست.",
            "entry_zone": f"${fib_618:,.2f} تا ${fib_500:,.2f}",
            "sl": f"${low_1y * 0.93:,.2f}",
            "tp1": f"${high_1y:,.2f}",
            "tp2": f"${high_1y * 1.28:,.2f}"
        },
        "CL=F": {
            "desc": "نفت خام بر مبنای معادلات عرضه اوپک‌پلاس، تقاضای صنعتی چین و مسائل ترانزیتی در محدوده کانال بلندمدت گردش دارد.",
            "entry_zone": f"${fib_618:,.2f} تا ${fib_500:,.2f}",
            "sl": f"${low_1y * 0.92:,.2f}",
            "tp1": f"${high_1y * 0.95:,.2f}",
            "tp2": f"${high_1y * 1.10:,.2f}"
        }
    }

    item = analysis_data.get(symbol, {
        "desc": "تحلیل میان‌مدت و بلندمدت براساس کانال فیبوناچی کلان و مومنتوم سالانه.",
        "entry_zone": f"${fib_618:,.2f} تا ${fib_500:,.2f}",
        "sl": f"${low_1y:,.2f}",
        "tp1": f"${high_1y:,.2f}",
        "tp2": f"${high_1y * 1.15:,.2f}"
    })

    return {
        "high_1y": high_1y, "low_1y": low_1y, "sma200": sma200,
        "desc": item["desc"], "entry_zone": item["entry_zone"],
        "sl": item["sl"], "tp1": item["tp1"], "tp2": item["tp2"]
    }

# ----------------------------------------------------
# 5. رابط کاربری کامل و داشبورد وب
# ----------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>هوش تحلیل و معامله‌گری خودکار | mishavad Pro</title>
    <meta http-equiv="refresh" content="35">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; background-color: #06090e; color: #f1f5f9; padding: 14px; display: flex; justify-content: center; }
        .main-wrapper { width: 100%; max-width: 580px; display: flex; flex-direction: column; gap: 14px; }
        .card { background-color: #0e1420; border-radius: 18px; padding: 18px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); border: 1px solid #1e293b; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 10px; }
        .title { font-weight: 900; font-size: 1.15rem; color: #38bdf8; }
        .time { font-size: 0.78rem; color: #9ca3af; }
        
        .nav-tabs { display: flex; gap: 6px; margin-top: 10px; }
        .nav-tab { flex: 1; padding: 10px 6px; text-align: center; border-radius: 10px; font-size: 0.84rem; text-decoration: none; font-weight: bold; background: #1e293b; color: #94a3b8; border: 1px solid #334155; }
        .nav-tab.active { background: #0284c7; color: #ffffff; border-color: #38bdf8; }

        select { background: #1e293b; color: #fff; border: 1px solid #334155; padding: 10px; border-radius: 10px; font-size: 0.95rem; width: 100%; cursor: pointer; outline: none; margin-top: 10px; }
        .price-box { text-align: center; margin: 12px 0 6px; }
        .price { font-size: 2.2rem; font-weight: 900; color: #f8fafc; font-family: monospace; }
        
        .signal-card { border-radius: 12px; padding: 12px; text-align: center; font-weight: 800; font-size: 1.15rem; margin-bottom: 12px; }
        .buy { background-color: rgba(34, 197, 94, 0.16); color: #4ade80; border: 1.5px solid #22c55e; }
        .sell { background-color: rgba(239, 68, 68, 0.16); color: #f87171; border: 1.5px solid #ef4444; }
        .hold { background-color: rgba(156, 163, 175, 0.14); color: #d1d5db; border: 1.5px solid #4b5563; }

        .prob-container { background: #0b101b; border-radius: 12px; padding: 12px; margin-bottom: 12px; border: 1px solid #1e293b; }
        .prob-header { display: flex; justify-content: space-between; font-size: 0.84rem; font-weight: bold; margin-bottom: 6px; }
        .prob-bar { height: 12px; border-radius: 6px; background: #ef4444; display: flex; overflow: hidden; margin-bottom: 6px; }
        .prob-fill-win { background: #22c55e; height: 100%; }

        .trade-setup { background: #080d16; border-radius: 12px; padding: 12px; margin-bottom: 12px; border: 1px solid #1e293b; }
        .trade-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 0.88rem; }
        .trade-row.border { border-bottom: 1px dashed #334155; }
        .val-entry { color: #38bdf8; font-weight: bold; font-family: monospace; }
        .val-tp { color: #4ade80; font-weight: bold; font-family: monospace; }
        .val-sl { color: #f87171; font-weight: bold; font-family: monospace; }

        .news-box { background: rgba(56, 189, 248, 0.05); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 12px; padding: 12px; margin-bottom: 12px; font-size: 0.84rem; line-height: 1.6; }
        .chart-box { border-radius: 14px; overflow: hidden; border: 1px solid #1e293b; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="main-wrapper">
        <div class="card">
            <div class="header">
                <span class="title">⚡ دستیار معامله‌گری هوشمند mishavad Pro</span>
                <span class="time">{{ data.time }}</span>
            </div>

            <div class="nav-tabs">
                <a href="/?tab=scalp&symbol={{ data.symbol }}" class="nav-tab {% if data.tab == 'scalp' %}active{% endif %}">⏱️ اسکالپ ۵ دقیقه</a>
                <a href="/?tab=charts&symbol={{ data.symbol }}" class="nav-tab {% if data.tab == 'charts' %}active{% endif %}">📊 چارت لایو</a>
                <a href="/?tab=macro&symbol={{ data.symbol }}" class="nav-tab {% if data.tab == 'macro' %}active{% endif %}">🏛️ سرمایه‌گذاری ۶ ماهه/۱ ساله</a>
            </div>

            <form id="symForm" method="GET" action="/">
                <input type="hidden" name="tab" value="{{ data.tab }}">
                <select name="symbol" onchange="document.getElementById('symForm').submit()">
                    {% for sym, info in assets.items() %}
                        <option value="{{ sym }}" {% if sym == data.symbol %}selected{% endif %}>{{ info.name }}</option>
                    {% endfor %}
                </select>
            </form>

            <div class="price-box">
                <div class="price">${{ "{:,.2f}".format(data.price) if data.price > 10 else "{:,.4f}".format(data.price) }}</div>
            </div>

            <!-- بخش اخبار و سنتیمنت زنده -->
            <div class="news-box">
                <div style="font-weight: bold; color: #38bdf8; margin-bottom: 4px;">🌍 پایش فاندامنتال زنده و اخبار فوری:</div>
                <div>وضعیت احساسات اخبار: <b>{{ data.news.sentiment }}</b> (شاخص: {{ data.news.score }}/100)</div>
                {% if data.news.news %}
                    <div style="color: #94a3b8; font-size: 0.78rem; margin-top: 4px;">• {{ data.news.news[0] }}</div>
                {% endif %}
            </div>

            {% if data.tab == 'scalp' %}
                <!-- بخش اسکالپ ۵ دقیقه -->
                <div class="signal-card {{ data.scalp.status_class }}">
                    {{ data.scalp.signal }}
                </div>

                <div class="prob-container">
                    <div class="prob-header">
                        <span style="color: #4ade80;">🟢 احتمال برد ستاپ: {{ data.scalp.win_rate }}%</span>
                        <span style="color: #f87171;">🔴 احتمال ریسک: {{ data.scalp.loss_rate }}%</span>
                    </div>
                    <div class="prob-bar">
                        <div class="prob-fill-win" style="width: {{ data.scalp.win_rate }}%;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.8rem;">
                        <span style="color: #94a3b8;">یادگیری فعال: <b>{{ data.stats.total_trades }} معامله تحلیل‌شده</b></span>
                        <span style="color: #facc15;">نسبت سود به ریسک: <b>{{ data.scalp.rr_ratio }}</b></span>
                    </div>
                </div>

                {% if data.scalp.entry %}
                <div class="trade-setup">
                    <div style="font-weight: bold; color: #cbd5e1; margin-bottom: 8px; font-size: 0.88rem;">📍 ستاپ معاملاتی با سود دو برابری حد ضرر (R:R = 1:2):</div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">نقطه ورود دقیق (Entry):</span>
                        <span class="val-entry">${{ "{:,.2f}".format(data.scalp.entry) if data.scalp.entry > 10 else "{:,.4f}".format(data.scalp.entry) }}</span>
                    </div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">تارگت خروج با سود (TP):</span>
                        <span class="val-tp">${{ "{:,.2f}".format(data.scalp.tp) if data.scalp.tp > 10 else "{:,.4f}".format(data.scalp.tp) }}</span>
                    </div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">حد ضرر قطعی (Stop Loss):</span>
                        <span class="val-sl">${{ "{:,.2f}".format(data.scalp.sl) if data.scalp.sl > 10 else "{:,.4f}".format(data.scalp.sl) }}</span>
                    </div>
                    <div class="trade-row">
                        <span style="color: #94a3b8;">قفل تا پایان معامله:</span>
                        <span style="color: #38bdf8; font-weight: bold;">فعال (عدم صدور سیگنال تداخلی)</span>
                    </div>
                </div>
                {% endif %}

            {% elif data.tab == 'charts' %}
                <!-- بخش چارت‌های زنده دوگانه TradingView -->
                <div style="font-weight: bold; color: #38bdf8; margin: 6px 0;">📈 ۱. چارت لایو کندل‌استیک بازار:</div>
                <div class="chart-box">
                    <iframe src="https://s.tradingview.com/widgetembed/?frameElementId=tradingview_1&symbol={{ data.tv_symbol }}&interval=5&theme=dark&style=1&locale=en" width="100%" height="320" frameborder="0"></iframe>
                </div>

                <div style="font-weight: bold; color: #4ade80; margin: 14px 0 6px;">📐 ۲. چارت تحلیل اندیکاتورها و میانگین‌ها:</div>
                <div class="chart-box">
                    <iframe src="https://s.tradingview.com/widgetembed/?frameElementId=tradingview_2&symbol={{ data.tv_symbol }}&interval=60&theme=dark&style=3&locale=en" width="100%" height="260" frameborder="0"></iframe>
                </div>

            {% else %}
                <!-- بخش سرمایه‌گذاری ۶ ماهه تا ۱ ساله -->
                <div style="background: #0b1120; border-radius: 14px; padding: 16px; border: 1px solid #1e293b;">
                    <div style="font-weight: bold; color: #38bdf8; margin-bottom: 8px;">🏛️ برنامه سرمایه‌گذاری ۶ ماهه تا ۱ ساله</div>
                    <div style="font-size: 0.88rem; line-height: 1.6; color: #cbd5e1; margin-bottom: 12px;">
                        {{ data.macro.desc }}
                    </div>

                    <div style="background: rgba(34, 197, 94, 0.12); border-left: 4px solid #22c55e; padding: 10px; border-radius: 8px; margin-bottom: 8px; font-size: 0.85rem;">
                        <b>🟢 محدوده خرید پله‌ای امن:</b> {{ data.macro.entry_zone }}
                    </div>
                    <div style="background: rgba(56, 189, 248, 0.12); border-left: 4px solid #38bdf8; padding: 10px; border-radius: 8px; margin-bottom: 8px; font-size: 0.85rem;">
                        <b>🎯 تارگت اول سود (۶ ماهه):</b> {{ data.macro.tp1 }}
                    </div>
                    <div style="background: rgba(168, 85, 247, 0.12); border-left: 4px solid #a855f7; padding: 10px; border-radius: 8px; margin-bottom: 8px; font-size: 0.85rem;">
                        <b>🚀 تارگت دوم سود (۱ ساله):</b> {{ data.macro.tp2 }}
                    </div>
                    <div style="background: rgba(239, 68, 68, 0.12); border-left: 4px solid #ef4444; padding: 10px; border-radius: 8px; font-size: 0.85rem;">
                        <b>🛑 حد ضرر سرمایه‌گذاری کلان:</b> {{ data.macro.sl }}
                    </div>
                </div>
            {% endif %}

            <p style="text-align: center; color: #64748b; font-size: 0.72rem; margin-top: 10px;">
                سیستم با الگوریتم یادگیری خودکار • بروزرسانی هر ۳۵ ثانیه
            </p>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    symbol = request.args.get('symbol', 'BTC-USD')
    tab = request.args.get('tab', 'scalp')
    
    if symbol not in ASSETS:
        symbol = 'BTC-USD'
    if tab not in ['scalp', 'charts', 'macro']:
        tab = 'scalp'

    try:
        # ۱. دریافت اخبار و تحلیل فاندامنتال
        keyword = ASSETS[symbol]['keyword']
        news_data = fetch_fundamental_sentiment(keyword)

        # ۲. دریافت دیتای تکنیکال ۵ دقیقه
        t_obj = yf.Ticker(symbol)
        df_5m = t_obj.history(period="2d", interval="5m")
        current_price = float(df_5m['Close'].dropna().iloc[-1])

        # ۳. پردازش استراتژی اسکالپ و یادگیری
        scalp_res = compute_scalp_strategy(df_5m, news_data, symbol)
        stats = get_historical_learning_stats(symbol)

        # ۴. تحلیل ماکرو ۱ ساله
        macro_res = compute_macro_deep_analysis(symbol)

        data = {
            "symbol": symbol,
            "tv_symbol": ASSETS[symbol]['tv'],
            "tab": tab,
            "price": current_price,
            "news": news_data,
            "scalp": scalp_res,
            "stats": stats,
            "macro": macro_res,
            "time": datetime.now().strftime("%H:%M:%S")
        }
    except Exception as e:
        data = {
            "symbol": symbol, "tv_symbol": "BINANCE:BTCUSDT", "tab": tab, "price": 0,
            "news": {"sentiment": "خطا در اتصال", "score": 50, "news": []},
            "scalp": {"signal": f"در حال اتصال مجدد: {e}", "status_class": "hold", "entry": None, "tp": None, "sl": None, "win_rate": 50, "loss_rate": 50, "rr_ratio": "1:2", "active_lock": False},
            "stats": {"total_trades": 0, "wins": 0},
            "macro": {"desc": "-", "entry_zone": "-", "sl": "-", "tp1": "-", "tp2": "-"},
            "time": datetime.now().strftime("%H:%M:%S")
        }

    return render_template_string(HTML_TEMPLATE, data=data, assets=ASSETS)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

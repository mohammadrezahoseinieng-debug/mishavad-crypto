import os
from flask import Flask, render_template_string, request
import yfinance as yf
import pandas as pd
from datetime import datetime

app = Flask(__name__)

ASSETS = {
    "BTC-USD": "بیت‌کوین (BTC/USDT)",
    "ETH-USD": "اتریوم (ETH/USDT)",
    "SOL-USD": "سولانا (SOL/USDT)",
    "GC=F": "انس طلا جهانی (Gold)",
    "EURUSD=X": "یورو / دلار (EUR/USD)"
}

HTML_PAGE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>دستیار اسکالپ هوشمند | mishavad</title>
    <meta http-equiv="refresh" content="25">
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background-color: #0b0f19; 
            color: #f3f4f6; 
            margin: 0; 
            padding: 16px; 
            display: flex; 
            justify-content: center; 
        }
        .container { 
            background-color: #111827; 
            border-radius: 20px; 
            padding: 20px; 
            width: 100%; 
            max-width: 480px; 
            box-shadow: 0 12px 30px rgba(0,0,0,0.6); 
            border: 1px solid #1f2937; 
        }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1f2937; padding-bottom: 12px; }
        .title { font-weight: 800; font-size: 1.1rem; color: #38bdf8; }
        .time { font-size: 0.8rem; color: #9ca3af; }
        
        .control-panel { margin: 16px 0; display: flex; gap: 8px; flex-direction: column; }
        select { 
            background: #1f2937; color: #fff; border: 1px solid #374151; padding: 10px; 
            border-radius: 10px; font-size: 0.95rem; width: 100%; cursor: pointer; outline: none;
        }
        .tf-group { display: flex; gap: 8px; margin-top: 4px; }
        .tf-btn {
            flex: 1; padding: 8px; text-align: center; border-radius: 8px; font-size: 0.85rem;
            text-decoration: none; font-weight: bold; background: #1f2937; color: #9ca3af; border: 1px solid #374151;
        }
        .tf-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }

        .price-box { text-align: center; margin: 14px 0 8px; }
        .price { font-size: 2.3rem; font-weight: 900; color: #f8fafc; font-family: monospace; }
        
        .signal-card { border-radius: 14px; padding: 14px; text-align: center; font-weight: 800; font-size: 1.2rem; margin-bottom: 16px; }
        .buy { background-color: rgba(34, 197, 94, 0.18); color: #4ade80; border: 1.5px solid #22c55e; }
        .sell { background-color: rgba(239, 68, 68, 0.18); color: #f87171; border: 1.5px solid #ef4444; }
        .hold { background-color: rgba(156, 163, 175, 0.15); color: #d1d5db; border: 1.5px solid #4b5563; }

        .trade-setup { background: #0f172a; border-radius: 12px; padding: 14px; margin-bottom: 16px; border: 1px solid #1e293b; }
        .trade-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 0.92rem; }
        .trade-row.border { border-bottom: 1px dashed #334155; }
        .val-entry { color: #38bdf8; font-weight: bold; font-family: monospace; }
        .val-tp { color: #4ade80; font-weight: bold; font-family: monospace; }
        .val-sl { color: #f87171; font-weight: bold; font-family: monospace; }
        
        .metrics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }
        .metric-box { background: #1f2937; padding: 8px 12px; border-radius: 8px; font-size: 0.82rem; }
        .metric-title { color: #9ca3af; margin-bottom: 2px; }
        .metric-val { font-weight: bold; font-family: monospace; font-size: 0.95rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="title">🎯 دستیار معاملات اسکالپ</span>
            <span class="time">{{ data.time }}</span>
        </div>

        <div class="control-panel">
            <form id="symbolForm" method="GET" action="/">
                <input type="hidden" name="tf" value="{{ data.tf }}">
                <select name="symbol" onchange="document.getElementById('symbolForm').submit()">
                    {% for sym, label in assets.items() %}
                        <option value="{{ sym }}" {% if sym == data.symbol %}selected{% endif %}>{{ label }}</option>
                    {% endfor %}
                </select>
            </form>
            
            <div class="tf-group">
                <a href="/?symbol={{ data.symbol }}&tf=5m" class="tf-btn {% if data.tf == '5m' %}active{% endif %}">⏱️ اسکالپ ۵ دقیقه</a>
                <a href="/?symbol={{ data.symbol }}&tf=15m" class="tf-btn {% if data.tf == '15m' %}active{% endif %}">⏱️ اسکالپ ۱۵ دقیقه</a>
            </div>
        </div>

        <div class="price-box">
            <div class="price">${{ "{:,.2f}".format(data.price) if data.price > 10 else "{:,.4f}".format(data.price) }}</div>
        </div>

        <div class="signal-card {{ data.status_class }}">
            {{ data.signal }}
        </div>

        {% if data.entry %}
        <div class="trade-setup">
            <div style="font-weight: bold; color: #cbd5e1; margin-bottom: 8px; font-size: 0.9rem;">📍 ستاپ معاملاتی پیشنهادی:</div>
            <div class="trade-row border">
                <span style="color: #94a3b8;">نقطه ورود (Entry):</span>
                <span class="val-entry">${{ "{:,.2f}".format(data.entry) if data.entry > 10 else "{:,.4f}".format(data.entry) }}</span>
            </div>
            <div class="trade-row border">
                <span style="color: #94a3b8;">تارگت اول (TP 1):</span>
                <span class="val-tp">${{ "{:,.2f}".format(data.tp1) if data.tp1 > 10 else "{:,.4f}".format(data.tp1) }}</span>
            </div>
            <div class="trade-row border">
                <span style="color: #94a3b8;">تارگت دوم (TP 2):</span>
                <span class="val-tp">${{ "{:,.2f}".format(data.tp2) if data.tp2 > 10 else "{:,.4f}".format(data.tp2) }}</span>
            </div>
            <div class="trade-row">
                <span style="color: #94a3b8;">حد ضرر (Stop Loss):</span>
                <span class="val-sl">${{ "{:,.2f}".format(data.sl) if data.sl > 10 else "{:,.4f}".format(data.sl) }}</span>
            </div>
        </div>
        {% endif %}

        <div class="metrics-grid">
            <div class="metric-box">
                <div class="metric-title">شاخص RSI:</div>
                <div class="metric-val">{{ "{:.2f}".format(data.rsi) }}</div>
            </div>
            <div class="metric-box">
                <div class="metric-title">میانگین EMA 9:</div>
                <div class="metric-val">${{ "{:,.2f}".format(data.ema9) if data.ema9 > 10 else "{:,.4f}".format(data.ema9) }}</div>
            </div>
            <div class="metric-box">
                <div class="metric-title">میانگین EMA 21:</div>
                <div class="metric-val">${{ "{:,.2f}".format(data.ema21) if data.ema21 > 10 else "{:,.4f}".format(data.ema21) }}</div>
            </div>
            <div class="metric-box">
                <div class="metric-title">نوسان لحظه‌ای (ATR):</div>
                <div class="metric-val">${{ "{:,.2f}".format(data.atr) if data.atr > 10 else "{:,.4f}".format(data.atr) }}</div>
            </div>
        </div>

        <p style="text-align: center; color: #64748b; font-size: 0.72rem; margin: 8px 0 0;">
            بروزرسانی خودکار هر ۲۵ ثانیه • مدیریت سرمایه الزامی است
        </p>
    </div>
</body>
</html>
"""

def compute_scalp_analysis(symbol='BTC-USD', timeframe='5m'):
    # دریافت داده برای اسکالپ (۱ روز گذشته در تایم‌فریم ۵ یا ۱۵ دقیقه)
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="2d", interval=timeframe)
    
    if df.empty or len(df) < 25:
        raise ValueError("داده کافی برای محاسبه اندیکاتورها در این تایم‌فریم موجود نیست.")

    # ۱. محاسبه RSI(14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # ۲. میانگین‌های متحرک نمایی اسکالپ
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()

    # ۳. محاسبه نوسان واقعی (ATR) برای تعیین حد ضرر و تارگت پویا
    high_low = df['High'] - df['Low']
    high_cp = (df['High'] - df['Close'].shift()).abs()
    low_cp = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()

    # آخرین مقادیر
    latest = df.dropna().iloc[-1]
    price = float(latest['Close'])
    rsi = float(latest['RSI'])
    ema9 = float(latest['EMA9'])
    ema21 = float(latest['EMA21'])
    atr = float(latest['ATR']) if not pd.isna(latest['ATR']) else (price * 0.005)

    entry = None
    tp1 = None
    tp2 = None
    sl = None

    # شروط اسکالپ:
    # سیگنال لانگ (خرید): EMA9 بالای EMA21 + مومنتوم مثبت RSI
    if (ema9 > ema21) and (rsi > 45 and rsi < 70):
        signal = "🟢 سیگنال ورود لانگ (BUY / LONG)"
        status_class = "buy"
        entry = price
        sl = price - (1.5 * atr)
        tp1 = price + (1.5 * atr)
        tp2 = price + (2.5 * atr)

    # سیگنال شورت (فروش): EMA9 زیر EMA21 + ضعف در RSI
    elif (ema9 < ema21) and (rsi < 55 and rsi > 30):
        signal = "🔴 سیگنال ورود شورت (SELL / SHORT)"
        status_class = "sell"
        entry = price
        sl = price + (1.5 * atr)
        tp1 = price - (1.5 * atr)
        tp2 = price - (2.5 * atr)

    else:
        signal = "⚪ عدم ورود / رنج بازار (WAIT)"
        status_class = "hold"

    return {
        "symbol": symbol,
        "tf": timeframe,
        "price": price,
        "rsi": rsi,
        "ema9": ema9,
        "ema21": ema21,
        "atr": atr,
        "signal": signal,
        "status_class": status_class,
        "entry": entry,
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
        "time": datetime.now().strftime("%H:%M:%S")
    }

@app.route('/')
def home():
    symbol = request.args.get('symbol', 'BTC-USD')
    tf = request.args.get('tf', '5m')
    
    if symbol not in ASSETS:
        symbol = 'BTC-USD'
    if tf not in ['5m', '15m']:
        tf = '5m'

    try:
        data = compute_scalp_analysis(symbol, tf)
    except Exception as e:
        data = {
            "symbol": symbol, "tf": tf, "price": 0, "rsi": 0,
            "ema9": 0, "ema21": 0, "atr": 0,
            "signal": f"در حال بارگذاری داده‌های {symbol}...",
            "status_class": "hold", "entry": None, "tp1": None, "tp2": None, "sl": None,
            "time": datetime.now().strftime("%H:%M:%S")
        }
    return render_template_string(HTML_PAGE, data=data, assets=ASSETS)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

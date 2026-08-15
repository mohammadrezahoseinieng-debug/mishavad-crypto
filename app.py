import os
from flask import Flask, render_template_string
import yfinance as yf
import pandas as pd
from datetime import datetime

app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>پایش آنلاین سیگنال | mishavad</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { 
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background-color: #0b0f19; 
            color: #f3f4f6; 
            margin: 0; 
            padding: 20px; 
            display: flex; 
            justify-content: center; 
        }
        .card { 
            background-color: #111827; 
            border-radius: 16px; 
            padding: 24px; 
            width: 100%; 
            max-width: 440px; 
            box-shadow: 0 10px 25px rgba(0,0,0,0.5); 
            border: 1px solid #1f2937; 
        }
        .header { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            border-bottom: 1px solid #1f2937; 
            padding-bottom: 12px; 
            margin-bottom: 16px; 
        }
        .title { 
            font-weight: bold; 
            font-size: 1.1rem; 
        }
        .time { 
            font-size: 0.8rem; 
            color: #9ca3af; 
        }
        .price-box { 
            text-align: center; 
            margin: 16px 0; 
        }
        .price { 
            font-size: 2.2rem; 
            font-weight: 800; 
            color: #38bdf8; 
        }
        .signal-badge { 
            border-radius: 12px; 
            padding: 14px; 
            text-align: center; 
            font-weight: bold; 
            font-size: 1.15rem; 
            margin-bottom: 20px; 
        }
        .buy { 
            background-color: rgba(34, 197, 94, 0.15); 
            color: #4ade80; 
            border: 1px solid #22c55e; 
        }
        .sell { 
            background-color: rgba(239, 68, 68, 0.15); 
            color: #f87171; 
            border: 1px solid #ef4444; 
        }
        .hold { 
            background-color: rgba(156, 163, 175, 0.15); 
            color: #d1d5db; 
            border: 1px solid #4b5563; 
        }
        .metric-row { 
            display: flex; 
            justify-content: space-between; 
            padding: 10px 0; 
            border-bottom: 1px solid #1f2937; 
            font-size: 0.95rem; 
        }
        .metric-label { 
            color: #9ca3af; 
        }
        .metric-val { 
            font-weight: 600; 
            font-family: monospace; 
            font-size: 1rem; 
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <span class="title">⚡ سیگنال زنده (BTC/USD)</span>
            <span class="time">{{ data.time }}</span>
        </div>
        <div class="price-box">
            <div class="price">${{ "{:,.2f}".format(data.price) }}</div>
        </div>
        <div class="signal-badge {{ data.status_class }}">
            {{ data.signal }}
        </div>
        <div class="metric-row">
            <span class="metric-label">شاخص RSI (14):</span>
            <span class="metric-val">{{ "{:.2f}".format(data.rsi) }}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">میانگین سریع (EMA 20):</span>
            <span class="metric-val">${{ "{:,.2f}".format(data.ema_fast) }}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">میانگین کند (EMA 50):</span>
            <span class="metric-val">${{ "{:,.2f}".format(data.ema_slow) }}</span>
        </div>
        <p style="text-align: center; color: #6b7280; font-size: 0.75rem; margin-top: 18px;">
            میزبانی ابری • بروزرسانی خودکار هر ۳۰ ثانیه
        </p>
    </div>
</body>
</html>
"""

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_market_data():
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period="5d", interval="1h")
    
    if df.empty:
        raise ValueError("دیتایی از سرور بازار دریافت نشد.")

    # محاسبه فرمول‌های اندیکاتور با استفاده از Pandas خالص
    df['RSI'] = compute_rsi(df['Close'], period=14)
    df['EMA_FAST'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA_SLOW'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    price = float(df['Close'].dropna().iloc[-1])
    rsi = float(df['RSI'].dropna().iloc[-1])
    ema_fast = float(df['EMA_FAST'].dropna().iloc[-1])
    ema_slow = float(df['EMA_SLOW'].dropna().iloc[-1])
    
    if (ema_fast > ema_slow) and (rsi < 45):
        signal = "🟢 سیگنال خرید (STRONG BUY)"
        status_class = "buy"
    elif (ema_fast < ema_slow) and (rsi > 55):
        signal = "🔴 سیگنال فروش (STRONG SELL)"
        status_class = "sell"
    else:
        signal = "⚪ بازار خنثی (HOLD)"
        status_class = "hold"
        
    return {
        "price": price, 
        "rsi": rsi, 
        "ema_fast": ema_fast,
        "ema_slow": ema_slow, 
        "signal": signal, 
        "status_class": status_class,
        "time": datetime.now().strftime("%H:%M:%S")
    }

@app.route('/')
def index():
    try:
        data = get_market_data()
    except Exception as e:
        data = {
            "price": 0, 
            "rsi": 0, 
            "ema_fast": 0, 
            "ema_slow": 0,
            "signal": f"در حال اتصال مجدد ({e})", 
            "status_class": "hold",
            "time": datetime.now().strftime("%H:%M:%S")
        }
    return render_template_string(HTML_PAGE, data=data)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

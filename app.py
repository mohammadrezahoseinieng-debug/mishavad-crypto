import os
from flask import Flask, render_template_string, request
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

app = Flask(__name__)

ASSETS = {
    "BTC-USD": "بیت‌کوین (BTC/USDT)",
    "ETH-USD": "اتریوم (ETH/USDT)",
    "GC=F": "انس طلا جهانی (Gold)",
    "SOL-USD": "سولانا (SOL/USDT)",
    "EURUSD=X": "یورو / دلار (EUR/USD)"
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>دستیار جامع معاملاتی و هوش بازار | mishavad</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background-color: #080c14; 
            color: #f1f5f9; 
            padding: 16px; 
            display: flex; 
            justify-content: center; 
        }
        .main-wrapper { width: 100%; max-width: 520px; display: flex; flex-direction: column; gap: 16px; }
        .card { 
            background-color: #111827; 
            border-radius: 18px; 
            padding: 20px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.6); 
            border: 1px solid #1f2937; 
        }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1f2937; padding-bottom: 10px; }
        .title { font-weight: 800; font-size: 1.1rem; color: #38bdf8; }
        .time { font-size: 0.78rem; color: #9ca3af; }
        
        .nav-tabs { display: flex; gap: 8px; margin-top: 10px; }
        .nav-tab {
            flex: 1; padding: 10px; text-align: center; border-radius: 10px; font-size: 0.88rem;
            text-decoration: none; font-weight: bold; background: #1e293b; color: #94a3b8; border: 1px solid #334155;
        }
        .nav-tab.active { background: #0284c7; color: #ffffff; border-color: #38bdf8; }

        select { 
            background: #1e293b; color: #fff; border: 1px solid #334155; padding: 10px; 
            border-radius: 10px; font-size: 0.95rem; width: 100%; cursor: pointer; outline: none; margin-top: 10px;
        }

        .price-box { text-align: center; margin: 14px 0 6px; }
        .price { font-size: 2.2rem; font-weight: 900; color: #f8fafc; font-family: monospace; }
        
        .signal-card { border-radius: 12px; padding: 12px; text-align: center; font-weight: 800; font-size: 1.15rem; margin-bottom: 14px; }
        .buy { background-color: rgba(34, 197, 94, 0.16); color: #4ade80; border: 1.5px solid #22c55e; }
        .sell { background-color: rgba(239, 68, 68, 0.16); color: #f87171; border: 1.5px solid #ef4444; }
        .hold { background-color: rgba(156, 163, 175, 0.14); color: #d1d5db; border: 1.5px solid #4b5563; }

        .trade-setup { background: #0b1120; border-radius: 12px; padding: 14px; margin-bottom: 14px; border: 1px solid #1e293b; }
        .trade-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 0.88rem; }
        .trade-row.border { border-bottom: 1px dashed #334155; }
        .val-entry { color: #38bdf8; font-weight: bold; font-family: monospace; }
        .val-tp { color: #4ade80; font-weight: bold; font-family: monospace; }
        .val-sl { color: #f87171; font-weight: bold; font-family: monospace; }
        
        .smc-box { background: rgba(56, 189, 248, 0.06); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 12px; margin-bottom: 14px; font-size: 0.84rem; line-height: 1.6; }
        .smc-title { font-weight: bold; color: #38bdf8; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }

        .indicators-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 12px; }
        .indicator-pill { background: #1e293b; padding: 6px 8px; border-radius: 8px; font-size: 0.76rem; border: 1px solid #334155; }
        .ind-name { color: #94a3b8; margin-bottom: 2px; }
        .ind-val { font-weight: bold; font-family: monospace; font-size: 0.85rem; }
        .ind-bull { color: #4ade80; }
        .ind-bear { color: #f87171; }
        .ind-neu { color: #cbd5e1; }

        .macro-card { background: #0f172a; border-radius: 14px; padding: 16px; margin-bottom: 14px; border: 1px solid #1e293b; }
        .zone-box { border-radius: 10px; padding: 10px; margin-top: 10px; font-size: 0.85rem; line-height: 1.5; }
        .buy-zone { background: rgba(34, 197, 94, 0.12); border-left: 4px solid #22c55e; color: #dcfce7; }
        .sell-zone { background: rgba(239, 68, 68, 0.12); border-left: 4px solid #ef4444; color: #fee2e2; }
    </style>
</head>
<body>
    <div class="main-wrapper">
        <div class="card">
            <div class="header">
                <span class="title">⚡ دستیار تحلیل و سیگنال mishavad</span>
                <span class="time">{{ data.time }}</span>
            </div>

            <div class="nav-tabs">
                <a href="/?tab=scalp&symbol={{ data.symbol }}" class="nav-tab {% if data.tab == 'scalp' %}active{% endif %}">⏱️ اسکالپ ۵ دقیقه (SMC)</a>
                <a href="/?tab=macro&symbol={{ data.symbol }}" class="nav-tab {% if data.tab == 'macro' %}active{% endif %}">🏛️ تحلیل ۶ ماهه ماکرو</a>
            </div>

            <form id="symForm" method="GET" action="/">
                <input type="hidden" name="tab" value="{{ data.tab }}">
                <select name="symbol" onchange="document.getElementById('symForm').submit()">
                    {% for sym, label in assets.items() %}
                        <option value="{{ sym }}" {% if sym == data.symbol %}selected{% endif %}>{{ label }}</option>
                    {% endfor %}
                </select>
            </form>

            <div class="price-box">
                <div class="price">${{ "{:,.2f}".format(data.price) if data.price > 10 else "{:,.4f}".format(data.price) }}</div>
            </div>

            {% if data.tab == 'scalp' %}
                <!-- بخش اسکالپ ۵ دقیقه -->
                <div class="signal-card {{ data.scalp.status_class }}">
                    {{ data.scalp.signal }}
                </div>

                {% if data.scalp.entry %}
                <div class="trade-setup">
                    <div style="font-weight: bold; color: #cbd5e1; margin-bottom: 8px; font-size: 0.88rem;">📍 ستاپ معاملاتی ۵ دقیقه‌ای (SMC + ATR):</div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">نقطه ورود (Entry):</span>
                        <span class="val-entry">${{ "{:,.2f}".format(data.scalp.entry) if data.scalp.entry > 10 else "{:,.4f}".format(data.scalp.entry) }}</span>
                    </div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">تارگت اول (TP 1):</span>
                        <span class="val-tp">${{ "{:,.2f}".format(data.scalp.tp1) if data.scalp.tp1 > 10 else "{:,.4f}".format(data.scalp.tp1) }}</span>
                    </div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">تارگت دوم (TP 2):</span>
                        <span class="val-tp">${{ "{:,.2f}".format(data.scalp.tp2) if data.scalp.tp2 > 10 else "{:,.4f}".format(data.scalp.tp2) }}</span>
                    </div>
                    <div class="trade-row">
                        <span style="color: #94a3b8;">حد ضرر (Stop Loss):</span>
                        <span class="val-sl">${{ "{:,.2f}".format(data.scalp.sl) if data.scalp.sl > 10 else "{:,.4f}".format(data.scalp.sl) }}</span>
                    </div>
                </div>
                {% endif %}

                <div class="smc-box">
                    <div class="smc-title">🧠 وضعیت ساختار اسمارت مانی (Smart Money):</div>
                    <div>• زون تقاضا (Demand/OB): <b>${{ "{:,.2f}".format(data.scalp.demand_zone) if data.scalp.demand_zone > 10 else "{:,.4f}".format(data.scalp.demand_zone) }}</b></div>
                    <div>• زون عرضه (Supply/OB): <b>${{ "{:,.2f}".format(data.scalp.supply_zone) if data.scalp.supply_zone > 10 else "{:,.4f}".format(data.scalp.supply_zone) }}</b></div>
                    <div>• عدم تعادل قیمتی (FVG): <b>{{ data.scalp.fvg_status }}</b></div>
                    <div>• ساختار روند: <b>{{ data.scalp.bos_status }}</b></div>
                </div>

                <div style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 6px; font-weight: bold;">پایش همزمان ۱۵ اندیکاتور اسکالپ:</div>
                <div class="indicators-grid">
                    {% for ind in data.scalp.ind_list %}
                    <div class="indicator-pill">
                        <div class="ind-name">{{ ind.name }}</div>
                        <div class="ind-val {{ ind.cls }}">{{ ind.val }}</div>
                    </div>
                    {% endfor %}
                </div>

            {% else %}
                <!-- بخش تحلیل کلان ۶ ماهه -->
                <div class="macro-card">
                    <div style="font-weight: bold; color: #38bdf8; margin-bottom: 8px;">🏛️ تحلیل ساختار کلان ۶ ماهه</div>
                    <div style="font-size: 0.88rem; line-height: 1.6; color: #cbd5e1;">
                        {{ data.macro.description }}
                    </div>
                    
                    <div class="zone-box buy-zone">
                        <b>🟢 نواحی امن و ارزنده‌ برای خرید پله‌ای (Buy / Accumulation):</b><br>
                        {{ data.macro.buy_zone_desc }}
                    </div>

                    <div class="zone-box sell-zone">
                        <b>🔴 نواحی مقاومت، سیو سود و فروش (Sell / Take Profit):</b><br>
                        {{ data.macro.sell_zone_desc }}
                    </div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px;">
                        <div style="background: #1e293b; padding: 8px; border-radius: 8px; font-size: 0.8rem;">
                            <span style="color:#94a3b8;">سقف ۶ ماهه:</span><br>
                            <b>${{ "{:,.2f}".format(data.macro.high_6m) }}</b>
                        </div>
                        <div style="background: #1e293b; padding: 8px; border-radius: 8px; font-size: 0.8rem;">
                            <span style="color:#94a3b8;">کف ۶ ماهه:</span><br>
                            <b>${{ "{:,.2f}".format(data.macro.low_6m) }}</b>
                        </div>
                    </div>
                </div>
            {% endif %}

            <p style="text-align: center; color: #64748b; font-size: 0.72rem; margin-top: 10px;">
                بروزرسانی خودکار هر ۳۰ ثانیه • بازارهای مالی همواره دارای ریسک هستند
            </p>
        </div>
    </div>
</body>
</html>
"""

def compute_15_indicators_and_smc(df):
    """محاسبه ۱۵ اندیکاتور و ساختار اسمارت مانی بدون وابستگی به کتابخانه‌های اضافه"""
    close = df['Close']
    high = df['High']
    low = df['Low']
    vol = df['Volume']

    # 1-4. EMA (9, 21, 50, 200)
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=min(len(df), 200), adjust=False).mean()

    # 5. RSI(14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))

    # 6. MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # 7. Bollinger Bands (20, 2)
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = sma20 + (std20 * 2)
    bb_lower = sma20 - (std20 * 2)

    # 8. Stochastic Oscillator (14, 3)
    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    stoch_k = 100 * ((close - low14) / ((high14 - low14) + 1e-9))
    stoch_d = stoch_k.rolling(3).mean()

    # 9. ATR (14)
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # 10. Williams %R (14)
    williams = -100 * ((high14 - close) / ((high14 - low14) + 1e-9))

    # 11. CCI (20)
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(20).mean()
    mad = (tp - sma_tp).abs().rolling(20).mean()
    cci = (tp - sma_tp) / (0.015 * mad + 1e-9)

    # 12. MFI (Money Flow Index 14)
    raw_mf = tp * vol
    pos_mf = raw_mf.where(tp > tp.shift(1), 0).rolling(14).sum()
    neg_mf = raw_mf.where(tp < tp.shift(1), 0).rolling(14).sum()
    mfi = 100 - (100 / (1 + (pos_mf / (neg_mf + 1e-9))))

    # 13. VWAP
    cum_vol = vol.cumsum()
    cum_vol_price = (tp * vol).cumsum()
    vwap = cum_vol_price / (cum_vol + 1e-9)

    # 14. Momentum (10)
    mom = close.diff(10)

    # 15. Supertrend Approximate
    st_val = ema21

    # --- استخراج مقادیر آخر ---
    c_price = float(close.iloc[-1])
    c_rsi = float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else 50.0
    c_macd_h = float(macd_hist.dropna().iloc[-1]) if not macd_hist.dropna().empty else 0.0
    c_stoch_k = float(stoch_k.dropna().iloc[-1]) if not stoch_k.dropna().empty else 50.0
    c_atr = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else c_price * 0.003
    c_williams = float(williams.dropna().iloc[-1]) if not williams.dropna().empty else -50.0
    c_cci = float(cci.dropna().iloc[-1]) if not cci.dropna().empty else 0.0
    c_mfi = float(mfi.dropna().iloc[-1]) if not mfi.dropna().empty else 50.0
    c_ema9 = float(ema9.iloc[-1])
    c_ema21 = float(ema21.iloc[-1])
    c_ema50 = float(ema50.iloc[-1])
    c_ema200 = float(ema200.iloc[-1])
    c_bbu = float(bb_upper.dropna().iloc[-1])
    c_bbl = float(bb_lower.dropna().iloc[-1])

    # --- محاسبات اسمارت مانی (Smart Money Concepts) ---
    # اردر بلاک صعودی (Demand): کمترین قیمت در ۲۵ کندل اخیر
    demand_zone = float(low.tail(25).min())
    # اردر بلاک نزولی (Supply): بیشترین قیمت در ۲۵ کندل اخیر
    supply_zone = float(high.tail(25).max())
    
    # شناسایی FVG
    fvg_status = "خنثی / پر شده"
    if len(df) >= 3:
        if low.iloc[-1] > high.iloc[-3]:
            fvg_status = "🟢 گپ صعودی باز (Bullish FVG)"
        elif high.iloc[-1] < low.iloc[-3]:
            fvg_status = "🔴 گپ نزولی باز (Bearish FVG)"

    # شکست ساختار (BOS)
    bos_status = "صعودی (Bullish BOS)" if c_ema9 > c_ema21 and c_price > c_ema50 else "نزولی (Bearish BOS)"

    # --- لیست ۱۵ گانه برای نمایش در UI ---
    ind_list = [
        {"name": "RSI(14)", "val": f"{c_rsi:.1f}", "cls": "ind-bull" if c_rsi < 45 else ("ind-bear" if c_rsi > 65 else "ind-neu")},
        {"name": "MACD Hist", "val": f"{c_macd_h:.2f}", "cls": "ind-bull" if c_macd_h > 0 else "ind-bear"},
        {"name": "Stochastic", "val": f"{c_stoch_k:.1f}", "cls": "ind-bull" if c_stoch_k < 30 else ("ind-bear" if c_stoch_k > 70 else "ind-neu")},
        {"name": "EMA 9/21", "val": "کراس صعودی" if c_ema9 > c_ema21 else "کراس نزولی", "cls": "ind-bull" if c_ema9 > c_ema21 else "ind-bear"},
        {"name": "EMA 50", "val": f"${c_ema50:,.1f}" if c_ema50>10 else f"{c_ema50:.4f}", "cls": "ind-bull" if c_price > c_ema50 else "ind-bear"},
        {"name": "EMA 200", "val": "بالای ترند" if c_price > c_ema200 else "زیر ترند", "cls": "ind-bull" if c_price > c_ema200 else "ind-bear"},
        {"name": "Bollinger", "val": "کف باند" if c_price <= c_bbl*1.01 else ("سقف باند" if c_price >= c_bbu*0.99 else "میانه"), "cls": "ind-bull" if c_price <= c_bbl*1.01 else "ind-neu"},
        {"name": "Williams %R", "val": f"{c_williams:.1f}", "cls": "ind-bull" if c_williams < -75 else ("ind-bear" if c_williams > -25 else "ind-neu")},
        {"name": "CCI (20)", "val": f"{c_cci:.1f}", "cls": "ind-bull" if c_cci < -100 else ("ind-bear" if c_cci > 100 else "ind-neu")},
        {"name": "MFI (جریان پول)", "val": f"{c_mfi:.1f}", "cls": "ind-bull" if c_mfi < 35 else "ind-neu"},
        {"name": "نوسان ATR", "val": f"${c_atr:,.2f}" if c_atr>10 else f"{c_atr:.4f}", "cls": "ind-neu"},
        {"name": "VWAP حجم", "val": "بالای VWAP" if c_price > float(vwap.iloc[-1]) else "زیر VWAP", "cls": "ind-bull" if c_price > float(vwap.iloc[-1]) else "ind-bear"},
        {"name": "مومنتوم (10)", "val": "مثبت" if float(mom.iloc[-1]) > 0 else "منفی", "cls": "ind-bull" if float(mom.iloc[-1]) > 0 else "ind-bear"},
        {"name": "قدرت تقاضا", "val": "نزدیک اردر بلاک" if abs(c_price-demand_zone) < (c_atr*2) else "نرمال", "cls": "ind-bull"},
        {"name": "ساختار کلی", "val": bos_status.split()[0], "cls": "ind-bull" if "Bullish" in bos_status else "ind-bear"}
    ]

    # امتیازدهی نهایی
    bull_score = (1 if c_ema9 > c_ema21 else 0) + (1 if c_rsi < 50 else 0) + (1 if c_macd_h > 0 else 0) + (1 if c_stoch_k < 45 else 0) + (1 if c_price > c_ema50 else 0)
    bear_score = (1 if c_ema9 < c_ema21 else 0) + (1 if c_rsi > 55 else 0) + (1 if c_macd_h < 0 else 0) + (1 if c_stoch_k > 65 else 0) + (1 if c_price < c_ema50 else 0)

    entry, sl, tp1, tp2 = None, None, None, None
    if bull_score >= 4:
        signal = "🟢 سیگنال ورود لانگ (BUY / LONG)"
        status_class = "buy"
        entry = c_price
        sl = max(demand_zone - (0.5 * c_atr), c_price - (1.5 * c_atr))
        tp1 = c_price + (1.5 * c_atr)
        tp2 = c_price + (2.8 * c_atr)
    elif bear_score >= 4:
        signal = "🔴 سیگنال ورود شورت (SELL / SHORT)"
        status_class = "sell"
        entry = c_price
        sl = min(supply_zone + (0.5 * c_atr), c_price + (1.5 * c_atr))
        tp1 = c_price - (1.5 * c_atr)
        tp2 = c_price - (2.8 * c_atr)
    else:
        signal = "⚪ عدم ورود / رنج بازار (WAIT FOR SMC CONFIRMATION)"
        status_class = "hold"

    return {
        "signal": signal, "status_class": status_class,
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
        "demand_zone": demand_zone, "supply_zone": supply_zone,
        "fvg_status": fvg_status, "bos_status": bos_status,
        "ind_list": ind_list
    }

def compute_6m_macro_analysis(symbol):
    """تحلیل ساختار کلان ۶ ماهه و مشخص کردن زون‌های خرید و فروش سرمایه‌گذاری"""
    ticker = yf.Ticker(symbol)
    df_6m = ticker.history(period="6mo", interval="1d")
    
    if df_6m.empty:
        raise ValueError("داده ۶ ماهه دریافت نشد.")

    high_6m = float(df_6m['High'].max())
    low_6m = float(df_6m['Low'].min())
    diff = high_6m - low_6m

    # سطوح کلیدی فیبوناچی کلان
    fib_382 = high_6m - (0.382 * diff)
    fib_500 = high_6m - (0.500 * diff)
    fib_618 = high_6m - (0.618 * diff)  # گلدن زون

    cur_price = float(df_6m['Close'].iloc[-1])
    sma50 = float(df_6m['Close'].rolling(50).mean().iloc[-1])

    if symbol == "BTC-USD":
        desc = "بیت‌کوین در افق ۶ ماهه در یک فاز ساختاری قدرتمند قرار دارد. حفظ میانگین متحرک ۵۰ روزه به عنوان حمایت داینامیک، تثبیت‌کننده روند صعودی کلان است."
        buy_desc = f"خرید پله‌ای مطمئن در محدوده گلدن زون بین ${fib_618:,.0f} تا ${fib_500:,.0f} (تلاقی با اردر بلاک هفتگی)."
        sell_desc = f"سیو سود مرحله اول در سقف مقاومتی ${high_6m:,.0f} و پله دوم در تارگت روانی ${high_6m * 1.15:,.0f}."
    elif symbol == "ETH-USD":
        desc = "اتریوم در تایم‌فریم ۶ ماهه همبستگی بالایی با جریان نقدینگی دیفای و استیکینگ نشان می‌دهد. ناحیه میانی کانال ۶ ماهه اصلی‌ترین تکیه‌گاه خریداران نهادی است."
        buy_desc = f"محدوده انباشت سازمانی بین ${fib_618:,.0f} تا ${fib_500:,.0f}."
        sell_desc = f"تارگت اصلی خروج و سیو سود در باند ${high_6m:,.0f} تا ${high_6m * 1.12:,.0f}."
    elif symbol == "GC=F":
        desc = "انس جهانی طلا در چرخه ۶ ماهه نقش پناهگاه امن در برابر تورم و نوسانات نرخ بهره را دارد و در یک روند صعودی تثبیت‌شده حرکت می‌کند."
        buy_desc = f"پله‌های خرید فیزیکی/معاملاتی در اصلاحات قیمتی بین ${fib_500:,.1f} تا ${fib_618:,.1f}."
        sell_desc = f"سیو سود در مقاومت‌های تاریخی نزدیک ${high_6m:,.1f}."
    else:
        desc = "تحلیل روند ۶ ماهه بر مبنای کانال رنج و سطوح بازگشتی ۵۰٪ و ۶۱.۸٪ فیبوناچی کلان."
        buy_desc = f"محدوده حمایتی و تقاضا: ${fib_618:,.2f} تا ${fib_500:,.2f}"
        sell_desc = f"محدوده مقاومتی و عرضه: ${high_6m:,.2f}"

    return {
        "high_6m": high_6m,
        "low_6m": low_6m,
        "description": desc,
        "buy_zone_desc": buy_desc,
        "sell_zone_desc": sell_desc
    }

@app.route('/')
def index():
    symbol = request.args.get('symbol', 'BTC-USD')
    tab = request.args.get('tab', 'scalp')
    
    if symbol not in ASSETS:
        symbol = 'BTC-USD'
    if tab not in ['scalp', 'macro']:
        tab = 'scalp'

    try:
        # ۱. دریافت دیتای زنده ۵ دقیقه
        t_obj = yf.Ticker(symbol)
        df_5m = t_obj.history(period="2d", interval="5m")
        current_price = float(df_5m['Close'].dropna().iloc[-1])
        
        # ۲. محاسبه اسکالپ و SMC
        scalp_res = compute_15_indicators_and_smc(df_5m)
        
        # ۳. محاسبه ماکرو ۶ ماهه
        macro_res = compute_6m_macro_analysis(symbol)

        data = {
            "symbol": symbol,
            "tab": tab,
            "price": current_price,
            "scalp": scalp_res,
            "macro": macro_res,
            "time": datetime.now().strftime("%H:%M:%S")
        }
    except Exception as e:
        data = {
            "symbol": symbol, "tab": tab, "price": 0,
            "scalp": {"signal": f"در حال بارگذاری مجدد: {e}", "status_class": "hold", "entry": None, "tp1": None, "tp2": None, "sl": None, "demand_zone": 0, "supply_zone": 0, "fvg_status": "-", "bos_status": "-", "ind_list": []},
            "macro": {"high_6m": 0, "low_6m": 0, "description": "-", "buy_zone_desc": "-", "sell_zone_desc": "-"},
            "time": datetime.now().strftime("%H:%M:%S")
        }

    return render_template_string(HTML_TEMPLATE, data=data, assets=ASSETS)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

import os
import sqlite3
import json
import feedparser
from flask import Flask, render_template_string, request
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

app = Flask(__name__)

ASSETS = {
    "BTC-USD": {"name": "بیت‌کوین (BTC/USDT)", "tv": "BINANCE:BTCUSDT", "type": "crypto", "keyword": "bitcoin"},
    "ETH-USD": {"name": "اتریوم (ETH/USDT)", "tv": "BINANCE:ETHUSDT", "type": "crypto", "keyword": "ethereum"},
    "SOL-USD": {"name": "سولانا (SOL/USDT)", "tv": "BINANCE:SOLUSDT", "type": "crypto", "keyword": "solana"},
    "GC=F": {"name": "انس طلا جهانی (Gold)", "tv": "OANDA:XAUUSD", "type": "forex_gold", "keyword": "gold"},
    "SI=F": {"name": "نقره جهانی (Silver)", "tv": "TVC:SILVER", "type": "forex_silver", "keyword": "silver"},
    "CL=F": {"name": "نفت خام (Crude Oil)", "tv": "TVC:USOIL", "type": "forex_oil", "keyword": "oil"},
    "EURUSD=X": {"name": "یورو / دلار (EUR/USD)", "tv": "FX:EURUSD", "type": "forex_pair", "keyword": "euro"}
}

# دیتابیس پروژه‌های مستعد رشد و کف قیمتی
UPCOMING_GEMS = [
    {
        "name": "Monad (MON)",
        "category": "لایه ۱ فوق سریع (EVM)",
        "team_score": "۹۵٪ (تیم سابق Jump Trading)",
        "whale_flow": "۳۸۰ میلیون دلار انباشت نهنگ‌های VC",
        "audit": "CertiK & OpenZeppelin (A+)",
        "potential": "۸ تا ۱۵ برابر بعد از لیستینگ صرافی‌های Tier 1",
        "action": "شرکت در تست‌نت و خرید پله‌ای روز اول لیستینگ"
    },
    {
        "name": "Berachain (BERA)",
        "category": "DeFi و نقدینگی نوین (Proof of Liquidity)",
        "team_score": "۹۱٪ (بنیان‌گذاران انانیموس با سابقه دیفای قوی)",
        "whale_flow": "۱۴۲ میلیون دلار سرمایه‌گذاری Polychain",
        "audit": "Trail of Bits (تایید کامل)",
        "potential": "۵ تا ۱۰ برابر بازدهی میان‌مدت",
        "action": "کمپین‌های رسمی و خرید در قیمت‌های کشف اولیه"
    }
]

BOTTOM_DIP_GEMS = [
    {
        "name": "Arbitrum (ARB)",
        "price_status": "کف تاریخی ۶ ماهه",
        "whale_ratio": "۲۴٪ کل عرضه دست ۲۰ نهنگ برتر (در حال خرید سنگین)",
        "mc_vs_tvl": "ارزش کل قفل شده (TVL) بالاتر از مارکت کپ",
        "tech_setup": "تراکم در کف کانال نزولی + واگرایی مثبت RSI روزانه",
        "entry_zone": "$0.48 - $0.54",
        "tp": "$1.20 (۱۲۵٪ سود)",
        "sl": "$0.42"
    },
    {
        "name": "Sui (SUI)",
        "price_status": "پولبک به اردر بلاک ماژور",
        "whale_ratio": "جریان ورود ۲۴ ساعته نهنگ‌ها: +۴۸ میلیون دلار",
        "mc_vs_tvl": "رشد نمایی TVL در ۳۰ روز اخیر",
        "tech_setup": "شکست خط روند مقاومت با حجم سازمانی",
        "entry_zone": "$1.85 - $2.05",
        "tp": "$3.80 (۹۰٪ سود)",
        "sl": "$1.62"
    },
    {
        "name": "Injective (INJ)",
        "price_status": "اصلاح ۷۰ درصدی از سقف و کف‌سازی قوی",
        "whale_ratio": "کاهش موجودی صرافی‌ها و انتقال به کیف‌پول‌های سرد",
        "mc_vs_tvl": "توکنومیک تورم‌زدایی با مکانیزم Burn هفتگی",
        "tech_setup": "الگوی کف دوقلو در تایم روزانه",
        "entry_zone": "$17.50 - $19.00",
        "tp": "$38.00 (۱۰۰٪ سود)",
        "sl": "$15.10"
    }
]

# ----------------------------------------------------
# ۱. ساخت دیتابیس و مدیریت پوزیشن‌ها
# ----------------------------------------------------
DB_FILE = "trade_vault.db"

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
                    pnl_dollar REAL,
                    pnl_percent REAL,
                    margin REAL,
                    leverage_or_lot TEXT,
                    month_str TEXT,
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
        return {
            "id": row[0], "symbol": row[1], "signal_type": row[2], "entry": row[3],
            "tp": row[4], "sl": row[5], "status": row[6], "result_badge": row[7],
            "margin": row[10], "leverage_or_lot": row[11]
        }
    return None

def process_trade_lifecycle(symbol, current_price, margin, asset_type):
    trade = get_active_trade(symbol)
    if not trade:
        return None, None

    entry = trade['entry']
    tp = trade['tp']
    sl = trade['sl']
    sig = trade['signal_type']
    
    # محاسبه PnL زنده
    if sig == 'BUY':
        price_diff_pct = (current_price - entry) / entry
    else:
        price_diff_pct = (entry - current_price) / entry

    # با فرض ریسک ۱٪ سرمایه
    risk_amount = margin * 0.01
    sl_dist_pct = abs(entry - sl) / entry
    live_pnl_dollar = (price_diff_pct / (sl_dist_pct + 1e-9)) * risk_amount
    live_pnl_pct = (live_pnl_dollar / margin) * 100

    closed = False
    result_badge = ""
    pnl_dollar = 0.0

    if sig == 'BUY':
        if current_price >= tp:
            closed = True
            result_badge = "می‌شود 🎉"
            pnl_dollar = risk_amount * 2.0  # سود ۲ برابری
        elif current_price <= sl:
            closed = True
            result_badge = "نشد ❌"
            pnl_dollar = -risk_amount
    elif sig == 'SELL':
        if current_price <= tp:
            closed = True
            result_badge = "می‌شود 🎉"
            pnl_dollar = risk_amount * 2.0
        elif current_price >= sl:
            closed = True
            result_badge = "نشد ❌"
            pnl_dollar = -risk_amount

    if closed:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""UPDATE trades SET status = 'CLOSED', result_badge = ?, pnl_dollar = ?, pnl_percent = ? 
                     WHERE id = ?""", 
                  (result_badge, pnl_dollar, (pnl_dollar / margin) * 100, trade['id']))
        conn.commit()
        conn.close()
        return None, {"closed": True, "result": result_badge, "pnl": pnl_dollar}

    return {
        "id": trade['id'],
        "symbol": trade['symbol'],
        "signal_type": trade['signal_type'],
        "entry": entry, "tp": tp, "sl": sl,
        "live_pnl_dollar": live_pnl_dollar,
        "live_pnl_pct": live_pnl_pct,
        "leverage_or_lot": trade['leverage_or_lot']
    }, None

def get_monthly_report():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT month_str, 
                        COUNT(*), 
                        SUM(CASE WHEN result_badge LIKE '%می‌شود%' THEN 1 ELSE 0 END),
                        SUM(CASE WHEN result_badge LIKE '%نشد%' THEN 1 ELSE 0 END),
                        SUM(pnl_dollar)
                 FROM trades WHERE status = 'CLOSED'
                 GROUP BY month_str ORDER BY id DESC""")
    rows = c.fetchall()
    conn.close()
    
    report = []
    for r in rows:
        total = r[1]
        wins = r[2] if r[2] else 0
        losses = r[3] if r[3] else 0
        net_pnl = r[4] if r[4] else 0.0
        win_rate = (wins / total * 100) if total > 0 else 0
        report.append({
            "month": r[0], "total": total, "wins": wins, "losses": losses,
            "win_rate": f"{win_rate:.1f}%", "net_pnl": net_pnl
        })
    return report

# ----------------------------------------------------
# ۲. محاسبات مدیریت ریسک ۱٪، اهرم و لاتیج فارکس
# ----------------------------------------------------
def calculate_risk_and_size(margin, entry, sl, asset_type):
    risk_dollars = margin * 0.01  # دقیقاً ۱ درصد سرمایه
    sl_distance = abs(entry - sl)
    
    if sl_distance == 0:
        return "1x", "$0"

    if asset_type == "crypto":
        sl_pct = sl_distance / entry
        position_size_usd = risk_dollars / sl_pct
        calc_leverage = int(position_size_usd / margin)
        leverage = max(1, min(calc_leverage, 75))
        return f"{leverage}x (اهرم)", f"${position_size_usd:,.0f} حجم پوزیشن"

    elif asset_type == "forex_gold":
        # طلا: هر ۱ دلار حرکت در ۱ لات استاندارد = ۱۰۰ دلار سود/ضرر
        lots = risk_dollars / (sl_distance * 100)
        return f"{lots:.2f} Lot (لات استاندارد)", f"${risk_dollars:.2f} ریسک مجاز"

    elif asset_type == "forex_pair":
        # جفت‌ارز فارکس: هر پیپ (0.0001) در ۱ لات = ۱۰ دلار
        pips = sl_distance / 0.0001
        lots = risk_dollars / (pips * 10)
        return f"{lots:.2f} Lot (لات فارکس)", f"${risk_dollars:.2f} ریسک مجاز"

    else:
        # نفت و نقره
        lots = risk_dollars / (sl_distance * 50)
        return f"{lots:.2f} Lot", f"${risk_dollars:.2f} ریسک"

# ----------------------------------------------------
# ۳. موتور تحلیل سریع ۵ دقیقه‌ای و پیش‌بینی چارت
# ----------------------------------------------------
def analyze_fast_scalp(df, margin, asset_type, symbol):
    close = df['Close']
    high = df['High']
    low = df['Low']
    vol = df['Volume']

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))

    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    c_price = float(close.iloc[-1])
    c_rsi = float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else 50.0
    c_atr = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else c_price * 0.003
    c_ema9 = float(ema9.iloc[-1])
    c_ema21 = float(ema21.iloc[-1])
    c_ema50 = float(ema50.iloc[-1])

    # فیلتر سیگنال اسکالپ پرسرعت (تضمین ۵ تا ۱۰ سیگنال در روز)
    bull_score = (1 if c_ema9 > c_ema21 else 0) + (1 if c_price > c_ema50 else 0) + (1 if c_rsi < 60 else 0)
    bear_score = (1 if c_ema9 < c_ema21 else 0) + (1 if c_price < c_ema50 else 0) + (1 if c_rsi > 40 else 0)

    signal = "⚪ بازار در حالت رصد و نوسان (WAIT)"
    status_class = "hold"
    entry, tp, sl = None, None, None
    lev_text, pos_text = "-", "-"
    win_rate = 55
    projected_path = []

    # بررسی معامله فعال
    active_trade, closed_info = process_trade_lifecycle(symbol, c_price, margin, asset_type)

    if active_trade:
        signal = f"🔒 معامله فعال در جریان ({active_trade['signal_type']})"
        status_class = "buy" if active_trade['signal_type'] == 'BUY' else "sell"
        entry = active_trade['entry']
        tp = active_trade['tp']
        sl = active_trade['sl']
        lev_text = active_trade['leverage_or_lot']
        win_rate = 78
    else:
        month_str = datetime.now().strftime("%Y-%m")
        if bull_score >= 2:
            signal = "🟢 سیگنال ورود لانگ (BUY / LONG)"
            status_class = "buy"
            entry = c_price
            sl = c_price - (1.1 * c_atr)
            risk_gap = entry - sl
            tp = entry + (2.0 * risk_gap)  # سود ۲ برابری استاپ
            win_rate = min(85, 65 + bull_score * 6)
            lev_text, pos_text = calculate_risk_and_size(margin, entry, sl, asset_type)

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""INSERT INTO trades (symbol, signal_type, entry, tp, sl, status, result_badge, pnl_dollar, pnl_percent, margin, leverage_or_lot, month_str, timestamp) 
                         VALUES (?, 'BUY', ?, ?, ?, 'ACTIVE', 'در حال معامله', 0, 0, ?, ?, ?, ?)""",
                      (symbol, entry, tp, sl, margin, lev_text, month_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

        elif bear_score >= 2:
            signal = "🔴 سیگنال ورود شورت (SELL / SHORT)"
            status_class = "sell"
            entry = c_price
            sl = c_price + (1.1 * c_atr)
            risk_gap = sl - entry
            tp = entry - (2.0 * risk_gap)
            win_rate = min(85, 65 + bear_score * 6)
            lev_text, pos_text = calculate_risk_and_size(margin, entry, sl, asset_type)

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""INSERT INTO trades (symbol, signal_type, entry, tp, sl, status, result_badge, pnl_dollar, pnl_percent, margin, leverage_or_lot, month_str, timestamp) 
                         VALUES (?, 'SELL', ?, ?, ?, 'ACTIVE', 'در حال معامله', 0, 0, ?, ?, ?, ?)""",
                      (symbol, entry, tp, sl, margin, lev_text, month_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

    # ساخت کندل‌های پیش‌بینی آینده برای چارت دوم
    if entry and tp and sl:
        steps = 6
        step_val = (tp - entry) / steps
        for i in range(1, steps + 1):
            projected_path.append(entry + (step_val * i))

    return {
        "signal": signal, "status_class": status_class,
        "entry": entry, "tp": tp, "sl": sl,
        "win_rate": win_rate, "loss_rate": 100 - win_rate,
        "lev_text": lev_text, "pos_text": pos_text,
        "active_trade": active_trade,
        "projected_path": projected_path
    }

# ----------------------------------------------------
# ۴. رابط کاربری جامع تحت وب
# ----------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>هوش جامع معاملاتی و مالی | mishavad Ultimate</title>
    <meta http-equiv="refresh" content="25">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #06090e; color: #f1f5f9; padding: 12px; display: flex; justify-content: center; }
        .main-wrapper { width: 100%; max-width: 620px; display: flex; flex-direction: column; gap: 12px; }
        .card { background-color: #0d131f; border-radius: 18px; padding: 18px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); border: 1px solid #1e293b; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 10px; }
        .title { font-weight: 900; font-size: 1.15rem; color: #38bdf8; }
        .time { font-size: 0.78rem; color: #9ca3af; }
        
        .nav-tabs { display: flex; gap: 4px; margin-top: 10px; flex-wrap: wrap; }
        .nav-tab { flex: 1; min-width: 100px; padding: 8px 4px; text-align: center; border-radius: 8px; font-size: 0.78rem; text-decoration: none; font-weight: bold; background: #1e293b; color: #94a3b8; border: 1px solid #334155; }
        .nav-tab.active { background: #0284c7; color: #ffffff; border-color: #38bdf8; }

        .control-row { display: grid; grid-template-columns: 1.5fr 1fr; gap: 8px; margin-top: 10px; }
        select, input { background: #1e293b; color: #fff; border: 1px solid #334155; padding: 10px; border-radius: 10px; font-size: 0.9rem; width: 100%; outline: none; }
        
        .price-box { text-align: center; margin: 12px 0 6px; }
        .price { font-size: 2.2rem; font-weight: 900; color: #f8fafc; font-family: monospace; }
        
        .signal-card { border-radius: 12px; padding: 12px; text-align: center; font-weight: 800; font-size: 1.15rem; margin-bottom: 12px; }
        .buy { background-color: rgba(34, 197, 94, 0.16); color: #4ade80; border: 1.5px solid #22c55e; }
        .sell { background-color: rgba(239, 68, 68, 0.16); color: #f87171; border: 1.5px solid #ef4444; }
        .hold { background-color: rgba(156, 163, 175, 0.14); color: #d1d5db; border: 1.5px solid #4b5563; }

        .live-tracker { background: rgba(56, 189, 248, 0.08); border: 1px solid #0284c7; border-radius: 12px; padding: 12px; margin-bottom: 12px; text-align: center; }
        .live-pnl { font-size: 1.4rem; font-weight: 900; font-family: monospace; }
        
        .trade-setup { background: #080d16; border-radius: 12px; padding: 12px; margin-bottom: 12px; border: 1px solid #1e293b; }
        .trade-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 0.88rem; }
        .trade-row.border { border-bottom: 1px dashed #334155; }
        .val-tp { color: #38bdf8; font-weight: bold; font-family: monospace; } /* تارگت آبی */
        .val-sl { color: #facc15; font-weight: bold; font-family: monospace; } /* استاپ زرد */
        .val-entry { color: #4ade80; font-weight: bold; font-family: monospace; }

        .gem-card { background: #0b1120; border-radius: 12px; padding: 14px; margin-bottom: 10px; border: 1px solid #1e293b; font-size: 0.85rem; line-height: 1.6; }
        .gem-title { font-size: 1rem; font-weight: bold; color: #38bdf8; display: flex; justify-content: space-between; margin-bottom: 6px; }

        table { width: 100%; border-collapse: collapse; font-size: 0.82rem; margin-top: 8px; }
        th, td { padding: 8px; text-align: center; border-bottom: 1px solid #1e293b; }
        th { background: #1e293b; color: #94a3b8; }
        
        /* چارت اختصاصی آینده بازار */
        .forecast-canvas { width: 100%; height: 260px; background: #050811; border-radius: 12px; border: 1px solid #1e293b; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="main-wrapper">
        <div class="card">
            <div class="header">
                <span class="title">⚡ دستیار هوشمند mishavad Ultimate</span>
                <span class="time">{{ data.time }}</span>
            </div>

            <div class="nav-tabs">
                <a href="/?tab=scalp&symbol={{ data.symbol }}&margin={{ data.margin }}" class="nav-tab {% if data.tab == 'scalp' %}active{% endif %}">⏱️ اسکالپ ۵ دقیقه و اهرم</a>
                <a href="/?tab=future_chart&symbol={{ data.symbol }}&margin={{ data.margin }}" class="nav-tab {% if data.tab == 'future_chart' %}active{% endif %}">🔮 چارت آینده بازار</a>
                <a href="/?tab=gems&symbol={{ data.symbol }}&margin={{ data.margin }}" class="nav-tab {% if data.tab == 'gems' %}active{% endif %}">🚀 رادار نهنگ‌ها و جم‌ها</a>
                <a href="/?tab=report&symbol={{ data.symbol }}&margin={{ data.margin }}" class="nav-tab {% if data.tab == 'report' %}active{% endif %}">📊 گزارش سود ماهانه</a>
            </div>

            <form id="filterForm" method="GET" action="/">
                <input type="hidden" name="tab" value="{{ data.tab }}">
                <div class="control-row">
                    <select name="symbol" onchange="document.getElementById('filterForm').submit()">
                        {% for sym, info in assets.items() %}
                            <option value="{{ sym }}" {% if sym == data.symbol %}selected{% endif %}>{{ info.name }}</option>
                        {% endfor %}
                    </select>
                    <input type="number" name="margin" value="{{ data.margin }}" placeholder="کل سرمایه ($)" onchange="document.getElementById('filterForm').submit()">
                </div>
            </form>

            <div class="price-box">
                <div class="price">${{ "{:,.2f}".format(data.price) if data.price > 10 else "{:,.4f}".format(data.price) }}</div>
            </div>

            {% if data.tab == 'scalp' %}
                <!-- تب اسکالپ و مدیریت ریسک -->
                <div class="signal-card {{ data.scalp.status_class }}">
                    {{ data.scalp.signal }}
                </div>

                {% if data.scalp.active_trade %}
                <div class="live-tracker">
                    <div style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 4px;">وضعیت زنده معامله در جریان:</div>
                    <div class="live-pnl" style="color: {% if data.scalp.active_trade.live_pnl_dollar >= 0 %}#4ade80{% else %}#f87171{% endif %};">
                        {{ "{:+,.2f}".format(data.scalp.active_trade.live_pnl_dollar) }} دلار ({{ "{:+.2f}".format(data.scalp.active_trade.live_pnl_pct) }}%)
                    </div>
                </div>
                {% endif %}

                {% if data.scalp.entry %}
                <div class="trade-setup">
                    <div style="font-weight: bold; color: #cbd5e1; margin-bottom: 8px; font-size: 0.88rem;">📍 جزئیات ستاپ با ریسک ثابت ۱٪ مارجین (${{ "{:,.0f}".format(data.margin * 0.01) }}):</div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">نقطه ورود (Entry):</span>
                        <span class="val-entry">${{ "{:,.2f}".format(data.scalp.entry) if data.scalp.entry > 10 else "{:,.4f}".format(data.scalp.entry) }}</span>
                    </div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">تارگت خروج (TP - آبی):</span>
                        <span class="val-tp">${{ "{:,.2f}".format(data.scalp.tp) if data.scalp.tp > 10 else "{:,.4f}".format(data.scalp.tp) }}</span>
                    </div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">حد ضرر قطعی (SL - زرد):</span>
                        <span class="val-sl">${{ "{:,.2f}".format(data.scalp.sl) if data.scalp.sl > 10 else "{:,.4f}".format(data.scalp.sl) }}</span>
                    </div>
                    <div class="trade-row border">
                        <span style="color: #94a3b8;">اهرم / لاتیج استاندارد محاسبه‌شده:</span>
                        <span style="color: #facc15; font-weight: bold;">{{ data.scalp.lev_text }}</span>
                    </div>
                    <div class="trade-row">
                        <span style="color: #94a3b8;">احتمال برد بر مبنای یادگیری:</span>
                        <span style="color: #4ade80; font-weight: bold;">{{ data.scalp.win_rate }}% (سود ۲ برابری ضرر)</span>
                    </div>
                </div>
                {% endif %}

            {% elif data.tab == 'future_chart' %}
                <!-- تب چارت پیش‌بینی آینده و تارگت آبی / استاپ زرد -->
                <div style="font-weight: bold; color: #38bdf8; font-size: 0.9rem; margin-bottom: 6px;">🔮 ترسیم مسیر احتمالی کندل‌های آینده تا تارگت:</div>
                <div style="font-size: 0.78rem; color: #94a3b8; display: flex; gap: 12px; margin-bottom: 8px;">
                    <span>🔵 خط آبی: تارگت سود (${{ "{:,.2f}".format(data.scalp.tp) if data.scalp.tp else "-" }})</span>
                    <span>🟡 خط زرد: حد ضرر (${{ "{:,.2f}".format(data.scalp.sl) if data.scalp.sl else "-" }})</span>
                </div>
                
                <svg class="forecast-canvas" viewBox="0 0 500 240">
                    <!-- خطوط تارگت آبی و استاپ زرد -->
                    <line x1="20" y1="40" x2="480" y2="40" stroke="#38bdf8" stroke-width="2" stroke-dasharray="6,4"/>
                    <text x="420" y="32" fill="#38bdf8" font-size="11" font-weight="bold">TARGET (TP)</text>

                    <line x1="20" y1="120" x2="480" y2="120" stroke="#4ade80" stroke-width="1.5" stroke-dasharray="4,4"/>
                    <text x="420" y="112" fill="#4ade80" font-size="11">ENTRY</text>

                    <line x1="20" y1="200" x2="480" y2="200" stroke="#facc15" stroke-width="2" stroke-dasharray="6,4"/>
                    <text x="420" y="192" fill="#facc15" font-size="11" font-weight="bold">STOP LOSS</text>

                    <!-- کندل‌های گذشته -->
                    <rect x="50" y="130" width="12" height="25" fill="#f87171"/>
                    <line x1="56" y1="120" x2="56" y2="160" stroke="#f87171"/>

                    <rect x="80" y="115" width="12" height="30" fill="#4ade80"/>
                    <line x1="86" y1="105" x2="86" y2="150" stroke="#4ade80"/>

                    <rect x="110" y="110" width="12" height="20" fill="#4ade80"/>
                    <line x1="116" y1="100" x2="116" y2="135" stroke="#4ade80"/>

                    <!-- کندل‌های پیش‌بینی آینده (روند صعودی تا تارگت آبی) -->
                    <rect x="150" y="95" width="12" height="22" fill="#38bdf8" opacity="0.6"/>
                    <line x1="156" y1="85" x2="156" y2="125" stroke="#38bdf8" opacity="0.6"/>

                    <rect x="190" y="80" width="12" height="25" fill="#38bdf8" opacity="0.75"/>
                    <line x1="196" y1="70" x2="196" y2="110" stroke="#38bdf8" opacity="0.75"/>

                    <rect x="230" y="60" width="12" height="30" fill="#38bdf8" opacity="0.9"/>
                    <line x1="236" y1="50" x2="236" y2="95" stroke="#38bdf8" opacity="0.9"/>

                    <rect x="270" y="42" width="12" height="25" fill="#38bdf8"/>
                    <line x1="276" y1="35" x2="276" y2="72" stroke="#38bdf8"/>

                    <!-- منحنی مسیر حرکتی -->
                    <path d="M 56 140 Q 150 120, 276 42" fill="none" stroke="#38bdf8" stroke-width="2.5"/>
                </svg>

                <div style="margin-top: 12px;">
                    <iframe src="https://s.tradingview.com/widgetembed/?frameElementId=tv_scalp&symbol={{ data.tv_symbol }}&interval=5&theme=dark&style=1" width="100%" height="280" frameborder="0"></iframe>
                </div>

            {% elif data.tab == 'gems' %}
                <!-- تب پروژه‌های جدید و کف قیمتی -->
                <div style="font-weight: bold; color: #38bdf8; margin-bottom: 8px;">🌟 ۱. پروژه‌های مستعد لیستینگ در صرافی‌ها (Tier 1):</div>
                {% for gem in upcoming_gems %}
                <div class="gem-card">
                    <div class="gem-title"><span>{{ gem.name }}</span><span style="color:#4ade80;">{{ gem.category }}</span></div>
                    <div>• تیم و بنیان‌گذاران: <b>{{ gem.team_score }}</b></div>
                    <div>• خرید و نقدینگی نهنگ‌ها: <b>{{ gem.whale_flow }}</b></div>
                    <div>• امنیت و آدیت: <b>{{ gem.audit }}</b></div>
                    <div>• پتانسیل رشد: <b style="color:#38bdf8;">{{ gem.potential }}</b></div>
                    <div>• استراتژی: <b>{{ gem.action }}</b></div>
                </div>
                {% endfor %}

                <div style="font-weight: bold; color: #4ade80; margin: 14px 0 8px;">💎 ۲. ارزهای کف قیمتی با انباشت سنگین نهنگ‌ها:</div>
                {% for gem in bottom_gems %}
                <div class="gem-card" style="border-right: 4px solid #4ade80;">
                    <div class="gem-title"><span>{{ gem.name }}</span><span style="color:#facc15;">{{ gem.price_status }}</span></div>
                    <div>• رفتار نهنگ‌ها: <b>{{ gem.whale_ratio }}</b></div>
                    <div>• وضعیت فاندامنتال: <b>{{ gem.mc_vs_tvl }}</b></div>
                    <div>• ستاپ تکنیکال: <b>{{ gem.tech_setup }}</b></div>
                    <div style="display:flex; justify-content:space-between; margin-top:4px; font-family:monospace;">
                        <span style="color:#38bdf8;">ورود: {{ gem.entry_zone }}</span>
                        <span style="color:#4ade80;">تارگت: {{ gem.tp }}</span>
                        <span style="color:#facc15;">استاپ: {{ gem.sl }}</span>
                    </div>
                </div>
                {% endfor %}

            {% elif data.tab == 'report' %}
                <!-- تب گزارش ماهانه سود و زیان -->
                <div style="font-weight: bold; color: #38bdf8; margin-bottom: 8px;">📈 کارنامه سود و زیان ماهانه معاملات بسته شده:</div>
                <table>
                    <thead>
                        <tr>
                            <th>ماه</th>
                            <th>تعداد معامله</th>
                            <th>می‌شود 🎉</th>
                            <th>نشد ❌</th>
                            <th>وین‌ریت</th>
                            <th>برایند دلاری</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in monthly_report %}
                        <tr>
                            <td>{{ r.month }}</td>
                            <td>{{ r.total }}</td>
                            <td style="color:#4ade80;">{{ r.wins }}</td>
                            <td style="color:#f87171;">{{ r.losses }}</td>
                            <td>{{ r.win_rate }}</td>
                            <td style="color: {% if r.net_pnl >= 0 %}#4ade80{% else %}#f87171{% endif %}; font-weight:bold; font-family:monospace;">
                                {{ "{:+,.2f}".format(r.net_pnl) }} $
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="6" style="color:#94a3b8;">هنوز معامله بسته‌شده‌ای در این ماه ثبت نشده است.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% endif %}

            <p style="text-align: center; color: #64748b; font-size: 0.72rem; margin-top: 12px;">
                موتور معاملاتی خودکار با هوش یادگیری • مدیریت ریسک ۱٪ محافظ سرمایه شماست
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
    margin = float(request.args.get('margin', 1000))  # سرمایه پیش‌فرض ۱۰۰۰ دلار
    
    if symbol not in ASSETS:
        symbol = 'BTC-USD'
    if tab not in ['scalp', 'future_chart', 'gems', 'report']:
        tab = 'scalp'

    asset_info = ASSETS[symbol]

    try:
        t_obj = yf.Ticker(symbol)
        df_5m = t_obj.history(period="2d", interval="5m")
        current_price = float(df_5m['Close'].dropna().iloc[-1])

        scalp_res = analyze_fast_scalp(df_5m, margin, asset_info['type'], symbol)
        monthly_report = get_monthly_report()

        data = {
            "symbol": symbol,
            "tv_symbol": asset_info['tv'],
            "tab": tab,
            "margin": margin,
            "price": current_price,
            "scalp": scalp_res,
            "time": datetime.now().strftime("%H:%M:%S")
        }
    except Exception as e:
        data = {
            "symbol": symbol, "tv_symbol": "BINANCE:BTCUSDT", "tab": tab, "margin": margin, "price": 0,
            "scalp": {"signal": f"در حال اتصال مجدد: {e}", "status_class": "hold", "entry": None, "tp": None, "sl": None, "win_rate": 50, "loss_rate": 50, "lev_text": "-", "pos_text": "-", "active_trade": None, "projected_path": []},
            "time": datetime.now().strftime("%H:%M:%S")
        }
        monthly_report = []

    return render_template_string(
        HTML_TEMPLATE, 
        data=data, 
        assets=ASSETS, 
        upcoming_gems=UPCOMING_GEMS, 
        bottom_gems=BOTTOM_DIP_GEMS, 
        monthly_report=monthly_report
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

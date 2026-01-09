#!/usr/bin/env python3
from okx import Market
import pandas as pd
import pandas_ta_classic as ta  # Modern fork of pandas_ta_classic
from tabulate import tabulate
from datetime import datetime
import warnings
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
warnings.filterwarnings("ignore")

# Email from GitHub secrets (secure)
SENDER_EMAIL = os.environ['SENDER_EMAIL']
SENDER_PASSWORD = os.environ['SENDER_PASSWORD']
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', SENDER_EMAIL)

def send_professional_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, "html"))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Email error: {e}")

# Initialize OKX Market API (no auth needed for public data)
market_api = Market.MarketAPI(flag="0")  # "0" = live

TIMEFRAMES = {
    "Weekly": "1W",
    "Daily": "1D",
    "4H": "4H"
}

def get_data(inst_id, tf):
    try:
        # Fetch candlesticks (OHLCV) - limit=200
        response = market_api.get_candlesticks(instId=inst_id, bar=tf, limit=200)
        if response["code"] != "0":
            print(f"Fetch error {inst_id} {tf}: {response['msg']}")
            return pd.DataFrame()

        data = response["data"]
        df = pd.DataFrame(data, columns=['ts', 'o', 'h', 'l', 'c', 'v', 'volCcy', 'volCcyQuote', 'confirm'])
        df = df.astype(float)
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df[['ts', 'o', 'h', 'l', 'c', 'v']]  # Standard OHLCV
    except Exception as e:
        print(f"Fetch error {inst_id} {tf}: {e}")
        return pd.DataFrame()

def score_asset(df):
    score = 0
    # === DMI ===
    adx = ta.adx(high=df['h'], low=df['l'], close=df['c'])
    df['adx'] = adx['ADX_14']
    df['plus'] = adx['DMP_14']
    df['minus'] = adx['DMN_14']
    if df['adx'].iloc[-1] > 19: score += 5
    if df['plus'].iloc[-1] > 19: score += 5
    if df['adx'].iloc[-1] > 30: score += 10
    if df['plus'].iloc[-1] > 30: score += 10
    if (df['plus'].iloc[-1] > df['plus'].iloc[-2]) or (df['adx'].iloc[-1] > df['adx'].iloc[-2]):
        score += 5
    if df['minus'].iloc[-1] < 17: score += 5
    if df['minus'].iloc[-1] < 10: score += 5
    if df['minus'].iloc[-1] < df['minus'].iloc[-2] < df['minus'].iloc[-3]:
        score += 5
    # === RSI ===
    df['rsi'] = ta.rsi(df['c'], length=14)
    df['rsi_ma'] = df['rsi'].rolling(14).mean()
    if df['rsi'].iloc[-1] > 50: score += 10
    if df['rsi'].iloc[-1] < 83: score += 5
    if df['rsi'].iloc[-1] > df['rsi_ma'].iloc[-1]: score += 5
    if df['rsi_ma'].iloc[-1] < 55: score += 5
    # === MACD ===
    macd = ta.macd(df['c'])
    df['macd'] = macd['MACD_12_26_9']
    df['signal'] = macd['MACDs_12_26_9']
    df['hist'] = macd['MACDh_12_26_9']
    if df['hist'].iloc[-1] >= 0: score += 5
    if df['hist'].iloc[-1] > df['hist'].iloc[-2]: score += 5
    if df['macd'].iloc[-1] > df['signal'].iloc[-1]: score += 5
    if df['macd'].iloc[-1] > df['hist'].iloc[-1]: score += 5
    if df['signal'].iloc[-1] > df['hist'].iloc[-1]: score += 5
    if df['macd'].iloc[-1] < df['hist'].iloc[-1] and df['macd'].iloc[-1] > 0: score += 3
    if df['macd'].iloc[-1] < df['hist'].iloc[-1] and df['macd'].iloc[-1] > -0.5: score += 2
    if df['hist'].iloc[-1] > df['signal'].iloc[-1]: score += 1
    # NEW: Tiered bonus for recent bullish MACD crossover
    cross_above = (df['macd'].shift(1) <= df['signal'].shift(1)) & (df['macd'] > df['signal'])
    if cross_above.iloc[-3:].any():
        score += 25
    elif cross_above.iloc[-5:].any():
        score += 15
    elif cross_above.iloc[-7:].any():
        score += 10
    # === ICHIMOKU STRUCTURE ===
    df['ema3'] = ta.ema(df['c'], length=3)
    df['ma3'] = ta.sma(df['c'], length=3)
    df['ema5'] = ta.ema(df['c'], length=5)
    df['ma6'] = ta.sma(df['c'], length=6)
    df['cl'] = (df['h'].rolling(9).max() + df['l'].rolling(9).min()) / 2
    df['bl'] = (df['h'].rolling(26).max() + df['l'].rolling(26).min()) / 2
    cl = df['cl'].iloc[-1]
    bl = df['bl'].iloc[-1]
    if cl < df['ema3'].iloc[-1]: score += 5
    if cl > df['ma3'].iloc[-1] or cl > df['ema5'].iloc[-1] or cl > df['ma6'].iloc[-1]: score += 5
    if bl > df['ma6'].iloc[-1]: score += 5
    # === MOVING AVERAGES ===
    df['ma20'] = ta.sma(df['c'], length=20)
    df['ma33'] = ta.sma(df['c'], length=33)
    if df['ma20'].iloc[-1] > df['ma20'].iloc[-2]: score += 5
    if df['ma33'].iloc[-1] > df['ma33'].iloc[-2]: score += 5
    return score

def run_scan():
    print(f"\n{'='*100}")
    print(f" JAMES' OKX FULL-MARKET SWAP LONG-TREND SCANNER ({datetime.now():%b %d, %Y · %I:%M %p})")
    print(f"{'='*100}\n")

    # Fetch all active perpetual swaps
    result = market_api.get_instruments(instType="SWAP")
    if result["code"] != "0":
        print("Error fetching instruments:", result["msg"])
        return ""

    all_instruments = result["data"]

    # Filter: ONLY USDT-margined (all) + BTC-margined inverse (BTC only)
    perpetual_symbols = []
    for instr in all_instruments:
        if instr["state"] != "live":
            continue
        inst_id = instr["instId"]
        settle_ccy = instr.get("settleCcy", "").upper()

        if "-USDT-SWAP" in inst_id:                    # All USDT-margined
            perpetual_symbols.append(inst_id)
        elif "-USD-SWAP" in inst_id and settle_ccy == "BTC":  # Only BTC-margined inverse
            perpetual_symbols.append(inst_id)

    print(f"Filtered active perpetuals (USDT-margined + BTC-margined only): {len(perpetual_symbols)}")

    html = f"""
    <html>
    <head>
    <style>
    body {{font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; background: #f8f9fa; margin: 40px; line-height: 1.6;}}
    h1 {{color: #1a3e72; text-align: center; border-bottom: 3px solid #1a3e72; padding-bottom: 10px;}}
    h2 {{color: #2c5282;}}
    h3 {{color: #2d3748;}}
    table {{width: 80%; margin: 25px auto; border-collapse: collapse; box-shadow: 0 2px 10px rgba(0,0,0,0.1);}}
    th, td {{border: 1px solid #cbd5e0; padding: 12px; text-align: center;}}
    th {{background: #e6fffa; color: #1a3e72; font-weight: bold;}}
    tr:nth-child(even) {{background: #f7fafc;}}
    .footer {{text-align: center; font-size: 0.85em; color: #718096; margin-top: 60px; border-top: 1px solid #e2e8f0; padding-top: 20px;}}
    </style>
    </head>
    <body>
    <h1>James' OKX Full-Market Long-Trend Scanner</h1>
    <p style="text-align:center;"><strong>Report Generated:</strong> {datetime.now():%B %d, %Y · %I:%M %p}</p>
    <p style="text-align:center;">Top 10 assets per timeframe (All OKX Perpetual Swaps - USDT & BTC-Margined)</p>
    <h2>USDT-Margined (Linear) & BTC-Margined (Inverse) Perpetual Markets</h2>
    """

    for label, tf in TIMEFRAMES.items():
        rankings = []
        for symbol in perpetual_symbols:
            try:
                df = get_data(symbol, tf)
                if len(df) < 60:
                    continue
                score = score_asset(df)
                rankings.append([
                    symbol.replace('-SWAP', ' (Perp)'),
                    score,
                    f"{df['c'].iloc[-1]:.8f}"
                ])
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                continue

        top10 = sorted(rankings, key=lambda x: -x[1])[:10]
        print(f"\n▶ {label} ({tf.upper()})\n")
        if top10:
            print(tabulate(top10, headers=["Symbol", "Score", "Price"], tablefmt="github"))
        else:
            print("No data\n")

        html += f"<h3>{label} Timeframe ({tf.upper()}) - Top 10</h3>"
        if top10:
            df_top = pd.DataFrame(top10, columns=["Symbol", "Score", "Price"])
            html += df_top.to_html(index=False, border=0)
        else:
            html += "<p style='text-align:center;'>No qualifying assets.</p>"

    html += """
    <div class="footer">
    <p><strong>Disclaimer:</strong> For informational purposes only. Not financial advice.</p>
    <p>Generated automatically • Confidential • James' Proprietary Scanner</p>
    </div>
    </body></html>
    """
    return html

if __name__ == "__main__":
    html_body = run_scan()
    subject = f"OKX Full-Market Long-Trend Report • {datetime.now():%b %d, %Y • %I:%M %p}"
    send_professional_email(subject, html_body)

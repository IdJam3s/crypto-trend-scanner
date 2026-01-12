#!/usr/bin/env python3
import okx.PublicData as PublicData
import okx.MarketData as MarketData # ← Correct for get_candlesticks
import pandas as pd
import pandas_ta_classic as ta
from tabulate import tabulate
from datetime import datetime
import warnings
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

warnings.filterwarnings("ignore")

print("Script loaded with __name__ =", __name__)

# <--- PLACE THE CLIENTS HERE --->
public_data_api = PublicData.PublicAPI(flag="0")
market_data_api = MarketData.MarketAPI(flag="0")

# Email setup (unchanged)
SENDER_EMAIL = os.environ['SENDER_EMAIL']
SENDER_PASSWORD = os.environ['SENDER_PASSWORD']
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', SENDER_EMAIL)

def send_professional_email(subject, html_body):
    # Your existing function (unchanged)
    pass  # Replace with full code

# Initialize OKX Market API (public data)
public_api = PublicData.PublicAPI(flag="0")      # For get_instruments
market_api = MarketData.MarketAPI(flag="0")      # For get_candlesticks

TIMEFRAMES = {
    "Weekly": "1W",
    "Daily": "1D",
    "4H": "4H"
}

def get_data(inst_id, tf):
    try:
        response = market_api.get_candlesticks(instId=inst_id, bar=tf, limit=200)  # ← Fixed client
        if response["code"] != "0":
            print(f"Fetch error {inst_id} {tf}: {response['msg']}")
            return pd.DataFrame()

        data = response["data"]
        df = pd.DataFrame(data, columns=['ts', 'o', 'h', 'l', 'c', 'v', 'volCcy', 'volCcyQuote', 'confirm'])
        df = df.astype(float)
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        return df[['ts', 'o', 'h', 'l', 'c', 'v']]
    except Exception as e:
        print(f"Fetch error {inst_id} {tf}: {e}")
        return pd.DataFrame()

# Your score_asset function (paste full version here)
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
    print(f" JAMES' OKX FULL-MARKET + BTC-SPOT 6 LONG-TREND SCANNER ({datetime.now():%b %d, %Y · %I:%M %p})")
    print(f"{'='*100}\n")

    # Fetch instruments using PublicData if needed, but for simplicity use MarketData if it supports
    # (fallback: keep PublicData for instruments if MarketData doesn't have it)
    # ── Fetch SWAP (perpetuals) ──
    swap_result = public_data_api.get_instruments(instType="SWAP")   # ← use public_data_api here
    if swap_result["code"] != "0":
        print("SWAP fetch error:", swap_result["msg"])
        return ""

    swap_instruments = swap_result["data"]

    # ── Fetch SPOT ──
    spot_result = public_data_api.get_instruments(instType="SPOT")
    if spot_result["code"] != "0":
        print("SPOT fetch error:", spot_result["msg"])
        spot_instruments = []  # fallback to empty list if failed
    else:
        spot_instruments = spot_result["data"]

    # ── Now filter both ──
    symbols = []  # or your existing list name

    # Filter SWAP (USDT-margined + BTC-margined inverse)
    for instr in swap_instruments:
        if instr["state"] != "live":
            continue
        inst_id = instr["instId"]
        settle_ccy = instr.get("settleCcy", "").upper()

        if "-USDT-SWAP" in inst_id:
            symbols.append((inst_id, "Perp USDT"))
        elif "-USD-SWAP" in inst_id and settle_ccy == "BTC":
            symbols.append((inst_id, "Perp BTC"))

    # Filter SPOT (only BTC-quoted pairs)
    for instr in spot_instruments:
        if instr["state"] == "live" and instr.get("quoteCcy", "").upper() == "BTC":
            inst_id = instr["instId"]  # e.g., SOL-BTC
            symbols.append((inst_id, "Spot BTC"))

    print(f"Total symbols to scan (Perps + BTC-quoted Spot): {len(symbols)}")

    # Filter: ONLY USDT-margined (all) + BTC-margined inverse (BTC only)
        # ── Filter & combine ──
    symbols = []  # ← Changed from perpetual_symbols to symbols (more accurate now)

    # Filter SWAP (USDT-margined + BTC-margined inverse)
    for instr in swap_instruments:  # ← This line is correct (you already changed to swap_instruments)
        if instr["state"] != "live":
            continue
        inst_id = instr["instId"]
        settle_ccy = instr.get("settleCcy", "").upper()

        if "-USDT-SWAP" in inst_id:
            symbols.append((inst_id, "Perp USDT"))     # ← Changed: append tuple instead of just inst_id
        elif "-USD-SWAP" in inst_id and settle_ccy == "BTC":
            symbols.append((inst_id, "Perp BTC"))

    #print(f"Filtered active perpetuals (USDT-margined + BTC-margined only): {len(perpetual_symbols)}")
    print(f"Total symbols to scan (Perps + BTC-quoted Spot): {len(symbols)}")

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
        for inst_id, market_type in symbols:   # ← Changed from perpetual_symbols to symbols + unpack tuple
            try:
                df = get_data(inst_id, tf)
                time.sleep(0.2)  # ← Add this to avoid rate limits (very important now with more symbols)
                if len(df) < 60:
                    continue
                score = score_asset(df)

                # Improved display name: shows market type clearly
                display_symbol = inst_id.replace('-SWAP', f' {market_type}').replace('-BTC', f' {market_type}')

                rankings.append([
                    display_symbol,
                    score,
                    f"{df['c'].iloc[-1]:.8f}"
                ])
            except Exception as e:
                print(f"Error processing {inst_id} ({market_type}): {e}")
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
    # Debug: confirm HTML was built
    print("HTML generation completed, length:", len(html))

    return html

if __name__ == "__main__":
    try:
        html_body = run_scan()
        if not html_body:
            print("Warning: html_body is empty - no email sent")
        else:
            subject = f"OKX Perps + BTC-Spot Long-Trend Report • {datetime.now():%b %d, %Y • %I:%M %p}"
            send_professional_email(subject, html_body)
    except Exception as e:
        timestamped_message = f"[{datetime.now():%Y-%m-%d %H:%M:%S UTC}] Script failed: {e}"
        print(timestamped_message)

        # Optional: also send an error notification email
        error_body = f"<p><strong>Error occurred:</strong> {timestamped_message}</p>"
        send_professional_email("OKX Scanner Error Alert", error_body)


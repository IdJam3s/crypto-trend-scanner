#!/usr/bin/env python3

import ccxt
import pandas as pd
import pandas_ta_classic as ta
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

# Bybit perpetual swaps
BYBIT_PERP = ccxt.bybit({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# Bybit spot for fallback
BYBIT_SPOT = ccxt.bybit({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

TIMEFRAMES = {
    "Weekly": "1w",
    "Daily": "1d",
    "4H": "4h"
}

QUOTES = {
    "USDT": "USDT",
    "BTC": "BTC"
}

include_spot_fallback = True  # Set False if you want perpetuals only

def get_data(exchange, symbol, tf):
    try:
        df = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, tf, limit=200),
            columns=['ts','o','h','l','c','v']
        )
        return df
    except Exception as e:
        print(f"Fetch error {symbol} {tf}: {e}")
        return pd.DataFrame()

def score_asset(df):
    score = 0

    # === DMI ===
    adx = ta.adx(df['h'], df['l'], df['c'])
    df['adx'], df['plus'], df['minus'] = (
        adx['ADX_14'], adx['DMP_14'], adx['DMN_14']
    )
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
    df['rsi'] = ta.rsi(df['c'], 14)
    df['rsi_ma'] = df['rsi'].rolling(14).mean()
    if df['rsi'].iloc[-1] > 50: score += 10
    if df['rsi'].iloc[-1] < 83: score += 5
    if df['rsi'].iloc[-1] > df['rsi_ma'].iloc[-1]: score += 5
    if df['rsi_ma'].iloc[-1] < 55: score += 5

    # === MACD ===
    macd = ta.macd(df['c'])
    df['macd'], df['signal'], df['hist'] = (
        macd['MACD_12_26_9'], macd['MACDs_12_26_9'], macd['MACDh_12_26_9']
    )
    if df['hist'].iloc[-1] >= 0: score += 5
    if df['hist'].iloc[-1] > df['hist'].iloc[-2]: score += 5
    if df['macd'].iloc[-1] > df['signal'].iloc[-1]: score += 5
    if df['macd'].iloc[-1] > df['hist'].iloc[-1]: score += 5
    if df['signal'].iloc[-1] > df['hist'].iloc[-1]: score += 5
    if df['macd'].iloc[-1] < df['hist'].iloc[-1] and df['macd'].iloc[-1] > 0: score += 3
    if df['macd'].iloc[-1] < df['hist'].iloc[-1] and df['macd'].iloc[-1] > -0.5: score += 2
    if (df['hist'].iloc[-1] > df['signal'].iloc[-1]): score += 1

    # === ICHIMOKU STRUCTURE ===
    df['ema3'] = ta.ema(df['c'], 3)
    df['ma3'] = ta.sma(df['c'], 3)
    df['ema5'] = ta.ema(df['c'], 5)
    df['ma6'] = ta.sma(df['c'], 6)
    df['cl'] = (df['h'].rolling(9).max() + df['l'].rolling(9).min()) / 2
    df['bl'] = (df['h'].rolling(26).max() + df['l'].rolling(26).min()) / 2

    cl = df['cl'].iloc[-1]
    bl = df['bl'].iloc[-1]

    # CL below 3EMA
    if cl < df['ema3'].iloc[-1]:
        score += 5

    # CL above ANY of (3MA, 5EMA, 6MA)
    if (
        cl > df['ma3'].iloc[-1] or
        cl > df['ema5'].iloc[-1] or
        cl > df['ma6'].iloc[-1]
    ):
        score += 5

    # BL above MA6
    if bl > df['ma6'].iloc[-1]:
        score += 5

    # === MOVING AVERAGES ===
    df['ma20'] = ta.sma(df['c'], 20)
    df['ma33'] = ta.sma(df['c'], 33)
    if df['ma20'].iloc[-1] > df['ma20'].iloc[-2]: score += 5
    if df['ma33'].iloc[-1] > df['ma33'].iloc[-2]: score += 5

    return score

def run_scan():
    print(f"\n{'='*100}")
    print(f" JAMES' BYBIT FULL-MARKET LONG-TREND SCANNER ({datetime.now():%b %d, %Y · %I:%M %p})")
    print(f"{'='*100}\n")

    perp_markets = BYBIT_PERP.load_markets()

    html = f"""
    <html>
    <head>
    <style>
    body {{font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; background: #f8f9fa; margin: 40px; line-height: 1.6;}}
    h1 {{color: #1a3e72; text-align: center; border-bottom: 3px solid #1a3e72; padding-bottom: 10px;}}
    h2 {{color: #2c5282; border-bottom: 1px solid #ddd; padding-bottom: 8px;}}
    h3 {{color: #2d3748;}}
    table {{width: 80%; margin: 25px auto; border-collapse: collapse; box-shadow: 0 2px 10px rgba(0,0,0,0.1);}}
    th, td {{border: 1px solid #cbd5e0; padding: 12px; text-align: center;}}
    th {{background: #e6fffa; color: #1a3e72; font-weight: bold;}}
    tr:nth-child(even) {{background: #f7fafc;}}
    .footer {{text-align: center; font-size: 0.85em; color: #718096; margin-top: 60px; border-top: 1px solid #e2e8f0; padding-top: 20px;}}
    </style>
    </head>
    <body>
    <h1>James' Bybit Full-Market Long-Trend Scanner</h1>
    <p style="text-align:center;"><strong>Report Generated:</strong> {datetime.now():%B %d, %Y · %I:%M %p}</p>
    <p style="text-align:center;">Top 5 assets per timeframe/quote (Bybit Perpetual Swaps + Spot fallback)</p>
    """

    for quote_name, quote in QUOTES.items():
        print(f"\n{'#'*90}")
        print(f" {quote_name}-DENOMINATED MARKETS ")
        print(f"{'#'*90}")
        html += f"<h2>{quote_name}-Denominated Markets (Bybit)</h2>"

        quote_symbols = [s for s in perp_markets if perp_markets[s]['active'] and perp_markets[s]['swap'] and quote in s]

        for label, tf in TIMEFRAMES.items():
            rankings = []
            for symbol in quote_symbols:
                try:
                    df = get_data(BYBIT_PERP, symbol, tf)
                    if len(df) < 60:
                        if include_spot_fallback:
                            # Bybit spot symbols are usually the same as perp (e.g., BTCUSDT)
                            spot_symbol = symbol
                            df = get_data(BYBIT_SPOT, spot_symbol, tf)
                            if len(df) < 60:
                                continue
                            symbol_type = "(Spot)"
                        else:
                            continue
                    else:
                        symbol_type = "(Perp)"

                    score = score_asset(df)
                    rankings.append([
                        symbol + f" {symbol_type}",
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

            html += f"<h3>{label} Timeframe ({tf.upper()}) - Top 5</h3>"
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
    subject = f"Bybit Full-Market Long-Trend Report • {datetime.now():%b %d, %Y • %I:%M %p}"
    send_professional_email(subject, html_body)

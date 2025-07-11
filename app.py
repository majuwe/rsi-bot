from flask import Flask
import requests
import math
import os

# Telegram-Konfiguration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = Flask(__name__)
WEBHOOK_URL = "https://wtalerts.com/bot/trading_view"

def calculate_rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bollinger_bands(closes, period=20, stddev_mult=2):
    sma = sum(closes[-period:]) / period
    stddev = math.sqrt(sum((c - sma) ** 2 for c in closes[-period:]) / period)
    lower_bb = sma - stddev_mult * stddev
    return lower_bb

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Fehler beim Senden an Telegram: {e}")

@app.route("/")
def hello():
    return "✅ RSI-Bot läuft"

@app.route("/rsi-scan")
def rsi_scan():
    try:
        tickers = requests.get("https://api.binance.com/api/v3/ticker/24hr").json()
        symbols = [t["symbol"] for t in tickers if t["symbol"].endswith("USDT") and not t["symbol"].endswith("BUSD")]
        top = sorted(symbols, key=lambda s: -float([t for t in tickers if t["symbol"] == s][0]["quoteVolume"]))[:150]

        hits = 0
        signal_details = []
        for symbol in top:
            try:
                url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=50"
                data = requests.get(url).json()
                closes = [float(k[4]) for k in data]
                volumes = [float(k[5]) for k in data]
                rsi = calculate_rsi(closes)
                lower_bb = bollinger_bands(closes)
                avg_vol = sum(volumes[:-1]) / (len(volumes) - 1)
                current_price = closes[-1]
                current_volume = volumes[-1]
                volume_change = round((current_volume / avg_vol) * 100, 1)

                if rsi < 30 and current_price < lower_bb and current_volume > 1.5 * avg_vol:
                    payload = {
                        "pair": symbol.replace("USDT", "/USDT"),
                        "action": "buy-market"
                    }
                    requests.post(WEBHOOK_URL, json=payload)

                    message = f"🟢 RSI Signal erkannt\nCoin: {payload['pair']}\nRSI: {round(rsi, 2)}\nPreis: ${round(current_price, 4)}\nBB-Untergrenze: ${round(lower_bb, 4)}\nVolumenänderung: {volume_change}%\nAktion: {payload['action']}"
                    send_telegram(message)

                    signal_details.append(
                        f"{hits + 1}. {payload['pair']}\n   RSI: {round(rsi, 2)}\n   Preis: ${round(current_price, 4)}\n   BB: ${round(lower_bb, 4)}\n   Volumenänderung: {volume_change}%\n   Aktion: {payload['action']}"
                    )
                    hits += 1
            except:
                continue
        if hits == 0:
            return "✅ RSI-Scan abgeschlossen – 0 Signale"
        else:
            return f"✅ RSI-Scan abgeschlossen – {hits} Signale\n\n" + "\n\n".join(signal_details)
    except Exception as e:
        return f"❌ Fehler: {e}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

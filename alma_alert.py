import math
import requests
import os
from datetime import datetime, timezone

# ============= CẤU HÌNH =============
SYMBOL = "BTCUSDT"      # Cặp muốn theo dõi
INTERVAL = "5m"         # Khung: 1m, 5m, 15m, 1h...
LIMIT = 300             # Số nến lấy (đủ cho ALMA200)
# ====================================

def fetch_klines(symbol, interval, limit=300):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    closes = [float(k[4]) for k in data]      # close price
    close_times = [int(k[6]) for k in data]   # close time (ms)
    return closes, close_times

def alma(series, length=50, offset=0.85, sigma=6.0):
    if len(series) < length:
        return [None] * len(series)
    m = offset * (length - 1)
    s = length / sigma
    out = []
    for i in range(len(series)):
        if i + 1 < length:
            out.append(None)
            continue
        window = series[i+1-length:i+1]
        w_sum = 0.0
        aw_sum = 0.0
        for j, price in enumerate(window):
            w = math.exp(-((j - m) ** 2) / (2 * s * s))
            w_sum += w
            aw_sum += price * w
        out.append(aw_sum / w_sum if w_sum != 0 else None)
    return out

def crossover(series1, series2):
    if len(series1) < 2 or len(series2) < 2:
        return False
    return (
        series1[-2] is not None and series2[-2] is not None and
        series1[-1] is not None and series2[-1] is not None and
        series1[-2] <= series2[-2] and series1[-1] > series2[-1]
    )

def crossunder(series1, series2):
    if len(series1) < 2 or len(series2) < 2:
        return False
    return (
        series1[-2] is not None and series2[-2] is not None and
        series1[-1] is not None and series2[-1] is not None and
        series1[-2] >= series2[-2] and series1[-1] < series2[-1]
    )

def send_telegram(msg: str):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    params = {"chat_id": chat_id, "text": msg}
    requests.get(url, params=params, timeout=10)

def main():
    closes, close_times = fetch_klines(SYMBOL, INTERVAL, LIMIT)

    alma50 = alma(closes, 50)
    alma200 = alma(closes, 200)

    bull = crossover(alma50, alma200)
    bear = crossunder(alma50, alma200)

    if not bull and not bear:
        print("No ALMA cross this run.")
        return

    last_close_ts = close_times[-1] / 1000.0
    last_close_dt = datetime.fromtimestamp(last_close_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if bull:
        msg = f"[{SYMBOL} {INTERVAL}] ALMA50 CẮT LÊN ALMA200 tại nến close {last_close_dt}"
    else:
        msg = f"[{SYMBOL} {INTERVAL}] ALMA50 CẮT XUỐNG ALMA200 tại nến close {last_close_dt}"

    print("Sending alert:", msg)
    send_telegram(msg)

if __name__ == "__main__":
    main()

import math
import requests
import os
from datetime import datetime, timezone

# ============= CẤU HÌNH =============
SYMBOL = "BTCUSDT"      # Cặp muốn theo dõi
INTERVAL = "1m"         # KHUNG THỜI GIAN 1 PHÚT
LIMIT = 300             # Số nến lấy (đủ cho ALMA200)
ALMA_OFFSET = 0.85
ALMA_SIGMA = 6.0
# ====================================

def fetch_klines(symbol: str, interval: str, limit: int = 300):
    """
    Lấy dữ liệu nến từ Binance (public API, không cần API key)
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    closes = [float(k[4]) for k in data]      # close price
    close_times = [int(k[6]) for k in data]   # close time (ms)
    return closes, close_times

def alma(series, length: int = 50, offset: float = 0.85, sigma: float = 6.0):
    """
    Tính ALMA giống ta.alma trong Pine Script
    """
    if len(series) < length:
        return [None] * len(series)
    m = offset * (length - 1)
    s = length / sigma
    out = []
    for i in range(len(series)):
        if i + 1 < length:
            out.append(None)
            continue
        window = series[i + 1 - length:i + 1]
        w_sum = 0.0
        aw_sum = 0.0
        for j, price in enumerate(window):
            w = math.exp(-((j - m) ** 2) / (2 * s * s))
            w_sum += w
            aw_sum += price * w
        out.append(aw_sum / w_sum if w_sum != 0 else None)
    return out

def crossover(series1, series2) -> bool:
    """
    ALMA50 cắt LÊN ALMA200
    """
    if len(series1) < 2 or len(series2) < 2:
        return False
    return (
        series1[-2] is not None and series2[-2] is not None and
        series1[-1] is not None and series2[-1] is not None and
        series1[-2] <= series2[-2] and series1[-1] > series2[-1]
    )

def crossunder(series1, series2) -> bool:
    """
    ALMA50 cắt XUỐNG ALMA200
    """
    if len(series1) < 2 or len(series2) < 2:
        return False
    return (
        series1[-2] is not None and series2[-2] is not None and
        series1[-1] is not None and series2[-1] is not None and
        series1[-2] >= series2[-2] and series1[-1] < series2[-1]
    )

def send_telegram(msg: str):
    """
    Gửi message qua Telegram Bot (dùng token & chat_id trong GitHub Secrets)
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    params = {"chat_id": chat_id, "text": msg}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()

def main():
    closes, close_times = fetch_klines(SYMBOL, INTERVAL, LIMIT)

    # ALMA50 & ALMA200
    alma50 = alma(closes, 50, ALMA_OFFSET, ALMA_SIGMA)
    alma200 = alma(closes, 200, ALMA_OFFSET, ALMA_SIGMA)

    # Kiểm tra giao cắt trên 2 cây nến gần nhất
    bull = crossover(alma50, alma200)
    bear = crossunder(alma50, alma200)

    if not bull and not bear:
        print("No ALMA cross this run.")
        return

    # Thời gian nến cuối cùng (đóng) theo UTC
    last_close_ts = close_times[-1] / 1000.0
    last_close_dt = datetime.fromtimestamp(
        last_close_ts, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")

    if bull:
        msg = f"[{SYMBOL} {INTERVAL}] ALMA50 CẮT LÊN ALMA200 tại nến close {last_close_dt}"
    else:
        msg = f"[{SYMBOL} {INTERVAL}] ALMA50 CẮT XUỐNG ALMA200 tại nến close {last_close_dt}"

    print("Sending alert:", msg)
    send_telegram(msg)

if __name__ == "__main__":
    main()

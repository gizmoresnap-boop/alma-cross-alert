import math
import requests
import os
import json
import time
from datetime import datetime, timezone

# ============= CẤU HÌNH =============
SYMBOL = "BTCUSDT"
INTERVAL = "1m"
LIMIT = 300
ALMA_OFFSET = 0.85
ALMA_SIGMA = 6.0
STATE_FILE = "last_alert.json"
# ====================================

def fetch_klines(symbol: str, interval: str, limit: int = 300, retries=3):
    """Lấy dữ liệu nến từ Binance với retry"""
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    
    for i in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            closes = [float(k[4]) for k in data]
            close_times = [int(k[6]) for k in data]
            return closes, close_times
        except Exception as e:
            if i == retries - 1:
                raise
            print(f"Lỗi API, retry {i+1}/{retries}...")
            time.sleep(2)

def alma(series, length: int = 50, offset: float = 0.85, sigma: float = 6.0):
    """Tính ALMA giống Pine Script"""
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
    """ALMA50 cắt LÊN ALMA200"""
    if len(series1) < 2 or len(series2) < 2:
        return False
    return (
        series1[-2] is not None and series2[-2] is not None and
        series1[-1] is not None and series2[-1] is not None and
        series1[-2] <= series2[-2] and series1[-1] > series2[-1]
    )

def crossunder(series1, series2) -> bool:
    """ALMA50 cắt XUỐNG ALMA200"""
    if len(series1) < 2 or len(series2) < 2:
        return False
    return (
        series1[-2] is not None and series2[-2] is not None and
        series1[-1] is not None and series2[-1] is not None and
        series1[-2] >= series2[-2] and series1[-1] < series2[-1]
    )

def load_state():
    """Đọc trạng thái lần chạy trước"""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    """Lưu trạng thái để tránh spam"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def send_telegram(msg: str, retries=3):
    """Gửi message qua Telegram với retry"""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    params = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}
    
    for i in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return
        except Exception as e:
            if i == retries - 1:
                print(f"Lỗi gửi Telegram: {e}")
            time.sleep(2)

def main():
    # Lấy dữ liệu
    closes, close_times = fetch_klines(SYMBOL, INTERVAL, LIMIT)
    
    # Tính ALMA
    alma50 = alma(closes, 50, ALMA_OFFSET, ALMA_SIGMA)
    alma200 = alma(closes, 200, ALMA_OFFSET, ALMA_SIGMA)
    
    # Kiểm tra giao cắt
    bull = crossover(alma50, alma200)
    bear = crossunder(alma50, alma200)
    
    if not bull and not bear:
        print("Không có tín hiệu giao cắt.")
        return
    
    # Kiểm tra đã gửi alert cho nến này chưa
    state = load_state()
    last_close_ts = close_times[-1]
    
    if state.get("last_alerted_candle") == last_close_ts:
        print("Đã gửi alert cho nến này rồi, bỏ qua...")
        return
    
    # Chuẩn bị thông tin
    current_price = closes[-1]
    last_close_dt = datetime.fromtimestamp(
        last_close_ts / 1000.0, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")
    chart_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{SYMBOL}&interval={INTERVAL}"
    
    # Tạo message
    if bull:
        msg = f"""🟢 <b>TÍN HIỆU TĂNG</b>
{SYMBOL} - Khung {INTERVAL}

💎 Giá hiện tại: <b>${current_price:,.2f}</b>
📊 ALMA50 cắt LÊN ALMA200
⏰ {last_close_dt}

📈 <a href="{chart_link}">Xem chart TradingView</a>"""
    else:
        msg = f"""🔴 <b>TÍN HIỆU GIẢM</b>
{SYMBOL} - Khung {INTERVAL}

💎 Giá hiện tại: <b>${current_price:,.2f}</b>
📊 ALMA50 cắt XUỐNG ALMA200
⏰ {last_close_dt}

📈 <a href="{chart_link}">Xem chart TradingView</a>"""
    
    # Gửi alert
    print("Gửi alert:", msg)
    send_telegram(msg)
    
    # Lưu trạng thái
    save_state({"last_alerted_candle": last_close_ts})
    print("✅ Đã lưu trạng thái.")

if __name__ == "__main__":
    main()

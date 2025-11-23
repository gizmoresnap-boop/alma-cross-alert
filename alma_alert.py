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
    """
    Lấy dữ liệu từ Binance, nếu bị 451 thì fallback sang Binance US
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    # Thử Binance chính
    for i in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            closes = [float(k[4]) for k in data]
            close_times = [int(k[6]) for k in data]
            print("✅ Lấy dữ liệu từ Binance API thành công")
            return closes, close_times
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 451:
                print("⚠️ Binance bị chặn (HTTP 451), chuyển sang Binance US...")
                break
            if i == retries - 1:
                print(f"❌ Lỗi Binance API sau {retries} lần thử: {e}")
                break
            print(f"🔄 Lỗi API, retry {i+1}/{retries}...")
            time.sleep(2)
        except Exception as e:
            if i == retries - 1:
                print(f"❌ Lỗi kết nối Binance: {e}")
                break
            print(f"🔄 Lỗi kết nối, retry {i+1}/{retries}...")
            time.sleep(2)

    # Fallback: Binance US
    print("🔄 Thử Binance US API...")
    url_us = "https://api.binance.us/api/v3/klines"
    for i in range(retries):
        try:
            resp = requests.get(url_us, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            closes = [float(k[4]) for k in data]
            close_times = [int(k[6]) for k in data]
            print("✅ Lấy dữ liệu từ Binance US API thành công")
            return closes, close_times
        except Exception as e:
            if i == retries - 1:
                raise Exception(f"❌ Cả Binance và Binance US đều lỗi. Lỗi cuối: {e}")
            print(f"🔄 Retry Binance US {i+1}/{retries}...")
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
    """
    ALMA50 cắt LÊN ALMA200 giữa nến -2 và -1
    (giống cross bạn thấy trên TradingView)
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
    ALMA50 cắt XUỐNG ALMA200 giữa nến -2 và -1
    """
    if len(series1) < 2 or len(series2) < 2:
        return False
    return (
        series1[-2] is not None and series2[-2] is not None and
        series1[-1] is not None and series2[-1] is not None and
        series1[-2] >= series2[-2] and series1[-1] < series2[-1]
    )

def load_state():
    """Đọc trạng thái lần chạy trước (nếu có)"""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    """Lưu trạng thái (nến đã alert) để tránh gửi trùng"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def send_telegram(msg: str, retries=3):
    """Gửi message qua Telegram với retry nhẹ"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    params = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}

    for i in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            print("✅ Gửi Telegram thành công")
            return
        except Exception as e:
            if i == retries - 1:
                print(f"❌ Lỗi gửi Telegram sau {retries} lần thử: {e}")
            else:
                print(f"🔄 Retry gửi Telegram {i+1}/{retries}...")
            time.sleep(2)

def main():
    print("=" * 50)
    print(f"🚀 Bắt đầu kiểm tra ALMA {SYMBOL} khung {INTERVAL}")
    print("=" * 50)

    # 1) Lấy dữ liệu
    try:
        closes, close_times = fetch_klines(SYMBOL, INTERVAL, LIMIT)
    except Exception as e:
        print(f"❌ Không thể lấy dữ liệu: {e}")
        return

    # 2) Tính ALMA
    print("📊 Đang tính ALMA50 và ALMA200...")
    alma50 = alma(closes, 50, ALMA_OFFSET, ALMA_SIGMA)
    alma200 = alma(closes, 200, ALMA_OFFSET, ALMA_SIGMA)

    # 3) Kiểm tra giao cắt trên HAI NẾN MỚI NHẤT (-2 và -1)
    bull = crossover(alma50, alma200)
    bear = crossunder(alma50, alma200)

    if not bull and not bear:
        print("ℹ️ Không có tín hiệu giao cắt.")
        return

    # 4) Lấy thông tin NẾN MỚI NHẤT (nến -1)
    last_candle_ts = close_times[-1]
    last_candle_close = closes[-1]

    # 5) Tránh gửi alert trùng
    state = load_state()
    if state.get("last_alerted_candle") == last_candle_ts:
        print("⏭️ Nến này đã gửi alert rồi, bỏ qua...")
        return

    last_candle_dt = datetime.fromtimestamp(
        last_candle_ts / 1000.0, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")

    chart_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{SYMBOL}&interval={INTERVAL}"

    # 6) Tạo message
    if bull:
        signal_type = "TÍN HIỆU TĂNG"
        emoji = "🟢"
        action = "cắt LÊN"
    else:
        signal_type = "TÍN HIỆU GIẢM"
        emoji = "🔴"
        action = "cắt XUỐNG"

    msg = f"""{emoji} <b>{signal_type}</b>
{SYMBOL} - Khung {INTERVAL}

💎 Giá đóng nến mới nhất: <b>${last_candle_close:,.2f}</b>
📊 ALMA50 {action} ALMA200
⏰ Nến close: {last_candle_dt}

📈 <a href="{chart_link}">Xem chart TradingView</a>"""

    # 7) Gửi alert + lưu state
    print(f"\n{emoji} Phát hiện tín hiệu: {signal_type}")
    print(f"💰 Giá đóng nến: ${last_candle_close:,.2f}")
    print(f"⏰ Thời gian nến close: {last_candle_dt}")
    print("📤 Đang gửi alert đến Telegram...")
    send_telegram(msg)

    save_state({"last_alerted_candle": last_candle_ts})
    print("✅ Đã lưu trạng thái.")
    print("=" * 50)


if __name__ == "__main__":
    main()

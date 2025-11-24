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
    Lấy dữ liệu từ nhiều nguồn (Binance → Binance US nếu bị chặn)
    """
    # Thử Binance API chính trước
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    
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
                print(f"❌ Lỗi Binance API sau {retries} lần thử")
                break
            print(f"🔄 Lỗi API, retry {i+1}/{retries}...")
            time.sleep(2)
        except Exception as e:
            if i == retries - 1:
                print(f"❌ Lỗi kết nối Binance: {e}")
                break
            time.sleep(2)
    
    # Dùng Binance US API dự phòng
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
                raise Exception(f"❌ Cả 2 API đều lỗi. Lỗi cuối: {e}")
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
    ALMA50 cắt LÊN ALMA200 trên nến ĐÃ ĐÓNG
    Kiểm tra nến -3 và -2 (cả 2 đều đã đóng hoàn toàn)
    """
    if len(series1) < 3 or len(series2) < 3:
        return False
    return (
        series1[-3] is not None and series2[-3] is not None and
        series1[-2] is not None and series2[-2] is not None and
        series1[-3] <= series2[-3] and series1[-2] > series2[-2]
    )

def crossunder(series1, series2) -> bool:
    """
    ALMA50 cắt XUỐNG ALMA200 trên nến ĐÃ ĐÓNG
    Kiểm tra nến -3 và -2 (cả 2 đều đã đóng hoàn toàn)
    """
    if len(series1) < 3 or len(series2) < 3:
        return False
    return (
        series1[-3] is not None and series2[-3] is not None and
        series1[-2] is not None and series2[-2] is not None and
        series1[-3] >= series2[-3] and series1[-2] < series2[-2]
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
    print("=" * 70)
    print(f"🚀 Bắt đầu kiểm tra ALMA {SYMBOL} khung {INTERVAL}")
    print("=" * 70)
    
    # Lấy dữ liệu
    try:
        closes, close_times = fetch_klines(SYMBOL, INTERVAL, LIMIT)
    except Exception as e:
        print(f"❌ Không thể lấy dữ liệu: {e}")
        return
    
    # Tính ALMA
    print("📊 Đang tính ALMA50 và ALMA200...")
    alma50 = alma(closes, 50, ALMA_OFFSET, ALMA_SIGMA)
    alma200 = alma(closes, 200, ALMA_OFFSET, ALMA_SIGMA)
    
    # ========== DEBUG: IN RA GIÁ TRỊ ALMA ==========
    print("\n🔍 DEBUG - Giá trị ALMA các nến gần nhất:")
    print("-" * 70)
    for i in range(-10, 0):  # 10 nến cuối
        candle_time = datetime.fromtimestamp(
            close_times[i] / 1000.0, tz=timezone.utc
        ).strftime("%H:%M:%S")
        
        a50 = alma50[i] if alma50[i] is not None else "N/A"
        a200 = alma200[i] if alma200[i] is not None else "N/A"
        
        if isinstance(a50, float) and isinstance(a200, float):
            diff = a50 - a200
            status = "🟢 ALMA50 > ALMA200" if diff > 0 else "🔴 ALMA50 < ALMA200"
            print(f"Nến [{candle_time}] | ALMA50: {a50:.2f} | ALMA200: {a200:.2f} | {status}")
        else:
            print(f"Nến [{candle_time}] | ALMA50: {a50} | ALMA200: {a200}")
    print("-" * 70)
    
    # ========== DEBUG: KIỂM TRA LOGIC GIAO CẮT ==========
    print("\n🔍 DEBUG - Kiểm tra điều kiện giao cắt:")
    print("-" * 70)
    
    # Kiểm tra nến -3 và -2
    if len(alma50) >= 3 and len(alma200) >= 3:
        a50_prev = alma50[-3]  # Nến -3
        a200_prev = alma200[-3]
        a50_curr = alma50[-2]  # Nến -2 (đã đóng)
        a200_curr = alma200[-2]
        
        print(f"Nến -3: ALMA50={a50_prev:.2f if a50_prev else 'N/A'}, ALMA200={a200_prev:.2f if a200_prev else 'N/A'}")
        print(f"Nến -2: ALMA50={a50_curr:.2f if a50_curr else 'N/A'}, ALMA200={a200_curr:.2f if a200_curr else 'N/A'}")
        
        if all([a50_prev, a200_prev, a50_curr, a200_curr]):
            print(f"\n📊 So sánh:")
            print(f"  - Nến -3: ALMA50 {'<=' if a50_prev <= a200_prev else '>'} ALMA200")
            print(f"  - Nến -2: ALMA50 {'>' if a50_curr > a200_curr else '<='} ALMA200")
            
            if a50_prev <= a200_prev and a50_curr > a200_curr:
                print("  ✅ ĐÃ CÓ CROSSOVER (ALMA50 cắt LÊN)")
            elif a50_prev >= a200_prev and a50_curr < a200_curr:
                print("  ✅ ĐÃ CÓ CROSSUNDER (ALMA50 cắt XUỐNG)")
            else:
                print("  ℹ️ KHÔNG CÓ GIAO CẮT")
        else:
            print("⚠️ Có giá trị ALMA = None, không thể kiểm tra giao cắt")
    print("-" * 70)
    
    # Kiểm tra giao cắt bằng hàm
    bull = crossover(alma50, alma200)
    bear = crossunder(alma50, alma200)
    
    print(f"\n🎯 Kết quả từ hàm crossover/crossunder:")
    print(f"  - Crossover (tăng): {bull}")
    print(f"  - Crossunder (giảm): {bear}")
    print("=" * 70)
    
    if not bull and not bear:
        print("\nℹ️ Không có tín hiệu giao cắt trên nến đã đóng.")
        return
    
    # Lấy thông tin nến ĐÃ ĐÓNG (nến -2)
    last_closed_candle_ts = close_times[-2]
    
    # Kiểm tra đã gửi alert cho nến này chưa
    state = load_state()
    
    if state.get("last_alerted_candle") == last_closed_candle_ts:
        print("⏭️ Đã gửi alert cho nến này rồi, bỏ qua...")
        return
    
    # Chuẩn bị thông tin
    candle_close_price = closes[-2]
    current_price = closes[-1]
    
    candle_close_dt = datetime.fromtimestamp(
        last_closed_candle_ts / 1000.0, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    chart_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{SYMBOL}&interval={INTERVAL}"
    
    # Tạo message
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

📍 Nến giao cắt (đã đóng): <b>${candle_close_price:,.2f}</b>
💎 Giá hiện tại: <b>${current_price:,.2f}</b>
📊 ALMA50 {action} ALMA200
⏰ Thời gian nến đóng: {candle_close_dt}

📈 <a href="{chart_link}">Xem chart TradingView</a>"""
    
    # Gửi alert
    print(f"\n{emoji} Phát hiện tín hiệu: {signal_type}")
    print(f"📍 Giá nến đóng: ${candle_close_price:,.2f}")
    print(f"💰 Giá hiện tại: ${current_price:,.2f}")
    print(f"⏰ Thời gian: {candle_close_dt}")
    print(f"📤 Đang gửi alert đến Telegram...")
    send_telegram(msg)
    
    # Lưu trạng thái
    save_state({"last_alerted_candle": last_closed_candle_ts})
    print("✅ Đã lưu trạng thái.")
    print("=" * 70)

if __name__ == "__main__":
    main()

import os
import time
import requests

# =============== SETTINGS ===============

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOL = "ETHUSDT"
INTERVAL = "15m"

EMA_FAST = 9
EMA_SLOW = 20

SWING_LOOKBACK = 20
MAX_RETEST_CANDLES = 8
RISK_REWARD = 2.0

# Watch alert when price is within 0.3% of a level.
WATCH_DISTANCE = 0.003

CHECK_INTERVAL = 20

BINANCE_URL = "https://api.binance.com/api/v3/klines"
TELEGRAM_URL = "https://api.telegram.org/bot{}/sendMessage"


# =============== TELEGRAM ===============

def send_telegram(message):
    response = requests.post(
        TELEGRAM_URL.format(TOKEN),
        json={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=15
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError("Telegram message failed.")


# =============== MARKET DATA ===============

def get_candles():
    response = requests.get(
        BINANCE_URL,
        params={
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "limit": 100
        },
        timeout=15
    )

    response.raise_for_status()

    now_ms = int(time.time() * 1000)
    raw_data = response.json()
    candles = []

    for item in raw_data:
        # Use completed candles only.
        if int(item[6]) >= now_ms:
            continue

        candles.append({
            "time": int(item[0]),
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4])
        })

    return candles


# =============== EMA ===============

def calculate_ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period

    for value in values[period:]:
        result = (
            value * multiplier
            + result * (1 - multiplier)
        )

    return result


# =============== TRADE SETUP MESSAGE ===============

def create_trade_alert(direction, entry, stop_loss):
    if direction == "LONG":
        risk = entry - stop_loss
        target = entry + risk * RISK_REWARD
    else:
        risk = stop_loss - entry
        target = entry - risk * RISK_REWARD

    if risk <= 0:
        return None

    return (
        f"{'🟢' if direction == 'LONG' else '🔴'} "
        f"ETH/USDT {direction} SETUP\n\n"
        f"⏱️ Timeframe: {INTERVAL}\n"
        f"💰 Entry reference: {entry:.2f}\n"
        f"🛑 Stop Loss: {stop_loss:.2f}\n"
        f"🎯 Target (2R): {target:.2f}\n"
        f"📏 Risk per ETH: {risk:.2f}\n\n"
        "Setup: Breakout + Retest\n"
        "Alerts only. No trade executed.\n"
        "No profit guarantee."
    )


# =============== MAIN BOT ===============

def main():
    if not TOKEN or not CHAT_ID:
        raise RuntimeError(
            "Telegram settings missing. Set "
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "in PowerShell first."
        )

    send_telegram(
        "🟢 ETH/USDT ALERT BOT STARTED\n\n"
        "⏱️ Timeframe: 15m\n"
        "👀 Breakout/Breakdown watch: ON\n"
        "🎯 Retest setup alerts: ON\n"
        "📊 Routine market updates: OFF\n\n"
        "Alert-only mode. No trades executed."
    )

    print(
        "ETH/USDT alert bot running. Ctrl+C to stop.",
        flush=True
    )

    last_processed_candle = None

    long_level = None
    long_bar_index = None

    short_level = None
    short_bar_index = None

    watch_state = None

    while True:
        try:
            candles = get_candles()

            print(
                f"Completed candles received: {len(candles)}",
                flush=True
            )

            minimum = max(
                SWING_LOOKBACK + 2,
                EMA_SLOW + 2
            )

            if len(candles) < minimum:
                time.sleep(CHECK_INTERVAL)
                continue

            current = candles[-1]

            # Process each completed candle once.
            if current["time"] == last_processed_candle:
                time.sleep(CHECK_INTERVAL)
                continue

            last_processed_candle = current["time"]
            index = len(candles) - 1
            price = current["close"]

            closes = [c["close"] for c in candles]

            fast = calculate_ema(closes[-60:], EMA_FAST)
            slow = calculate_ema(closes[-60:], EMA_SLOW)

            if fast is None or slow is None:
                time.sleep(CHECK_INTERVAL)
                continue

            previous_candles = candles[
                -(SWING_LOOKBACK + 1):-1
            ]

            resistance = max(
                c["high"] for c in previous_candles
            )

            support = min(
                c["low"] for c in previous_candles
            )

            print(
                f"Price={price:.2f} | "
                f"EMA9={fast:.2f} | EMA20={slow:.2f} | "
                f"Support={support:.2f} | "
                f"Resistance={resistance:.2f}",
                flush=True
            )

            # -------- WATCH ALERTS --------

            near_resistance = (
                price < resistance
                and price >= resistance * (1 - WATCH_DISTANCE)
                and fast > slow
            )

            near_support = (
                price > support
                and price <= support * (1 + WATCH_DISTANCE)
                and fast < slow
            )

            if near_resistance:
                if watch_state != "RESISTANCE":
                    send_telegram(
                        "👀 ETH/USDT BREAKOUT WATCH\n\n"
                        f"💰 Price: {price:.2f}\n"
                        f"🔴 Resistance: {resistance:.2f}\n"
                        f"📈 EMA9: {fast:.2f}\n"
                        f"📉 EMA20: {slow:.2f}\n\n"
                        "Price is near resistance.\n"
                        "Wait for a confirmed breakout and retest.\n"
                        "This is NOT an entry signal."
                    )

                    watch_state = "RESISTANCE"

            elif near_support:
                if watch_state != "SUPPORT":
                    send_telegram(
                        "👀 ETH/USDT BREAKDOWN WATCH\n\n"
                        f"💰 Price: {price:.2f}\n"
                        f"🟢 Support: {support:.2f}\n"
                        f"📈 EMA9: {fast:.2f}\n"
                        f"📉 EMA20: {slow:.2f}\n\n"
                        "Price is near support.\n"
                        "Wait for a confirmed breakdown and retest.\n"
                        "This is NOT an entry signal."
                    )

                    watch_state = "SUPPORT"

            else:
                watch_state = None

            # -------- EXPIRE OLD SETUPS --------

            if (
                long_bar_index is not None
                and index - long_bar_index > MAX_RETEST_CANDLES
            ):
                long_level = None
                long_bar_index = None

            if (
                short_bar_index is not None
                and index - short_bar_index > MAX_RETEST_CANDLES
            ):
                short_level = None
                short_bar_index = None

            # -------- LONG RETEST --------

            if (
                long_level is not None
                and index > long_bar_index
            ):
                level = long_level

                if price < level * 0.998:
                    long_level = None
                    long_bar_index = None

                elif (
                    current["low"] <= level * 1.0015
                    and price > level
                    and fast > slow
                ):
                    alert = create_trade_alert(
                        "LONG",
                        price,
                        current["low"]
                    )

                    if alert:
                        send_telegram(alert)
                        print("LONG setup alert sent.", flush=True)

                    long_level = None
                    long_bar_index = None

            # -------- SHORT RETEST --------

            if (
                short_level is not None
                and index > short_bar_index
            ):
                level = short_level

                if price > level * 1.002:
                    short_level = None
                    short_bar_index = None

                elif (
                    current["high"] >= level * 0.9985
                    and price < level
                    and fast < slow
                ):
                    alert = create_trade_alert(
                        "SHORT",
                        price,
                        current["high"]
                    )

                    if alert:
                        send_telegram(alert)
                        print("SHORT setup alert sent.", flush=True)

                    short_level = None
                    short_bar_index = None

            # -------- DETECT NEW BREAKOUT --------

            if price > resistance and fast > slow:
                if long_level is None:
                    long_level = resistance
                    long_bar_index = index

                    short_level = None
                    short_bar_index = None

                    print(
                        f"Breakout detected at {long_level:.2f}",
                        flush=True
                    )

            elif price < support and fast < slow:
                if short_level is None:
                    short_level = support
                    short_bar_index = index

                    long_level = None
                    long_bar_index = None

                    print(
                        f"Breakdown detected at {short_level:.2f}",
                        flush=True
                    )

        except requests.RequestException as error:
            print(
                f"Network/API error: {error}",
                flush=True
            )

        except Exception as error:
            print(
                f"Bot error: {type(error).__name__}: {error}",
                flush=True
            )

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("\nBot stopped.", flush=True)

    except Exception as error:
        print(
            f"Startup error: {type(error).__name__}: {error}",
            flush=True
        )
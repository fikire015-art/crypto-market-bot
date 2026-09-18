import os
import asyncio
import logging
from typing import Optional

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =========================================================
# CONFIG
# =========================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_KEY")

INTERVAL = "15min"
OUTPUT_SIZE = 100
REQUEST_TIMEOUT = 20

# Keep this list small on the free Twelve Data plan.
# /time_series costs 1 API credit per symbol.
SCAN_SYMBOLS = [
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "XRP/USD",
    "BNB/USD",
    "ADA/USD",
]

BASE_URL = "https://api.twelvedata.com/time_series"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("crypto-market-bot")


# =========================================================
# INDICATORS
# =========================================================

def ema(values: list[float], period: int) -> Optional[float]:
    """Calculate the latest EMA value."""
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)
    current = sum(values[:period]) / period

    for price in values[period:]:
        current = (price - current) * multiplier + current

    return current


def rsi(values: list[float], period: int = 14) -> Optional[float]:
    """Calculate the latest RSI using Wilder's smoothing."""
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def make_signal(
    price: float,
    ema9_value: float,
    ema21_value: float,
    rsi_value: float,
) -> tuple[str, str]:
    """
    Simple technical rule:
      BUY  = EMA9 > EMA21 and RSI >= 50
      SELL = EMA9 < EMA21 and RSI <= 50
      WAIT = mixed/neutral conditions

    This is technical-analysis logic only, not a guarantee of future movement.
    """
    if ema9_value > ema21_value and rsi_value >= 50:
        if rsi_value >= 70:
            return "BUY", "Bullish EMA alignment; RSI is strong/overbought."
        return "BUY", "EMA 9 is above EMA 21 and RSI is above 50."

    if ema9_value < ema21_value and rsi_value <= 50:
        if rsi_value <= 30:
            return "SELL", "Bearish EMA alignment; RSI is weak/oversold."
        return "SELL", "EMA 9 is below EMA 21 and RSI is below 50."

    return "WAIT", "EMA and RSI are not aligned strongly enough."


# =========================================================
# TWELVE DATA
# =========================================================

def fetch_prices(symbol: str) -> tuple[Optional[list[float]], Optional[str]]:
    """Fetch 15-minute closes. Returns (closes, error_message)."""
    if not TWELVE_DATA_KEY:
        return None, "TWELVE_DATA_KEY is missing."

    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "outputsize": OUTPUT_SIZE,
        "order": "asc",
        "apikey": TWELVE_DATA_KEY,
    }

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 429:
            return None, (
                "Twelve Data API limit reached (HTTP 429). "
                "Wait for the quota to reset or use a larger plan."
            )

        response.raise_for_status()

        data = response.json()

        if "code" in data and "message" in data:
            return None, str(data["message"])

        values = data.get("values")
        if not values:
            return None, "No market data returned."

        closes = []
        for row in values:
            try:
                closes.append(float(row["close"]))
            except (KeyError, TypeError, ValueError):
                continue

        if len(closes) < 22:
            return None, f"Not enough data points ({len(closes)})."

        return closes, None

    except requests.Timeout:
        return None, "Twelve Data request timed out."

    except requests.RequestException as exc:
        return None, f"Network/API error: {exc}"

    except ValueError:
        return None, "Twelve Data returned invalid JSON."


def analyze_symbol_data(symbol: str) -> dict:
    closes, error = fetch_prices(symbol)

    if error:
        return {
            "ok": False,
            "symbol": symbol,
            "error": error,
        }

    price = closes[-1]
    ema9_value = ema(closes, 9)
    ema21_value = ema(closes, 21)
    rsi_value = rsi(closes, 14)

    if ema9_value is None or ema21_value is None or rsi_value is None:
        return {
            "ok": False,
            "symbol": symbol,
            "error": "Could not calculate indicators.",
        }

    signal, reason = make_signal(
        price,
        ema9_value,
        ema21_value,
        rsi_value,
    )

    return {
        "ok": True,
        "symbol": symbol,
        "price": price,
        "ema9": ema9_value,
        "ema21": ema21_value,
        "rsi": rsi_value,
        "signal": signal,
        "reason": reason,
    }


# =========================================================
# TELEGRAM FORMATTERS
# =========================================================

def format_analysis(result: dict) -> str:
    symbol = result["symbol"]

    if not result.get("ok"):
        return (
            f"❌ {symbol}\n"
            f"Error: {result.get('error', 'Unknown error')}"
        )

    signal = result["signal"]

    return (
        f"📊 {symbol} — {INTERVAL}\n\n"
        f"💰 Price: {result['price']:.8f}\n"
        f"📈 EMA 9: {result['ema9']:.8f}\n"
        f"📉 EMA 21: {result['ema21']:.8f}\n"
        f"📊 RSI 14: {result['rsi']:.2f}\n\n"
        f"🎯 Signal: {signal}\n"
        f"📌 Reason: {result['reason']}\n\n"
        "⚠️ Technical analysis only — not a guarantee of future price movement."
    )


# =========================================================
# TELEGRAM COMMANDS
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 CryptoFlowBot is online.\n\n"
        "Commands:\n"
        "/analyze BTC/USD — analyze one symbol\n"
        "/scan — scan the configured symbols\n"
        "/all — same as /scan\n"
        "/status — check bot/API configuration\n\n"
        f"⏱ Timeframe: {INTERVAL}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token_ok = bool(TELEGRAM_BOT_TOKEN)
    key_ok = bool(TWELVE_DATA_KEY)

    await update.message.reply_text(
        "🟢 Bot status\n\n"
        f"Telegram token: {'✅ OK' if token_ok else '❌ Missing'}\n"
        f"Twelve Data key: {'✅ OK' if key_ok else '❌ Missing'}\n"
        f"Timeframe: {INTERVAL}\n"
        f"Scan symbols: {len(SCAN_SYMBOLS)}\n"
        f"Output size: {OUTPUT_SIZE}\n\n"
        "Note: each /time_series symbol request uses 1 API credit."
    )


async def analyze_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "እባክዎ symbol ያስገቡ።\n"
            "ለምሳሌ:\n"
            "/analyze BTC/USD\n"
            "/analyze ETH/USD\n"
            "/analyze XAU/USD"
        )
        return

    symbol = context.args[0].upper().strip()

    await update.message.reply_text(
        f"🔍 {symbol} በ {INTERVAL} እየተመረመረ ነው..."
    )

    # requests is blocking, so run it outside Telegram's event loop.
    result = await asyncio.to_thread(analyze_symbol_data, symbol)

    await update.message.reply_text(format_analysis(result))


async def scan_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🔎 {len(SCAN_SYMBOLS)} symbols በ {INTERVAL} እየተመረመሩ ነው..."
    )

    results = []

    for symbol in SCAN_SYMBOLS:
        result = await asyncio.to_thread(analyze_symbol_data, symbol)

        if result.get("ok"):
            results.append(result)

        # Small pause so a large burst is avoided.
        await asyncio.sleep(0.25)

    if not results:
        await update.message.reply_text(
            "⚠️ No usable market data was returned.\n\n"
            "Check:\n"
            "• Twelve Data API key\n"
            "• API credit limit\n"
            "• Symbol availability\n"
            "• Render logs"
        )
        return

    # Put strongest/simple signals first.
    buys = [r for r in results if r["signal"] == "BUY"]
    sells = [r for r in results if r["signal"] == "SELL"]
    waits = [r for r in results if r["signal"] == "WAIT"]

    lines = [
        f"📊 {INTERVAL} MARKET SCAN",
        "",
        f"🟢 BUY: {len(buys)}",
        f"🔴 SELL: {len(sells)}",
        f"🟡 WAIT: {len(waits)}",
        "",
    ]

    for result in results:
        icon = {
            "BUY": "🟢",
            "SELL": "🔴",
            "WAIT": "🟡",
        }.get(result["signal"], "⚪")

        lines.append(
            f"{icon} {result['symbol']} | "
            f"{result['signal']} | "
            f"RSI {result['rsi']:.1f} | "
            f"Price {result['price']:.8f}"
        )

    lines.extend(
        [
            "",
            "⚠️ Technical analysis only.",
            "Not a guarantee of future price movement.",
        ]
    )

    await update.message.reply_text("\n".join(lines))


# =========================================================
# MAIN
# =========================================================

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing from Render Environment Variables."
        )

    if not TWELVE_DATA_KEY:
        raise RuntimeError(
            "TWELVE_DATA_KEY is missing from Render Environment Variables."
        )

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("analyze", analyze_symbol))
    application.add_handler(CommandHandler("scan", scan_market))
    application.add_handler(CommandHandler("all", scan_market))

    logger.info("CryptoFlowBot is running.")
    logger.info("Timeframe: %s", INTERVAL)
    logger.info("Symbols: %s", ", ".join(SCAN_SYMBOLS))

    # run_polling() already keeps the bot alive.
    # Do NOT wrap it in while True.
    application.run_polling()


if __name__ == "__main__":
    main()


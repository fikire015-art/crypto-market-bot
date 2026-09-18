import os
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

# Keep this list small to avoid wasting Twelve Data credits.
SCAN_SYMBOLS = [
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "XRP/USD",
    "BNB/USD",
]

API_URL = "https://api.twelvedata.com/time_series"


# =========================================================
# TWELVE DATA
# =========================================================

def get_market_data(symbol, outputsize=50):
    """Get candles from Twelve Data."""

    if not TWELVE_DATA_KEY:
        return {
            "error": "TWELVE_DATA_KEY is missing."
        }

    try:
        response = requests.get(
            API_URL,
            params={
                "symbol": symbol,
                "interval": INTERVAL,
                "outputsize": outputsize,
                "apikey": TWELVE_DATA_KEY,
            },
            timeout=15,
        )

        data = response.json()

        # API error
        if response.status_code == 429 or data.get("code") == 429:
            return {
                "error": (
                    "Twelve Data API limit reached (429). "
                    "The daily API credits have been exhausted."
                ),
                "rate_limited": True,
            }

        if "status" in data and data["status"] == "error":
            return {
                "error": data.get(
                    "message",
                    "Twelve Data returned an error."
                )
            }

        if "values" not in data or not data["values"]:
            return {
                "error": "No market data returned."
            }

        return {
            "values": data["values"]
        }

    except requests.RequestException as e:
        return {
            "error": f"Network error: {str(e)}"
        }

    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}"
        }


# =========================================================
# SIMPLE TECHNICAL ANALYSIS
# =========================================================

def analyze_data(values):
    """
    Simple 15-minute analysis using:
    - EMA 9
    - EMA 21
    - RSI 14
    """

    # Twelve Data returns newest first.
    candles = list(reversed(values))

    closes = []

    for candle in candles:
        try:
            closes.append(float(candle["close"]))
        except (KeyError, ValueError, TypeError):
            continue

    if len(closes) < 22:
        return {
            "signal": "WAIT",
            "reason": "Not enough candle data.",
        }

    # -------------------------
    # EMA
    # -------------------------

    def ema(data, period):
        multiplier = 2 / (period + 1)
        value = data[0]

        for price in data[1:]:
            value = (
                price - value
            ) * multiplier + value

        return value

    ema9 = ema(closes[-30:], 9)
    ema21 = ema(closes[-30:], 21)

    # -------------------------
    # RSI
    # -------------------------

    period = 14
    recent = closes[-(period + 1):]

    gains = []
    losses = []

    for i in range(1, len(recent)):
        change = recent[i] - recent[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    current_price = closes[-1]

    # -------------------------
    # SIGNAL
    # -------------------------

    if ema9 > ema21 and rsi >= 50 and rsi < 70:
        signal = "BUY"
        reason = "EMA9 above EMA21 and RSI confirms upward momentum."

    elif ema9 < ema21 and rsi <= 50 and rsi > 30:
        signal = "SELL"
        reason = "EMA9 below EMA21 and RSI confirms downward momentum."

    else:
        signal = "WAIT"
        reason = "Indicators are mixed or market momentum is weak."

    return {
        "signal": signal,
        "price": current_price,
        "ema9": ema9,
        "ema21": ema21,
        "rsi": rsi,
        "reason": reason,
    }


# =========================================================
# /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🤖 ሰላም! Crypto Market Bot በ15-minute timeframe ላይ እየሰራ ነው.\n\n"
        "📌 Commands:\n"
        "/scan - የተመረጡ crypto symbols ይቃኛል\n"
        "/all - ተመሳሳይ market scan\n"
        "/analyze BTC/USD\n"
        "/analyze ETH/USD\n"
        "/analyze XAU/USD\n\n"
        "⏱ Timeframe: 15 minutes"
    )


# =========================================================
# /ANALYZE
# =========================================================

async def analyze_symbol(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:
        await update.message.reply_text(
            "⚠️ Symbol ያስገቡ።\n\n"
            "ለምሳሌ:\n"
            "/analyze BTC/USD\n"
            "/analyze XAU/USD"
        )
        return

    symbol = context.args[0].upper()

    await update.message.reply_text(
        f"🔍 Analyzing {symbol}...\n"
        f"⏱ Timeframe: {INTERVAL}"
    )

    result = get_market_data(symbol, 50)

    if "error" in result:

        if result.get("rate_limited"):
            await update.message.reply_text(
                "❌ Twelve Data API limit reached.\n\n"
                "የዛሬ API credits ተጠናቀዋል። "
                "Limit እስኪ reset ድረስ አዲስ market data "
                "መውሰድ አይቻልም።"
            )
        else:
            await update.message.reply_text(
                f"❌ Data error:\n{result['error']}"
            )

        return

    analysis = analyze_data(result["values"])

    signal = analysis["signal"]

    if signal == "BUY":
        emoji = "🟢"
    elif signal == "SELL":
        emoji = "🔴"
    else:
        emoji = "🟡"

    await update.message.reply_text(
        f"📊 {symbol} — {INTERVAL}\n\n"
        f"💰 Price: {analysis.get('price', 0):.5f}\n"
        f"EMA 9: {analysis.get('ema9', 0):.5f}\n"
        f"EMA 21: {analysis.get('ema21', 0):.5f}\n"
        f"RSI 14: {analysis.get('rsi', 0):.2f}\n\n"
        f"{emoji} Signal: {signal}\n\n"
        f"📝 {analysis['reason']}\n\n"
        f"⚠️ This is technical analysis, not a guarantee of future price movement."
    )


# =========================================================
# /SCAN
# =========================================================

async def scan_market(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🔍 Scanning selected symbols...\n"
        "⏱ Timeframe: 15 minutes"
    )

    results = []
    rate_limited = False

    for symbol in SCAN_SYMBOLS:

        data = get_market_data(symbol, 30)

        if "error" in data:

            if data.get("rate_limited"):
                rate_limited = True
                break

            continue

        analysis = analyze_data(data["values"])

        results.append(
            (
                symbol,
                analysis["signal"],
                analysis.get("rsi", 0),
                analysis.get("price", 0),
            )
        )

    # -------------------------
    # API LIMIT
    # -------------------------

    if rate_limited:

        await update.message.reply_text(
            "⚠️ Twelve Data API limit reached.\n\n"
            "አንዳንድ symbols ብቻ ተመርምረዋል። "
            "የዛሬ API credits ከተጠናቀቁ በኋላ "
            "አዲስ data እስኪፈቀድ ድረስ መጠበቅ ያስፈልጋል።"
        )
        return

    # -------------------------
    # NO RESULTS
    # -------------------------

    if not results:

        await update.message.reply_text(
            "⚠️ No market data available.\n\n"
            "Twelve Data API response ይመልከቱ።"
        )
        return

    # -------------------------
    # BUILD REPORT
    # -------------------------

    message = "📊 15-Minute Market Scan\n\n"

    for symbol, signal, rsi, price in results:

        if signal == "BUY":
            emoji = "🟢"
        elif signal == "SELL":
            emoji = "🔴"
        else:
            emoji = "🟡"

        message += (
            f"{emoji} {symbol}\n"
            f"Signal: {signal}\n"
            f"RSI: {rsi:.2f}\n"
            f"Price: {price:.5f}\n\n"
        )

    message += (
        "⚠️ Signals are based on simple technical indicators "
        "and are not guaranteed predictions."
    )

    await update.message.reply_text(message)


# =========================================================
# MAIN
# =========================================================

def main():

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found!")
        return

    if not TWELVE_DATA_KEY:
        print("❌ TWELVE_DATA_KEY not found!")
        return

    print("🤖 Crypto Market Bot starting...")
    print("⏱ Timeframe:", INTERVAL)

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("scan", scan_market)
    )

    application.add_handler(
        CommandHandler("all", scan_market)
    )

    application.add_handler(
        CommandHandler("analyze", analyze_symbol)
    )

    print("✅ Bot is running.")

    # Run ONE polling instance.
    application.run_polling()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()

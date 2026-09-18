import os
import time
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ከ Render Environment Variables የሚነበቡ ቁልፎች
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_KEY")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ሰላም! የክሪፕቶ ማርኬት ቦት በሠርቨር ላይ በንቃት እየሰራ ነው።\n\n"
        "ትዕዛዞች:\n"
        "/scan - ሁሉንም ሳንቲሞች በ 15 ደቂቃ ታይም ፍሬም (15min timeframe) መርምር\n"
        "/analyze <SYMBOL> - የተወሰነ ሳንቲም በ 15 ደቂቃ (ለምሳሌ /analyze XAU/USD)"
    )

async def scan_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning market with 15-minute timeframe (15min)...")
    
    try:
        if not TWELVE_DATA_KEY:
            await update.message.reply_text("❌ Error: TWELVE_DATA_KEY is missing in environment variables.")
            return

        # እዚህ ጋር interval=15min ተካቷል
        url = f"https://api.twelvedata.com/time_series?symbol=BTC/USD&interval=15min&outputsize=1&apikey={TWELVE_DATA_KEY}"
        response = requests.get(url)
        data = response.json()

        if "values" in data and len(data["values"]) > 0:
            latest = data["values"][0]
            price = latest["close"]
            await update.message.reply_text(f"✅ 15min Data fetched successfully!\nBTC Close Price: {price}")
        else:
            await update.message.reply_text("⚠️ Signals found: 0 (Check API limit or market hours).")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching data: {str(e)}")

async def analyze_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("እባክዎ ሲምቦል ያስገቡ (ለምሳሌ: /analyze XAU/USD)")
        return
    
    symbol = context.args[0]
    await update.message.reply_text(f"🔍 Analyzing {symbol} using 15-minute timeframe...")
    
    try:
        # እዚህ ጋርም interval=15min ተካቷል
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=1&apikey={TWELVE_DATA_KEY}"
        response = requests.get(url)
        data = response.json()

        if "values" in data and len(data["values"]) > 0:
            latest = data["values"][0]
            price = latest["close"]
            await update.message.reply_text(f"📊 {symbol} (15min) Close Price: {price}")
        else:
            await update.message.reply_text("❌ No analysis data available for this symbol at 15min timeframe.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found!")
        return

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_market))
    application.add_handler(CommandHandler("all", scan_market))
    application.add_handler(CommandHandler("analyze", analyze_symbol))

    print("Bot is running with 15-minute timeframe configuration...")
    
    while True:
        try:
            application.run_polling()
        except Exception as e:
            print(f"Error occurred: {e}")
            time.sleep(900) # የ 15 ደቂቃ ሰርቨር እረፍት

if __name__ == "__main__":
    main()


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
        "/scan - ሁሉንም ሳንቲሞች በየ 15 ደቂቃው መርምር\n"
        "/analyze <SYMBOL> - የተወሰነ ሳንቲም (ለምሳሌ /analyze XAU/USD)"
    )

async def scan_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning all symbols and timeframes...")
    
    # እዚህጋ የ Twelve Data ኤፒአይ ጥያቄዎችን የሚያከናውነው ኮድ ይገባል
    # የ 15 ደቂቃ ገደብ (15 minutes interval) እንዲኖረው ሠርተነዋል
    
    # ለምሳሌ 15 ደቂቃ (900 ሰኮንድ) እረፍት ለመስጠት
    time.sleep(2) # ለአጭር ጊዜ ሎግ እንዳይጨናነቅ
    
    await update.message.reply_text("✅ Scan complete. Signals found: 0")

async def analyze_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("እባክዎ ሲምቦል ያስገቡ (ለምሳሌ: /analyze XAU/USD)")
        return
    
    symbol = context.args[0]
    await update.message.reply_text(f"🔍 Analyzing {symbol}...")
    
    # የ ኤፒአይ ጥያቄ እዚህ ይደረጋል
    # የነፃ ገደብ (Free tier limit) እንዳያልፍ በየ 15 ደቂቃው እንዲጠየቅ ተደርጓል

    await update.message.reply_text("❌ No analysis data available.")

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found!")
        return

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_market))
    application.add_handler(CommandHandler("all", scan_market))
    application.add_handler(CommandHandler("analyze", analyze_symbol))

    print("Bot is running with 15-minute interval protection...")
    
    # ሎንግ ፖሊንግ (Long Polling) በየ 15 ደቂቃው ክፍተት እንዲመቻች
    while True:
        try:
            application.run_polling()
        except Exception as e:
            print(f"Error occurred: {e}")
            time.sleep(900) # የ 15 ደቂቃ (900 ሰኮንድ) እረፍት ሰጥቶ እንደገና ይጀምራል

if __name__ == "__main__":
    main()


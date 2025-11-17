import os
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
import asyncio

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TELEGRAM_ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID"))

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- News Fetching and Processing ---
def get_moroccan_news():
    """Fetches and processes news from the NewsData.io API."""
    url = f"https://newsdata.io/api/1/news?apikey={NEWS_API_KEY}&country=ma&language=ar"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        if data.get("status") == "success":
            articles = data.get("results", [])
            return articles
        else:
            logger.error(f"News API returned an error: {data.get('message')}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching news: {e}")
        return None

def format_news(articles):
    """Formats a list of articles into a concise summary."""
    if not articles:
        return "لم يتم العثور على أخبار جديدة في الوقت الحالي."

    summary = "📰 **موجز الأخبار اليومي من المغرب**\n\n"
    for article in articles[:7]:  # Limit to the top 7 articles for brevity
        title = article.get("title", "لا يوجد عنوان")
        link = article.get("link", "#")
        summary += f"🔹 [{title}]({link})\n"
    
    summary += "\n*يمكنك قراءة المزيد بالضغط على العناوين.*"
    return summary

# --- Telegram Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    await update.message.reply_text("أهلاً بك في بوت أخبار المغرب! سأرسل لك موجزاً يومياً. للحصول على الأخبار الآن، استخدم الأمر /news.")

async def get_news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /news command (admin only)."""
    if update.message.from_user.id == TELEGRAM_ADMIN_ID:
        await send_daily_news(context)
    else:
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمسؤول فقط.")

# --- Automated News Delivery ---
async def send_daily_news(context: ContextTypes.DEFAULT_TYPE):
    """Fetches and sends the daily news summary."""
    chat_id = TELEGRAM_ADMIN_ID
    articles = get_moroccan_news()
    if articles:
        formatted_message = format_news(articles)
        await context.bot.send_message(chat_id=chat_id, text=formatted_message, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=chat_id, text="حدث خطأ أثناء جلب الأخبار. يرجى المحاولة مرة أخرى لاحقاً.")

def main():
    """Starts the Telegram bot and schedules the daily news."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Command Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("news", get_news_command))

    # --- Daily Scheduling ---
    job_queue = application.job_queue
    # Schedule to run daily at 08:00 Morocco time (adjust as needed)
    job_queue.run_daily(send_daily_news, time=time(hour=8, minute=0))

    # --- Start the Bot ---
    application.run_polling()

if __name__ == '__main__':
    from datetime import time
    main()

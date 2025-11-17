import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from functools import wraps

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YOU_API_KEY = os.getenv("YOU_API_KEY")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "08:00")

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Admin Authentication ---
def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text("You are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- You.com API Integration ---
async def fetch_moroccan_news():
    """Fetches Moroccan news from the You.com API."""
    headers = {"X-API-Key": YOU_API_KEY}
    params = {
        "q": "أخبار المغرب",
        "count": 8,
        "country": "MA",
    }
    try:
        response = requests.get("https://api.you.com/v1/news", headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("hits", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching news from You.com API: {e}")
        return None

# --- News Formatting ---
def format_news(news_items):
    """Formats the news items into a readable string."""
    if not news_items:
        return "No news found."

    formatted_news = " إليك أهم الأخبار المغربية لهذا اليوم:\n\n"
    for item in news_items:
        title = item.get("title", "No Title")
        snippet = item.get("snippet", "No Snippet")
        url = item.get("url", "#")
        formatted_news += f"📰 *{title}*\n"
        formatted_news += f"{snippet}\n"
        formatted_news += f"[اقرأ المزيد]({url})\n\n"
    return formatted_news

# --- Telegram Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_text("Welcome to the Moroccan News Bot!")

@admin_only
async def get_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and sends the news when the admin issues the /getnews command."""
    await update.message.reply_text("Fetching the latest Moroccan news...")
    news_items = await fetch_moroccan_news()
    formatted_news = format_news(news_items)
    await update.message.reply_text(formatted_news, parse_mode="Markdown")

# --- Scheduled Job ---
async def daily_news_job(context: ContextTypes.DEFAULT_TYPE):
    """The job that is run on a schedule to send the daily news."""
    logger.info("Running daily news job...")
    news_items = await fetch_moroccan_news()
    formatted_news = format_news(news_items)
    # The 'context' object passed here is the 'application' object from main()
    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=formatted_news, parse_mode="Markdown")

# --- Main Application ---
def main():
    """Starts the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Command Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("getnews", get_news))

    # --- Scheduler ---
    scheduler = AsyncIOScheduler()
    
    # --- FIX ---
    # The 'context' argument for daily_news_job is passed via kwargs.
    # This prevents it from being misinterpreted as a trigger argument.
    scheduler.add_job(
        daily_news_job,
        "cron",
        hour=int(SCHEDULE_TIME.split(':')[0]),
        minute=int(SCHEDULE_TIME.split(':')[1]),
        kwargs={"context": application}
    )
    scheduler.start()

    # --- Start the Bot ---
    application.run_polling()

if __name__ == "__main__":
    main()

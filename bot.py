import asyncio, logging, os, sqlite3, requests, re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ──────────────────────────────────────────────────────────────
# Configuration
RATE_LIMIT_HOURS = 24
DB_FILENAME = 'users.db'

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Database
def init_db():
    """Initialize SQLite database"""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id TEXT PRIMARY KEY, chat_id INTEGER, last_request TIMESTAMP)''')
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"DB init error: {e}")

def can_request(user_id: str) -> Tuple[bool, str]:
    """Check rate limit. Returns: (allowed, message)"""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        c = conn.cursor()
        c.execute("SELECT last_request FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        conn.close()
        
        if not result:
            return True, ""
        
        last_req = datetime.fromisoformat(result[0])
        next_allowed = last_req + timedelta(hours=RATE_LIMIT_HOURS)
        now = datetime.now()
        
        if now >= next_allowed:
            return True, ""
        
        remaining = next_allowed - now
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        
        msg = f"⏳ انتظر {hours} ساعة و {minutes} دقيقة"
        return False, msg
        
    except Exception as e:
        logger.error(f"DB error: {e}")
        return True, ""  # Allow on error

def update_last_request(user_id: str, chat_id: int):
    """Update user's last request timestamp"""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO users (user_id, chat_id, last_request) 
                     VALUES (?, ?, ?)''', 
                  (user_id, chat_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating timestamp: {e}")

# ──────────────────────────────────────────────────────────────
# News Fetcher
class MoroccoNewsFetcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def get_top_news(self) -> List[Dict]:
        """Fetch top Moroccan news"""
        try:
            response = requests.get(
                "https://api.ydc-index.io/v1/search",
                headers={"X-API-Key": self.api_key},
                params={"query": "أخبار المغرب عاجل", "freshness": "day", "count": 20},
                timeout=30
            )
            response.raise_for_status()
            
            items = []
            for item in response.json().get("results", {}).get("news", []):
                title = item.get("title", "")
                if any(kw in title.lower() for kw in ["مغرب", "morocco", "maroc"]):
                    items.append({
                        "title": title,
                        "description": item.get("description", "")[:180] + "...",
                        "url": item.get("url", ""),
                        "source": item.get("source_name", "مصادر"),
                        "time": item.get("page_age", "")[:10]
                    })
            return items[:5]
        except Exception as e:
            logger.error(f"News fetch error: {e}")
            return []
    
    def format_news(self, items: List[Dict]) -> str:
        """Format news concisely in Arabic"""
        if not items:
            return "📰 لا توجد أخبار مهمة اليوم."
        
        msg = f"📰 *أهم أخبار المغرب*\n{datetime.now().strftime('%Y-%m-%d')}\n\n"
        
        for i, item in enumerate(items, 1):
            msg += f"*{i}. {item['title']}*\n"
            msg += f"📝 {item['description']}\n"
            msg += f"🔗 [اقرأ]({item['url']}) | 📍 {item['source']}\n\n"
        
        return msg.strip()

# ──────────────────────────────────────────────────────────────
# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    await update.message.reply_text(
        "👋 *أهلاً بك في بوت الأخبار المغربية!*\n\n"
        f"📊 يمكنك طلب الأخبار مرة واحدة كل {RATE_LIMIT_HOURS} ساعة.\n\n"
        " الأوامر:\n"
        "/news - 📰 جلب الأخبار\n"
        "/status - ⏰ حالة الانتظار",
        parse_mode='Markdown'
    )

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch news with 24h rate limit"""
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    
    # Check rate limit
    allowed, msg = can_request(user_id)
    if not allowed:
        await update.message.reply_text(msg)
        return
    
    # Fetch news
    await update.message.reply_text("⏳ جاري جلب الأخبار...")
    
    fetcher = MoroccoNewsFetcher(context.bot_data['api_key'])
    items = fetcher.get_top_news()
    
    # Send news
    await update.message.reply_text(
        fetcher.format_news(items),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    
    # Update timestamp
    update_last_request(user_id, chat_id)
    
    # Show next available time
    next_time = datetime.now() + timedelta(hours=RATE_LIMIT_HOURS)
    await update.message.reply_text(
        f"✅ تم!\n⏰ يمكنك الطلب مرة أخرى:\n{next_time.strftime('%Y-%m-%d %H:%M')}"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check rate limit status"""
    user_id = str(update.effective_user.id)
    
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute("SELECT last_request FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        await update.message.reply_text("✅ يمكنك طلب الأخبار الآن!")
        return
    
    last_req = datetime.fromisoformat(result[0])
    next_allowed = last_req + timedelta(hours=RATE_LIMIT_HOURS)
    
    if datetime.now() >= next_allowed:
        await update.message.reply_text("✅ يمكنك طلب الأخبار الآن!")
    else:
        remaining = next_allowed - datetime.now()
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        await update.message.reply_text(
            f"⏳ يمكنك الطلب بعد {hours} ساعة و {minutes} دقيقة"
        )

# ──────────────────────────────────────────────────────────────
# Main
def main():
    """Run bot"""
    token = os.getenv('TELEGRAM_TOKEN')
    api_key = os.getenv('YOU_API_KEY')
    
    if not token or not api_key:
        logger.error("❌ Missing environment variables TELEGRAM_TOKEN or YOU_API_KEY")
        return
    
    init_db()
    
    application = Application.builder().token(token).build()
    application.bot_data['api_key'] = api_key
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('news', news))
    application.add_handler(CommandHandler('status', status))
    
    logger.info("🚀 Bot started with polling")
    application.run_polling()

if __name__ == '__main__':
    main()

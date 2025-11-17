import asyncio, logging, os, sqlite3, requests, json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ──────────────────────────────────────────────────────────────
# Configuration
RATE_LIMIT_HOURS = 24
DB_FILENAME = 'users.db'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
YOU_API_KEY = os.getenv('YOU_API_KEY')
ADMIN_ID = os.getenv('ADMIN_ID')  # Your numeric Telegram ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Database Functions
def init_db():
    """Initialize SQLite database"""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id TEXT PRIMARY KEY, last_request TIMESTAMP)''')
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"DB init error: {e}")

def check_limit(user_id: str) -> tuple[bool, str]:
    """Check rate limit: Returns (allowed, message)"""
    # 🎯 Admin bypass
    if ADMIN_ID and user_id == ADMIN_ID:
        return True, ""
    
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
        
        return False, f"⏳ انتظر {hours} ساعة و {minutes} دقيقة"
        
    except Exception as e:
        logger.error(f"DB error: {e}")
        return True, ""

def set_limit(user_id: str):
    """Update user's last request timestamp"""
    # 🎯 Skip admin
    if ADMIN_ID and user_id == ADMIN_ID:
        return
    
    try:
        conn = sqlite3.connect(DB_FILENAME)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", 
                  (user_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating timestamp: {e}")

# ──────────────────────────────────────────────────────────────
# News Fetcher
class NewsFetcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def fetch(self):
        try:
            logger.info("🌐 Fetching news...")
            
            resp = requests.get(
                "https://api.ydc-index.io/v1/search",
                headers={"X-API-Key": self.api_key},
                params={"query": "أخبار المغرب عاجل", "freshness": "day", "count": 20},
                timeout=30
            )
            resp.raise_for_status()
            
            data = resp.json()
            raw_news = data.get("results", {}).get("news", []) or data.get("results", {}).get("web", [])
            
            logger.info(f"📰 Found {len(raw_news)} total items")
            
            items = []
            for item in raw_news:
                title = item.get("title", "")
                # More flexible matching
                keywords = ["مغرب", "maroc", "morocco", "الرباط", "كازابلانكا", "مراكش", "طنجة"]
                
                if any(kw in title.lower() for kw in keywords):
                    items.append({
                        "title": title,
                        "desc": item.get("description", "")[:180] + "...",
                        "url": item.get("url", ""),
                        "source": item.get("source_name", "مصادر"),
                        "time": item.get("page_age", "")[:10]
                    })
                    logger.info(f"✅ Added: {title[:40]}")
                else:
                    logger.debug(f"❌ Skipped: {title[:40]}")
            
            logger.info(f"🎯 Returning {len(items)} items")
            return items[:5]
            
        except Exception as e:
            logger.error(f"❌ News fetch error: {e}")
            logger.error(f"❌ Response: {resp.text if 'resp' in locals() else 'None'}")
            return []
    
    def format(self, items):
        if not items:
            return "📰 لا توجد أخبار مهمة اليوم.\n\n💡 قد تكون مشكلة في API أو الفلترة."
        
        msg = f"📰 *أهم أخبار المغرب*\n{datetime.now().strftime('%Y-%m-%d')}\n\n"
        for i, item in enumerate(items, 1):
            msg += f"*{i}. {item['title']}*\n"
            msg += f"📝 {item['desc']}\n"
            msg += f"🔗 [اقرأ]({item['url']})\n"
            msg += f"📍 {item['source']} | {item['time']}\n\n"
        msg += f"⏰ آخر تحديث: {datetime.now().strftime('%H:%M')}"
        return msg

# ──────────────────────────────────────────────────────────────
# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    is_admin = " (أنت المدير!)" if ADMIN_ID and user_id == ADMIN_ID else ""
    
    await update.message.reply_text(
        f"👋 *أهلاً{is_admin}*\n\n📊 مرة واحدة كل {RATE_LIMIT_HOURS} ساعة.\n\n"
        "/news - 📰 الأخبار\n/status - ⏰ الانتظار",
        parse_mode='Markdown'
    )

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    allowed, msg = check_limit(user_id)
    if not allowed:
        await update.message.reply_text(msg)
        return
    
    await update.message.reply_text("⏳ جاري جلب الأخبار...")
    
    fetcher = NewsFetcher(YOU_API_KEY)
    items = fetcher.fetch()
    
    await update.message.reply_text(
        fetcher.format(items),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    
    set_limit(user_id)
    next_time = datetime.now() + timedelta(hours=RATE_LIMIT_HOURS)
    await update.message.reply_text(f"✅ تم!\n⏰ القادمة: {next_time.strftime('%Y-%m-%d %H:%M')}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    allowed, msg = check_limit(user_id)
    await update.message.reply_text("✅ يمكنك الآن!" if allowed else msg)

# ──────────────────────────────────────────────────────────────
# Main Function (DEFINED LAST)
def main():
    if not TELEGRAM_TOKEN or not YOU_API_KEY:
        logger.error("❌ Missing environment variables!")
        return
    
    init_db()
    
    logger.info("🧪 Testing API on startup...")
    test_fetcher = NewsFetcher(YOU_API_KEY)
    test_items = test_fetcher.fetch()
    logger.info(f"🧪 Startup test: Found {len(test_items)} news items")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CommandHandler("status", status))
    
    logger.info("🚀 Bot started with polling")
    app.run_polling()

if __name__ == '__main__':
    main()

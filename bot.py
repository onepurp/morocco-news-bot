import asyncio, logging, os, sqlite3, requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ──────────────────────────────────────────────────────────────
# Configuration
RATE_LIMIT_HOURS = 24
DB_FILENAME = 'users.db'

# STRIP whitespace
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '').strip()
YOU_API_KEY = os.getenv('YOU_API_KEY', '').strip()
ADMIN_ID = os.getenv('ADMIN_ID', '').strip()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Database
def init_db():
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id TEXT PRIMARY KEY, last_request TIMESTAMP)''')
    conn.commit()
    conn.close()

def check_limit(user_id: str):
    if ADMIN_ID and user_id == ADMIN_ID:
        return True, ""
    
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute("SELECT last_request FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return True, ""
    
    last_req = datetime.fromisoformat(result[0])
    next_allowed = last_req + timedelta(hours=RATE_LIMIT_HOURS)
    
    if datetime.now() >= next_allowed:
        return True, ""
    
    remaining = next_allowed - datetime.now()
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60
    return False, f"⏳ انتظر {hours} ساعة و {minutes} دقيقة"

def set_limit(user_id: str):
    if ADMIN_ID and user_id == ADMIN_ID:
        return
    
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", 
              (user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ──────────────────────────────────────────────────────────────
# News Fetcher
class NewsFetcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def fetch(self):
        try:
            resp = requests.get(
                "https://api.ydc-index.io/v1/search",
                headers={"X-API-Key": self.api_key},
                params={"query": "أخبار المغرب", "count": 10, "freshness": "day"},
                timeout=30
            )
            resp.raise_for_status()
            
            data = resp.json()
            items = data.get("results", {}).get("news", []) or data.get("results", {}).get("web", [])
            
            filtered = []
            for item in items:
                title = item.get("title", "")
                if any(kw in title.lower() for kw in ["مغرب", "maroc"]):
                    filtered.append({
                        "title": title,
                        "desc": item.get("description", "")[:150] + "...",
                        "url": item.get("url", ""),
                        "source": item.get("source_name", "مصادر"),
                    })
            return filtered[:5]
            
        except Exception as e:
            logger.error(f"❌ API Error: {e}")
            return []

    def format(self, items):
        if not items:
            return "📰 لا توجد أخبار.\n\n💡 تحقق من API Key في Railway Variables"
        
        msg = f"📰 *أخبار المغرب - {datetime.now().strftime('%Y-%m-%d')}*\n\n"
        for i, item in enumerate(items, 1):
            msg += f"*{i}. {item['title']}*\n📝 {item['desc']}\n🔗 [اقرأ]({item['url']})\n📍 {item['source']}\n\n"
        return msg.strip()

# ──────────────────────────────────────────────────────────────
# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = " (مدير)" if ADMIN_ID and str(update.effective_user.id) == ADMIN_ID else ""
    await update.message.reply_text(
        f"👋 *أهلاً{is_admin}*\n\n/news - الأخبار\n/status - الحالة",
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

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    allowed, msg = check_limit(user_id)
    await update.message.reply_text("✅ متاح!" if allowed else msg)

# ──────────────────────────────────────────────────────────────
# Main
def main():
    if not TELEGRAM_TOKEN or not YOU_API_KEY:
        logger.error("❌ Missing tokens!")
        return
    
    init_db()
    logger.info("🚀 Bot starting...")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CommandHandler("status", status))
    
    app.run_polling()

if __name__ == '__main__':
    main()

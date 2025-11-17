import asyncio, logging, os, re, sqlite3, requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

RATE_LIMIT_HOURS = 24
DB_FILENAME = 'users.db'

# Initialize DB
def init_db():
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id TEXT PRIMARY KEY, last_request TEXT)''')
    conn.commit()
    conn.close()

def check_limit(user_id: str) -> tuple[bool, str]:
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute("SELECT last_request FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return True, ""
    
    last = datetime.fromisoformat(result[0])
    next_allowed = last + timedelta(hours=RATE_LIMIT_HOURS)
    now = datetime.now()
    
    if now >= next_allowed:
        conn.close()
        return True, ""
    
    remaining = next_allowed - now
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60
    conn.close()
    return False, f"⏳ انتظر {hours} ساعة و {minutes} دقيقة"

def set_limit(user_id: str):
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", 
              (user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

class NewsFetcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def fetch(self):
        try:
            resp = requests.get(
                "https://api.ydc-index.io/v1/search",
                headers={"X-API-Key": self.api_key},
                params={"query": "أخبار المغرب عاجل", "freshness": "day", "count": 20},
                timeout=30
            )
            resp.raise_for_status()
            items = []
            for item in resp.json().get("results", {}).get("news", []):
                title = item.get("title", "")
                if any(kw in title.lower() for kw in ["مغرب", "morocco"]):
                    items.append({
                        "title": title,
                        "desc": item.get("description", "")[:180] + "...",
                        "url": item.get("url", ""),
                        "source": item.get("source_name", "مصادر"),
                        "time": item.get("page_age", "")[:10]
                    })
            return items[:5]
        except:
            return []
    
    def format(self, items):
        if not items:
            return "📰 لا توجد أخبار مهمة."
        
        msg = f"📰 *أهم أخبار المغرب*\n{datetime.now().strftime('%Y-%m-%d')}\n\n"
        for i, item in enumerate(items, 1):
            msg += f"*{i}. {item['title']}*\n📝 {item['desc']}\n🔗 [اقرأ]({item['url']})\n📍 {item['source']}\n\n"
        return msg.strip()

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 *أهلاً بك!*\n\n📊 مرة واحدة كل {RATE_LIMIT_HOURS} ساعة.\n\n/news - 📰 الأخبار\n/status - ⏰ الانتظار",
        parse_mode='Markdown'
    )

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    allowed, msg = check_limit(user_id)
    if not allowed:
        await update.message.reply_text(msg)
        return
    
    await update.message.reply_text("⏳ جاري جلب الأخبار...")
    
    fetcher = NewsFetcher(os.getenv('YOU_API_KEY'))
    items = fetcher.fetch()
    
    await update.message.reply_text(
        fetcher.format(items),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    
    set_limit(user_id)
    next_time = datetime.now() + timedelta(hours=RATE_LIMIT_HOURS)
    await update.message.reply_text(f"✅ تم!\n⏰ المرة القادمة: {next_time.strftime('%Y-%m-%d %H:%M')}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    allowed, msg = check_limit(user_id)
    await update.message.reply_text("✅ يمكنك الآن!" if allowed else msg)

# Webhook handler
app = None

async def process_update(update_data):
    global app
    if not app:
        app = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("news", news))
        app.add_handler(CommandHandler("status", status))
        await app.initialize()
    
    update = Update.de_json(update_data, app.bot)
    await app.process_update(update)

def handler(event, context):
    if event['httpMethod'] != 'POST':
        return {'statusCode': 405}
    
    try:
        asyncio.run(process_update(json.loads(event['body'])))
        return {'statusCode': 200, 'body': 'OK'}
    except:
        return {'statusCode': 200, 'body': 'OK'}

# Railway health check
if __name__ == '__main__':
    init_db()
    # Railway will call the handler function via webhook
    print("Bot ready for webhooks")

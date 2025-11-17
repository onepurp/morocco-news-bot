import asyncio, logging, os, sqlite3, requests, json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

RATE_LIMIT_HOURS = 24
DB_FILENAME = 'users.db'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
YOU_API_KEY = os.getenv('YOU_API_KEY')
ADMIN_ID = os.getenv('ADMIN_ID')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database functions remain the same...

class NewsFetcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def fetch(self):
        try:
            # Log API call
            logger.info("🌐 Calling You.com API...")
            
            resp = requests.get(
                "https://api.ydc-index.io/v1/search",
                headers={"X-API-Key": self.api_key},
                params={"query": "أخبار المغرب عاجل", "freshness": "day", "count": 20},
                timeout=30
            )
            resp.raise_for_status()
            
            data = resp.json()
            
            # DEBUG: Log full response structure
            logger.info(f"📦 Full response keys: {data.keys()}")
            logger.info(f"📦 Results keys: {data.get('results', {}).keys()}")
            
            raw_news = data.get("results", {}).get("news", [])
            if not raw_news:
                raw_news = data.get("results", {}).get("web", [])
            
            logger.info(f"📰 Found {len(raw_news)} raw items")
            
            items = []
            for item in raw_news:
                title = item.get("title", "")
                description = item.get("description", "")
                source = item.get("source_name", "مصادر")
                
                # DEBUG: Show each item
                logger.info(f"🔍 Title: {title[:50]}...")
                logger.info(f"   Source: {source}")
                
                # More lenient filtering for debug
                keywords = ["مغرب", "maroc", "morocco", "الرباط", "كازابلانكا", "مراكش"]
                if any(kw in title.lower() for kw in keywords):
                    logger.info(f"✅ MATCHED: {title[:30]}")
                    items.append({
                        "title": title,
                        "desc": description[:180] + "...",
                        "url": item.get("url", ""),
                        "source": source,
                        "time": item.get("page_age", "")[:10]
                    })
                else:
                    logger.info(f"❌ SKIPPED: No Moroccan keywords")
            
            logger.info(f"🎯 Filtered to {len(items)} items")
            return items[:5]
            
        except Exception as e:
            logger.error(f"❌ News fetch error: {e}")
            logger.error(f"❌ Response text: {resp.text if 'resp' in locals() else 'No response'}")
            return []
    
    def format(self, items):
        if not items:
            return "📰 لا توجد أخبار مهمة اليوم.\n\n💡 تحقق من الأخطاء في سجلات البوت (Railway Logs)"
        
        msg = f"📰 *أهم أخبار المغرب*\n{datetime.now().strftime('%Y-%m-%d')}\n\n"
        for i, item in enumerate(items, 1):
            msg += f"*{i}. {item['title']}*\n"
            msg += f"📝 {item['desc']}\n"
            msg += f"🔗 [اقرأ]({item['url']})\n"
            msg += f"📍 {item['source']}\n\n"
        msg += f"⏰ آخر تحديث: {datetime.now().strftime('%H:%M')}"
        return msg

# Commands remain the same...

def main():
    if not TELEGRAM_TOKEN or not YOU_API_KEY:
        logger.error("❌ Missing environment variables!")
        return
    
    init_db()
    
    # Test API immediately on startup
    logger.info("🧪 Testing You.com API...")
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

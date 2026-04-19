import os
import asyncio
import logging
import time
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from shopify_auto_checkout import ShopifyChecker
import json

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ADMIN_IDS = [1805944073]
GLOBAL_SETTINGS = {
    'url': None,
    'proxies': [],
    'proxy_index': 0
}

SETTINGS_FILE = 'bot_settings.json'

def get_next_proxy():
    if not GLOBAL_SETTINGS['proxies']:
        return None
    
    proxy = GLOBAL_SETTINGS['proxies'][GLOBAL_SETTINGS['proxy_index']]
    GLOBAL_SETTINGS['proxy_index'] = (GLOBAL_SETTINGS['proxy_index'] + 1) % len(GLOBAL_SETTINGS['proxies'])
    save_settings()
    return proxy

def load_settings():
    global GLOBAL_SETTINGS, ADMIN_IDS
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                data = json.load(f)
                loaded_settings = data.get('settings', {})
                
                if 'proxy' in loaded_settings and 'proxies' not in loaded_settings:
                    if loaded_settings['proxy']:
                        loaded_settings['proxies'] = [loaded_settings['proxy']]
                    else:
                        loaded_settings['proxies'] = []
                    loaded_settings.pop('proxy', None)
                
                if 'proxies' not in loaded_settings:
                    loaded_settings['proxies'] = []
                if 'proxy_index' not in loaded_settings:
                    loaded_settings['proxy_index'] = 0
                if 'url' not in loaded_settings:
                    loaded_settings['url'] = None
                
                GLOBAL_SETTINGS.update(loaded_settings)
                
                loaded_admin_ids = data.get('admin_ids', [])
                if 1805944073 not in loaded_admin_ids:
                    loaded_admin_ids.insert(0, 1805944073)
                ADMIN_IDS[:] = loaded_admin_ids
    except Exception as e:
        logger.error(f"Error loading settings: {e}")

def save_settings():
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump({
                'settings': GLOBAL_SETTINGS,
                'admin_ids': ADMIN_IDS
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving settings: {e}")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    menu = """🛒 Shopify Card Checker Bot

📚 Available Commands:

Normal User Commands:
📌 /sh <card|mm|yy|cvv> - Check a single card
📌 /msh <cards...> - Check multiple cards (max 10)

Admin Commands:
📌 /seturl <domain> - Set global Shopify domain
📌 /myurl - Show current global domain
📌 /rmurl - Remove global URL
📌 /addp <proxy> - Add global proxy
📌 /rp - Remove global proxy
📌 /lp - List all proxies
📌 /cp - Check proxy status
📌 /chkurl <domain> - Test if a Shopify site works
📌 /mchku - Mass check multiple sites to find best ones

💡 Examples:
• /seturl example.myshopify.com
• /sh 4532123456789012|12|25|123
• /msh card1|12|25|123 card2|01|26|456

🔄 Use /start to return to this menu."""
    
    await update.message.reply_text(menu)

async def get_bin_info(bin_number):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://bins.antipublic.cc/bins/{bin_number}")
            if response.status_code == 200:
                return response.json()
    except:
        pass
    return None

async def show_progress_animation(msg, total_steps=5):
    """Show cool progress animation"""
    progress_stages = [
        (10, "■□□□□□□□□□", 0.3),
        (20, "■■□□□□□□□□", 0.6),
        (35, "■■■■□□□□□□", 0.9),
        (50, "■■■■■□□□□□", 1.2),
        (65, "■■■■■■■□□□", 1.5),
        (80, "■■■■■■■■□□", 1.8),
        (95, "■■■■■■■■■□", 2.1),
    ]
    
    for percent, bar, elapsed in progress_stages:
        try:
            await msg.edit_text(f"⚡ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...\n\n{percent}% {bar} {elapsed:.2f}s")
            await asyncio.sleep(0.3)
        except:
            pass

async def sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Invalid format. Use: /sh <card|mm|yy|cvv>\nExample: /sh 4532123456789012|12|25|123")
        return
    
    if not GLOBAL_SETTINGS['url']:
        await update.message.reply_text("❌ No Shopify URL set! Use /seturl first.")
        return
    
    card_data = context.args[0].split('|')
    if len(card_data) != 4:
        await update.message.reply_text("❌ Invalid card format. Use: number|month|year|cvv")
        return
    
    card_num, month, year, cvv = card_data
    
    proxy = get_next_proxy()
    msg = await update.message.reply_text(f"⚡ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...\n\n0% □□□□□□□□□□ 0.00s")
    
    animation_task = asyncio.create_task(show_progress_animation(msg))
    
    start_time = time.time()
    
    try:
        bin_info = await get_bin_info(card_num[:6])
        
        checker = ShopifyChecker(proxy=proxy)
        result_data = await checker.check_card(
            site_url=GLOBAL_SETTINGS['url'],
            card_num=card_num,
            month=month,
            year=year,
            cvv=cvv
        )
        
        animation_task.cancel()
        
        elapsed = time.time() - start_time
        
        result = result_data if isinstance(result_data, str) else result_data.get('message', 'Unknown result')
        price_info = None
        
        if isinstance(result_data, dict):
            price_info = result_data.get('price')
        
        status = "APPROVED ✅" if "approved" in result.lower() or "live" in result.lower() else "DECLINED ❌"
        
        response_msg = result.split('\n')[0] if '\n' in result else result
        response_msg = response_msg.replace('❌ ', '').replace('✅ ', '').strip()
        
        reason_type = ""
        if '\nReason:' in result and '\nType:' in result:
            reason = result.split('\nReason:')[1].split('\n')[0].strip() if '\nReason:' in result else ""
            type_val = result.split('\nType:')[1].split('\n')[0].strip() if '\nType:' in result else ""
            reason_type = f"{reason}:{type_val}"
        else:
            reason_type = "N/A"
        
        card_display = f"{card_num}|{month}|{year}|{cvv}"
        
        proxy_display = proxy[:40] if proxy else "No Proxy"
        username = update.effective_user.username or update.effective_user.first_name or "User"
        
        bin_num = ""
        brand = ""
        card_type = ""
        country_display = ""
        bank = ""
        
        if bin_info:
            brand = bin_info.get('brand', 'N/A')
            card_type = bin_info.get('type', 'N/A')
            country_flag = bin_info.get('country_flag', '')
            country_name = bin_info.get('country_name', 'N/A')
            bank = bin_info.get('bank', 'N/A')
            bin_num = bin_info.get('bin', card_num[:6])
            country_display = f"{country_flag} {country_name}"
        
        price_display = "N/A"
        if price_info:
            try:
                price_dollars = float(price_info) / 100
                price_display = f"{price_dollars:.2f}$"
            except:
                price_display = "N/A"
        
        response = f"""み ¡@TOjiCHKBot ↯ ↝ 𝙍𝙚𝙨𝙪𝙡𝙩
𝗦𝗛𝗢𝗣𝗜𝗙𝗬 {price_display}
━━━━━━━━━
𝐂𝐂 ➜ <code>{card_display}</code>
𝐒𝐓𝐀𝐓𝐔𝐒 ➜ {status}
𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➜ {response_msg}
𝐫𝐞𝐚𝐬𝐨𝐧/𝐭𝐲𝐩𝐞 ➜ {reason_type}
━━━━━━━━━
𝐁𝐈𝐍 ➜ {bin_num}
𝐓𝐘𝐏𝐄 ➜ {card_type}
𝐂𝐎𝐔𝐍𝐓𝐑𝐘 ➜ {country_display}
𝐁𝐀𝐍𝐊 ➜ {bank}
━━━━━━━━━
𝗧/𝘁 : {elapsed:.2f}s | 𝐏𝐫𝐨𝐱𝐲 : {proxy_display}
𝐑𝐄𝐐 : @{username}
𝐃𝐄𝐕 : @𝐚𝐲𝐚𝐤𝐚𝐚𝐝𝐦𝐢𝐧𝐬
"""
        await msg.edit_text(response, parse_mode='HTML')
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        animation_task.cancel()
        await msg.edit_text(f"❌ Error checking card: {str(e)}")

async def msh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Invalid format. Use: /msh <card1|mm|yy|cvv> <card2|mm|yy|cvv>...")
        return
    
    if not GLOBAL_SETTINGS['url']:
        await update.message.reply_text("❌ No Shopify URL set! Use /seturl first.")
        return
    
    cards = context.args[:10]
    msg = await update.message.reply_text(f"⚡ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(cards)} 𝗰𝗮𝗿𝗱𝘀...\n\n0% □□□□□□□□□□ 0.00s")
    
    results = []
    username = update.effective_user.username or update.effective_user.first_name or "User"
    
    overall_start = time.time()
    
    for i, card_str in enumerate(cards, 1):
        card_data = card_str.split('|')
        if len(card_data) != 4:
            results.append(f"{i}. ❌ Invalid format")
            continue
        
        card_num, month, year, cvv = card_data
        
        try:
            start_time = time.time()
            proxy = get_next_proxy()
            bin_info = await get_bin_info(card_num[:6])
            checker = ShopifyChecker(proxy=proxy)
            
            progress_percent = int((i / len(cards)) * 100)
            progress_filled = int((i / len(cards)) * 10)
            progress_bar = "■" * progress_filled + "□" * (10 - progress_filled)
            elapsed_so_far = time.time() - overall_start
            await msg.edit_text(f"⚡ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {i}/{len(cards)}...\n\n{progress_percent}% {progress_bar} {elapsed_so_far:.2f}s")
            
            result_data = await checker.check_card(
                site_url=GLOBAL_SETTINGS['url'],
                card_num=card_num,
                month=month,
                year=year,
                cvv=cvv
            )
            elapsed = time.time() - start_time
            
            result = result_data if isinstance(result_data, str) else result_data.get('message', 'Unknown result')
            
            status = "✅" if "approved" in result.lower() or "live" in result.lower() else "❌"
            
            bin_str = ""
            if bin_info:
                brand = bin_info.get('brand', 'N/A')
                country_flag = bin_info.get('country_flag', '')
                bin_str = f"[{brand} {country_flag}]"
            
            card_display = f"{card_num}|{month}|{year}|{cvv}"
            results.append(f"{i}. {status} {card_display} {bin_str}\n   {result[:60]} - {elapsed:.1f}s")
            
        except Exception as e:
            results.append(f"{i}. ❌ {card_num}|{month}|{year}|{cvv}\n   Error: {str(e)[:50]}")
    
    total_time = time.time() - overall_start
    
    response = f"""み ¡@TOjiCHKBot ↯ ↝  𝙈𝙖𝙨𝙨 𝘾𝙝𝙚𝙘𝙠
━━━━━━━━━━━━━━━
📊 Total: {len(cards)} cards
🏪 Gateway: Shopify

{chr(10).join(results)}
━━━━━━━━━━━━━━━
• 𝗥𝗲𝗾 ⌁ @{username}
• 𝗗𝗲𝘃𝗕𝘆 ⌁ @ayaka_admins
• Time ⌁ {total_time:.2f}s
"""
    await msg.edit_text(response)

async def seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /seturl <domain>\nExample: /seturl https://example.myshopify.com")
        return
    
    url = context.args[0]
    if not url.startswith('http'):
        url = f'https://{url}'
    
    GLOBAL_SETTINGS['url'] = url
    save_settings()
    await update.message.reply_text(f"✅ Global Shopify URL set to:\n{url}")

async def myurl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if GLOBAL_SETTINGS['url']:
        await update.message.reply_text(f"🏪 Current URL: {GLOBAL_SETTINGS['url']}")
    else:
        await update.message.reply_text("❌ No URL set. Use /seturl to set one.")

async def rmurl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command!")
        return
    
    GLOBAL_SETTINGS['url'] = None
    save_settings()
    await update.message.reply_text("✅ Global URL removed.")

async def addp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /addp <proxy>\nExample: /addp http://user:pass@ip:port")
        return
    
    proxy = context.args[0]
    if proxy not in GLOBAL_SETTINGS['proxies']:
        GLOBAL_SETTINGS['proxies'].append(proxy)
        save_settings()
        await update.message.reply_text(f"✅ Proxy added!\n🔌 {proxy[:50]}...\n\n📊 Total proxies: {len(GLOBAL_SETTINGS['proxies'])}")
    else:
        await update.message.reply_text(f"⚠️ Proxy already exists!")

async def rp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command!")
        return
    
    if not context.args:
        GLOBAL_SETTINGS['proxies'] = []
        GLOBAL_SETTINGS['proxy_index'] = 0
        save_settings()
        await update.message.reply_text("✅ All proxies removed.")
        return
    
    try:
        index = int(context.args[0]) - 1
        if 0 <= index < len(GLOBAL_SETTINGS['proxies']):
            removed = GLOBAL_SETTINGS['proxies'].pop(index)
            if GLOBAL_SETTINGS['proxy_index'] >= len(GLOBAL_SETTINGS['proxies']) and GLOBAL_SETTINGS['proxies']:
                GLOBAL_SETTINGS['proxy_index'] = 0
            save_settings()
            await update.message.reply_text(f"✅ Proxy removed:\n{removed[:50]}...\n\n📊 Remaining: {len(GLOBAL_SETTINGS['proxies'])}")
        else:
            await update.message.reply_text(f"❌ Invalid index! Use /lp to see proxy list.")
    except ValueError:
        await update.message.reply_text("❌ Usage: /rp <number> or /rp (to remove all)\nExample: /rp 1")

async def lp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command!")
        return
    
    if not GLOBAL_SETTINGS['proxies']:
        await update.message.reply_text("❌ No proxies configured.")
        return
    
    proxy_list = "\n".join([f"{i+1}. {p[:50]}..." for i, p in enumerate(GLOBAL_SETTINGS['proxies'])])
    next_idx = GLOBAL_SETTINGS['proxy_index'] + 1
    await update.message.reply_text(f"🔌 Global Proxies ({len(GLOBAL_SETTINGS['proxies'])} total)\n🔄 Next: #{next_idx}\n\n{proxy_list}")

async def cp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command!")
        return
    
    if not GLOBAL_SETTINGS['proxies']:
        await update.message.reply_text("❌ No proxies configured.")
        return
    
    total = len(GLOBAL_SETTINGS['proxies'])
    next_idx = GLOBAL_SETTINGS['proxy_index'] + 1
    next_proxy = GLOBAL_SETTINGS['proxies'][GLOBAL_SETTINGS['proxy_index']]
    
    msg = await update.message.reply_text(f"⏳ Testing proxy...\n🔌 {next_proxy[:50]}...")
    
    try:
        start_time = time.time()
        
        async with httpx.AsyncClient(proxy=next_proxy, timeout=15.0) as client:
            response = await client.get('https://api.ipify.org?format=json')
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                ip_data = response.json()
                proxy_ip = ip_data.get('ip', 'Unknown')
                
                await msg.edit_text(
                    f"✅ Proxy is ALIVE!\n\n"
                    f"🔌 Proxy: {next_proxy[:50]}...\n"
                    f"🌐 IP: {proxy_ip}\n"
                    f"⚡ Response Time: {elapsed:.2f}s\n"
                    f"📊 Total Proxies: {total}\n"
                    f"🔄 Current Index: #{next_idx}"
                )
            else:
                await msg.edit_text(
                    f"⚠️ Proxy responded but with status {response.status_code}\n\n"
                    f"🔌 {next_proxy[:50]}...\n"
                    f"📊 Total: {total} | Index: #{next_idx}"
                )
    except httpx.ProxyError as e:
        await msg.edit_text(
            f"❌ Proxy is DEAD! (Proxy Error)\n\n"
            f"🔌 {next_proxy[:50]}...\n"
            f"❗ Error: Proxy connection failed\n"
            f"📊 Total: {total} | Index: #{next_idx}"
        )
    except httpx.TimeoutException:
        await msg.edit_text(
            f"❌ Proxy is DEAD! (Timeout)\n\n"
            f"🔌 {next_proxy[:50]}...\n"
            f"❗ Error: Connection timed out (>15s)\n"
            f"📊 Total: {total} | Index: #{next_idx}"
        )
    except Exception as e:
        await msg.edit_text(
            f"❌ Proxy is DEAD!\n\n"
            f"🔌 {next_proxy[:50]}...\n"
            f"❗ Error: {str(e)[:80]}\n"
            f"📊 Total: {total} | Index: #{next_idx}"
        )

async def chkurl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /chkurl <domain>")
        return
    
    url = context.args[0]
    if not url.startswith('http'):
        url = f'https://{url}'
    
    msg = await update.message.reply_text(f"⏳ Testing {url}...")
    
    try:
        checker = ShopifyChecker()
        from fake_useragent import UserAgent
        import httpx
        
        ua = UserAgent()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{url}/products.json",
                headers={'User-Agent': ua.random},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                products = data.get('products', [])
                await msg.edit_text(f"✅ Site is working!\n🏪 {url}\n📦 Found {len(products)} products")
            else:
                await msg.edit_text(f"⚠️ Site responded but may have issues\n🏪 {url}\n📡 Status: {response.status_code}")
                
    except Exception as e:
        await msg.edit_text(f"❌ Site test failed\n🏪 {url}\n❗ Error: {str(e)[:100]}")

async def mchku(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command!")
        return
    
    await update.message.reply_text("""
📋 Mass URL Check

Please send Shopify URLs (one per line):
Example:
https://shop1.myshopify.com
https://shop2.myshopify.com
https://shop3.myshopify.com

Send them in your next message.
    """)
    
    context.user_data['waiting_for_urls'] = True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_urls'):
        context.user_data['waiting_for_urls'] = False
        
        urls = [line.strip() for line in update.message.text.split('\n') if line.strip()]
        msg = await update.message.reply_text(f"⏳ Testing {len(urls)} sites...")
        
        results = []
        from fake_useragent import UserAgent
        import httpx
        
        ua = UserAgent()
        
        for i, url in enumerate(urls[:20], 1):
            if not url.startswith('http'):
                url = f'https://{url}'
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{url}/products.json",
                        headers={'User-Agent': ua.random},
                        timeout=10.0
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        products = len(data.get('products', []))
                        results.append(f"{i}. ✅ {url} ({products} products)")
                    else:
                        results.append(f"{i}. ⚠️ {url} (Status: {response.status_code})")
                        
            except Exception as e:
                results.append(f"{i}. ❌ {url} (Error)")
            
            if i % 5 == 0:
                await msg.edit_text(f"⏳ Testing {i}/{len(urls)}...\n\n{chr(10).join(results[-5:])}")
        
        response = f"📊 Mass URL Check Complete\n\n{chr(10).join(results)}"
        await msg.edit_text(response[:4000])

def main():
    load_settings()
    
    bot_token = os.getenv('8615792617:AAEQxc0mWh2e1gHwusCTjOm-JSseYPBzsgk')
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        print("❌ Error: TELEGRAM_BOT_TOKEN is required!")
        print("Please set your Telegram bot token in the Secrets panel.")
        return
    
    application = Application.builder().token(bot_token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sh", sh))
    application.add_handler(CommandHandler("msh", msh))
    application.add_handler(CommandHandler("seturl", seturl))
    application.add_handler(CommandHandler("myurl", myurl))
    application.add_handler(CommandHandler("rmurl", rmurl))
    application.add_handler(CommandHandler("addp", addp))
    application.add_handler(CommandHandler("rp", rp))
    application.add_handler(CommandHandler("lp", lp))
    application.add_handler(CommandHandler("cp", cp))
    application.add_handler(CommandHandler("chkurl", chkurl))
    application.add_handler(CommandHandler("mchku", mchku))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 TOJI CHK Bot Starting...")
    print("✅ Bot is running! Send /start to your bot to begin.")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

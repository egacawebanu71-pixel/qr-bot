import os
import sqlite3
import threading
import time
import logging
from datetime import datetime
from flask import Flask
import telebot
from telebot import types

# ---------------------------------------------------------
# 1. LOGGING & FLASK 24/7 KEEP-ALIVE SERVER
# ---------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

web_app = Flask('')

@web_app.route('/')
def home():
    return "DAKSH QR BOT IS ALIVE 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    web_app.run(host="0.0.0.0", port=port)

# ---------------------------------------------------------
# 2. BOT INITIALIZATION & DATABASE SETUP
# ---------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") # Render Environment Variables में टोकन डालें
bot = telebot.TeleBot(TOKEN)

# SQLite Database Setup
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

# Tables Creation
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0.0,
    banned INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS qr_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qr_file_id TEXT,
    price REAL,
    status TEXT DEFAULT 'AVAILABLE',
    claimed_by INTEGER
)''')

conn.commit()

# Default Main Admins
MAIN_ADMINS = [5057266771,8737232198]
for admin_id in MAIN_ADMINS:
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,))
conn.commit()

# Dynamic Admin Check Helper
def is_admin(user_id):
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def register_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username or "Unknown"))
    conn.commit()

def is_banned(user_id):
    cursor.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row and row[0] == 1

# Temporary memory store for multi-step inputs
user_states = {}

# ---------------------------------------------------------
# 3. USER COMMAND HANDLERS
# ---------------------------------------------------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    register_user(uid, message.from_user.username)
    
    if is_banned(uid):
        bot.reply_to(message, "❌ आप इस बॉट में बैन (Ban) हैं!")
        return
        
    bot.reply_to(message, 
                 "🚀 **DAKSH QR BOT** में आपका स्वागत है!\n\n"
                 "नीचे दिए गए ऑप्शन्स और कमांड्स का उपयोग करें।\n"
                 "💰 बैलेंस चेक: `/balance`\n"
                 "💸 विड्रॉल: `/withdrawal`", 
                 parse_mode="Markdown")

@bot.message_handler(commands=['balance'])
def balance_cmd(message):
    uid = message.from_user.id
    if is_banned(uid): return
    register_user(uid, message.from_user.username)
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
    bal = cursor.fetchone()[0]
    bot.reply_to(message, f"💰 **आपका कुल बैलेंस:** ₹{bal:.2f}", parse_mode="Markdown")

@bot.message_handler(commands=['withdrawal'])
def withdrawal_cmd(message):
    uid = message.from_user.id
    if is_banned(uid): return
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
    bal = cursor.fetchone()[0]
    
    if bal <= 0:
        bot.reply_to(message, "❌ आपके पास विड्रॉल करने के लिए बैलेंस नहीं है!")
    else:
        bot.reply_to(message, f"💸 आपका विड्रॉल रिक्वेस्ट स्वीकार कर लिया गया है। एडमिन आपसे जल्द संपर्क करेंगे।\nबैलेंस: ₹{bal:.2f}")

# ---------------------------------------------------------
# 4. MAIN ADMIN CONTROL PANEL
# ---------------------------------------------------------
@bot.message_handler(commands=['admin'])
def admin_panel_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ You are not authorized to use admin commands.")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    b1 = types.InlineKeyboardButton("📤 Upload QR", callback_data="p_uploadqr")
    b2 = types.InlineKeyboardButton("📊 Bot Stats", callback_data="p_stats")
    b3 = types.InlineKeyboardButton("📢 Broadcast", callback_data="p_broadcast")
    b4 = types.InlineKeyboardButton("💸 Withdrawals", callback_data="p_withdrawals")
    b5 = types.InlineKeyboardButton("👥 Pending Users", callback_data="p_pendingusers")
    b6 = types.InlineKeyboardButton("➕ Add Admin", callback_data="p_addadmin")
    b7 = types.InlineKeyboardButton("➖ Remove Admin", callback_data="p_removeadmin")
    b8 = types.InlineKeyboardButton("👤 Registered Users", callback_data="p_users")
    b9 = types.InlineKeyboardButton("🚫 Ban User", callback_data="p_banuser")
    b10 = types.InlineKeyboardButton("✅ Unban User", callback_data="p_unbanuser")

    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5)
    markup.add(b6, b7)
    markup.add(b8)
    markup.add(b9, b10)

    bot.send_message(message.chat.id, "👑 **MAIN ADMIN CONTROL PANEL**\n\nSelect an operation from below:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("p_"))
def admin_callbacks(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ आपके पास परमिशन नहीं है!", show_alert=True)
        return

    action = call.data
    chat_id = call.message.chat.id

    if action == "p_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        u_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM admins")
        a_count = cursor.fetchone()[0]
        bot.send_message(chat_id, f"📊 **Bot Stats:**\n\n👥 कुल यूज़र्स: `{u_count}`\n👑 कुल एडमिन: `{a_count}`", parse_mode="Markdown")
    
    elif action == "p_uploadqr":
        bot.send_message(chat_id, "📤 QR अपलोड करने के लिए `/uploadqr` टाइप करें या सीधे फोटो भेजें।", parse_mode="Markdown")
    
    elif action == "p_broadcast":
        bot.send_message(chat_id, "📢 ब्रॉडकास्ट भेजने के लिए यह कमांड लिखें:\n`/broadcast आपका मैसेज`", parse_mode="Markdown")
        
    elif action == "p_addadmin":
        bot.send_message(chat_id, "➕ नया एडमिन जोड़ने के लिए कमांड लिखें:\n`/addadmin <User_ID>`", parse_mode="Markdown")
        
    elif action == "p_removeadmin":
        bot.send_message(chat_id, "➖ एडमिन हटाने के लिए कमांड लिखें:\n`/removeadmin <User_ID>`", parse_mode="Markdown")
        
    elif action == "p_users":
        cursor.execute("SELECT user_id, username, balance FROM users LIMIT 20")
        rows = cursor.fetchall()
        text = "👥 **Registered Users (Top 20):**\n\n"
        for r in rows:
            text += f"• ID: `{r[0]}` | @{r[1]} | Balance: ₹{r[2]}\n"
        bot.send_message(chat_id, text, parse_mode="Markdown")

    elif action == "p_banuser":
        bot.send_message(chat_id, "🚫 यूज़र बैन करने के लिए लिखें:\n`/ban <User_ID>`", parse_mode="Markdown")

    elif action == "p_unbanuser":
        bot.send_message(chat_id, "✅ यूज़र अनबैन करने के लिए लिखें:\n`/unban <User_ID>`", parse_mode="Markdown")

# ---------------------------------------------------------
# 5. ALL ADMIN COMMANDS
# ---------------------------------------------------------

# /addadmin <User_ID>
@bot.message_handler(commands=['addadmin'])
def add_admin_cmd(message):
    if not is_admin(message.from_user.id): return
    try:
        new_id = int(message.text.split()[1])
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
        conn.commit()
        bot.reply_to(message, f"✅ **User ID `{new_id}` अब एडमिन बन चुका है!**", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ सही तरीका: `/addadmin 123456789`", parse_mode="Markdown")

# /removeadmin <User_ID>
@bot.message_handler(commands=['removeadmin'])
def remove_admin_cmd(message):
    if not is_admin(message.from_user.id): return
    try:
        rem_id = int(message.text.split()[1])
        cursor.execute("DELETE FROM admins WHERE user_id = ?", (rem_id,))
        conn.commit()
        bot.reply_to(message, f"🚫 **User ID `{rem_id}` को एडमिन से हटा दिया गया!**", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ सही तरीका: `/removeadmin 123456789`", parse_mode="Markdown")

# /users
@bot.message_handler(commands=['users'])
def users_cmd(message):
    if not is_admin(message.from_user.id): return
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    bot.reply_to(message, f"👥 **कुल रजिस्टर्ड यूज़र्स:** `{total}`", parse_mode="Markdown")

# /ban <User_ID>
@bot.message_handler(commands=['ban'])
def ban_cmd(message):
    if not is_admin(message.from_user.id): return
    try:
        target_id = int(message.text.split()[1])
        cursor.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        bot.reply_to(message, f"🚫 User ID `{target_id}` को **बैन** कर दिया गया!", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ सही तरीका: `/ban 123456789`", parse_mode="Markdown")

# /unban <User_ID>
@bot.message_handler(commands=['unban'])
def unban_cmd(message):
    if not is_admin(message.from_user.id): return
    try:
        target_id = int(message.text.split()[1])
        cursor.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        bot.reply_to(message, f"✅ User ID `{target_id}` को **अनबैन** कर दिया गया!", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ सही तरीका: `/unban 123456789`", parse_mode="Markdown")

# /broadcast <Message>
@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if not is_admin(message.from_user.id): return
    msg_text = message.text.replace("/broadcast", "").strip()
    if not msg_text:
        bot.reply_to(message, "⚠️ कमांड के साथ मैसेज भी लिखें! उदाहरण:\n`/broadcast हेलो दोस्तों`", parse_mode="Markdown")
        return
        
    cursor.execute("SELECT user_id FROM users WHERE banned = 0")
    users = cursor.fetchall()
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], msg_text)
            count += 1
        except:
            pass
    bot.reply_to(message, f"📢 ब्रॉडकास्ट कुल `{count}` यूज़र्स को भेज दिया गया!", parse_mode="Markdown")

# /broadcastphoto
@bot.message_handler(commands=['broadcastphoto'])
def broadcast_photo_cmd(message):
    if not is_admin(message.from_user.id): return
    user_states[message.from_user.id] = "WAITING_BROADCAST_PHOTO"
    bot.reply_to(message, "📸 कृपया वो फोटो भेजें जिसे आप सब यूज़र्स को ब्रॉडकास्ट करना चाहते हैं:")

# /uploadqr
@bot.message_handler(commands=['uploadqr'])
def upload_qr_cmd(message):
    if not is_admin(message.from_user.id): return
    user_states[message.from_user.id] = "WAITING_QR_PHOTO"
    bot.reply_to(message, "📥 कृपया QR Code की इमेज (Photo) भेजें:")

# Photo Receiver (For QR Upload & Broadcast Photo)
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    uid = message.from_user.id
    if not is_admin(uid): return
    
    state = user_states.get(uid)
    
    if state == "WAITING_BROADCAST_PHOTO":
        file_id = message.photo[-1].file_id
        caption = message.caption or ""
        cursor.execute("SELECT user_id FROM users WHERE banned = 0")
        users = cursor.fetchall()
        count = 0
        for u in users:
            try:
                bot.send_photo(u[0], file_id, caption=caption)
                count += 1
            except:
                pass
        user_states[uid] = None
        bot.reply_to(message, f"📸 फोटो ब्रॉडकास्ट `{count}` यूज़र्स को सफलतापूर्वक भेज दिया गया!", parse_mode="Markdown")
        
    elif state == "WAITING_QR_PHOTO":
        file_id = message.photo[-1].file_id
        cursor.execute("INSERT INTO qr_tasks (qr_file_id, price) VALUES (?, ?)", (file_id, 10.0))
        conn.commit()
        task_id = cursor.lastrowid
        user_states[uid] = None
        bot.reply_to(message, f"✅ QR Code सफलतापूर्वक सेव हो गया! Task ID: `{task_id}`", parse_mode="Markdown")

# /newqr - EXACT SCREENSHOT UI MATCHING
@bot.message_handler(commands=['newqr'])
def new_qr_cmd(message):
    if not is_admin(message.from_user.id): return
    cursor.execute("SELECT id, qr_file_id FROM qr_tasks WHERE status = 'AVAILABLE' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        bot.reply_to(message, "⚠️ कोई उपलब्ध QR नहीं है! पहले `/uploadqr` से QR अपलोड करें।")
        return
        
    task_id, file_id = row
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("💳 Make Payment", callback_data=f"claim_qr_{task_id}")
    markup.add(btn)
    
    # Exact Screenshot UI Caption
    caption_text = (
        "📢 **NEW QR AVAILABLE**\n\n"
        "Tap 💳 **Make Payment** to claim the QR.\n"
        "Only the first eligible member can claim it."
    )
    
    cursor.execute("SELECT user_id FROM users WHERE banned = 0")
    users = cursor.fetchall()
    for u in users:
        try:
            bot.send_photo(u[0], file_id, caption=caption_text, reply_markup=markup, parse_mode="Markdown")
        except:
            pass
    bot.reply_to(message, "🚀 नया QR स्क्रीनशॉट स्टाइल में सभी यूज़र्स को भेज दिया गया है!")

# QR Claim Button Action (First Come First Serve Security)
@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_qr_"))
def claim_qr_callback(call):
    uid = call.from_user.id
    if is_banned(uid):
        bot.answer_callback_query(call.id, "❌ आप बैन हैं!", show_alert=True)
        return
        
    task_id = int(call.data.replace("claim_qr_", ""))
    cursor.execute("SELECT status FROM qr_tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    
    if not row or row[0] != 'AVAILABLE':
        bot.answer_callback_query(call.id, "❌ यह QR पहले ही किसी द्वारा क्लेम किया जा चुका है!", show_alert=True)
    else:
        cursor.execute("UPDATE qr_tasks SET status = 'CLAIMED', claimed_by = ? WHERE id = ?", (uid, task_id))
        cursor.execute("UPDATE users SET balance = balance + 10.0 WHERE user_id = ?", (uid,))
        conn.commit()
        bot.answer_callback_query(call.id, "🎉 बधाई हो! आपने QR सफलता से क्लेम कर लिया। आपके खाते में ₹10 जोड़ दिए गए!", show_alert=True)

# /addbalance <User_ID> <Amount>
@bot.message_handler(commands=['addbalance'])
def add_balance_cmd(message):
    if not is_admin(message.from_user.id): return
    try:
        parts = message.text.split()
        target_id = int(parts[1])
        amount = float(parts[2])
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
        conn.commit()
        bot.reply_to(message, f"✅ User ID `{target_id}` के बैलेंस में **+₹{amount:.2f}** बढ़ा दिए गए!", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ सही तरीका: `/addbalance 123456789 50`", parse_mode="Markdown")

# /deductbalance <User_ID> <Amount>
@bot.message_handler(commands=['deductbalance'])
def deduct_balance_cmd(message):
    if not is_admin(message.from_user.id): return
    try:
        parts = message.text.split()
        target_id = int(parts[1])
        amount = float(parts[2])
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target_id))
        conn.commit()
        bot.reply_to(message, f"✅ User ID `{target_id}` के बैलेंस से **-₹{amount:.2f}** काट लिए गए!", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ सही तरीका: `/deductbalance 123456789 20`", parse_mode="Markdown")
# ---------------------------------------------------------
# CUSTOM KEYBOARD / TEXT BUTTON HANDLERS
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True)
def handle_text_buttons(message):
    uid = message.from_user.id
    if is_banned(uid): 
        return
        
    register_user(uid, message.from_user.username)
    text = message.text.strip()

    # Get QR Button
    if text in ["📍 Get QR", "Get QR", "QR"]:
        cursor.execute("SELECT id, qr_file_id FROM qr_tasks WHERE status = 'AVAILABLE' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            bot.reply_to(message, "⚠️ अभी कोई नया QR उपलब्ध नहीं है!")
            return
        task_id, file_id = row
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("💳 Make Payment", callback_data=f"claim_qr_{task_id}")
        markup.add(btn)
        caption_text = (
            "📢 **NEW QR AVAILABLE**\n\n"
            "Tap 💳 **Make Payment** to claim the QR.\n"
            "Only the first eligible member can claim it."
        )
        bot.send_photo(message.chat.id, file_id, caption=caption_text, reply_markup=markup, parse_mode="Markdown")

    # Balance Button
    elif text in ["💰 Balance", "Balance"]:
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        bal = cursor.fetchone()[0]
        bot.reply_to(message, f"💰 **आपका कुल बैलेंस:** ₹{bal:.2f}", parse_mode="Markdown")

    # Withdrawal Button
    elif text in ["💸 Withdrawal", "Withdrawal"]:
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        bal = cursor.fetchone()[0]
        if bal <= 0:
            bot.reply_to(message, "❌ आपके पास विड्रॉल करने के लिए बैलेंस नहीं है!")
        else:
            bot.reply_to(message, f"💸 आपका विड्रॉल रिक्वेस्ट स्वीकार कर लिया गया है। एडमिन आपसे जल्द संपर्क करेंगे।\nबैलेंस: ₹{bal:.2f}")

    # History Button
    elif text in ["📜 History", "History"]:
        bot.reply_to(message, "📜 आपकी हिस्ट्री में अभी कोई पिछला रिकॉर्ड नहीं है।")

    # Support Button
    elif text in ["🆘 Support", "Support"]:
        bot.reply_to(message, "🆘 सहायता के लिए हमारे एडमिन से संपर्क करें।")

# ---------------------------------------------------------
# 6. MAIN EXECUTION THREAD
# ---------------------------------------------------------
if __name__ == "__main__":
    # Start Keep-Alive Flask Server in background thread
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    
    print("Bot starting polling...")
    bot.infinity_polling(skip_pending=True)

import os
import sqlite3
import threading
import time
import logging
from datetime import datetime
from flask import Flask
import telebot
from telebot import types

# ==================== 🛠️ LOGGING SETUP ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==================== 🌐 24/7 KEEPALIVE SERVER ====================
web_app = Flask('')

@web_app.route('/')
def home():
    return "⚡ QR Task Bot Pro Max is Live and Running 24/7!"

def run_web():
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

keep_alive()

# ==================== ⚙️ CONFIGURATION ====================
BOT_TOKEN = "8699692757:AAH2TzJTjAWBU16kpTQZLf24YZPPvhWTKp4"
SUPPORT_USERNAME = "https://t.me/Dictator_0771"
MAIN_ADMIN_ID = 8737232198

REWARD_PER_TASK = 8.0   # ₹8 प्रति टास्क
MIN_WITHDRAWAL = 1.0    # ₹1 मिनिमम विड्रॉल

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ==================== 🗄️ DATABASE ENGINE ====================
db_lock = threading.Lock()
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

def init_db():
    with db_lock:
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'pending_approval',
            balance REAL DEFAULT 0.0
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            qr_file_id TEXT,
            reward REAL DEFAULT 8.0,
            status TEXT DEFAULT 'open',
            claimed_by INTEGER DEFAULT NULL,
            claim_time TIMESTAMP DEFAULT NULL
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            work_no INTEGER,
            task_no INTEGER,
            reward REAL,
            status TEXT,
            timestamp TEXT
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            upi_id TEXT,
            amount REAL,
            status TEXT DEFAULT 'PENDING',
            timestamp TEXT
        )''')

        # FORCE MAIN ADMIN AS APPROVED
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (MAIN_ADMIN_ID,))
        cursor.execute("INSERT OR REPLACE INTO users (user_id, status, balance) VALUES (?, 'approved', 0.0)", (MAIN_ADMIN_ID,))
        conn.commit()

init_db()

# ==================== ➕ ADD / REMOVE ADMIN COMMANDS ====================
@bot.message_handler(commands=['addadmin'])
def add_admin_cmd(message):
    if message.from_user.id != MAIN_ADMIN_ID:
        bot.send_message(message.chat.id, "❌ केवल Main Admin ही नए एडमिन जोड़ सकता है।")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.send_message(message.chat.id, "⚠️ **सही तरीका:** `/addadmin <User_ID>`\nउदाहरण: `/addadmin 123456789`")
            return
        
        new_admin_id = int(args[1])
        with db_lock:
            cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
            cursor.execute("UPDATE users SET status='approved' WHERE user_id=?", (new_admin_id,))
            conn.commit()
        
        bot.send_message(message.chat.id, f"✅ यूजर `{new_admin_id}` को सफलतापूर्वक **Admin** बना दिया गया है!")
        try:
            bot.send_message(new_admin_id, "🎉 **बधाई हो!** आपको इस बॉट का Admin बना दिया गया है। आप /admin कमांड का इस्तेमाल कर सकते हैं।")
        except Exception:
            pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ गलत User ID! कृपया केवल नंबर डालें।")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_cmd(message):
    if message.from_user.id != MAIN_ADMIN_ID:
        bot.send_message(message.chat.id, "❌ केवल Main Admin ही एडमिन हटा सकता है।")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.send_message(message.chat.id, "⚠️ **सही तरीका:** `/removeadmin <User_ID>`\nउदाहरण: `/removeadmin 123456789`")
            return
        
        rem_admin_id = int(args[1])
        if rem_admin_id == MAIN_ADMIN_ID:
            bot.send_message(message.chat.id, "❌ आप मेन एडमिन (खुद) को नहीं हटा सकते!")
            return

        with db_lock:
            cursor.execute("DELETE FROM admins WHERE user_id=?", (rem_admin_id,))
            conn.commit()
        
        bot.send_message(message.chat.id, f"✅ यूजर `{rem_admin_id}` को Admin से हटा दिया गया है।")
    except ValueError:
        bot.send_message(message.chat.id, "❌ गलत User ID! कृपया केवल नंबर डालें।")

# ==================== 🧱 HELPER FUNCTIONS ====================
def is_admin(user_id):
    if user_id == MAIN_ADMIN_ID:
        return True
    with db_lock:
        cursor.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
        return cursor.fetchone() is not None

def start_4min_timer(task_id, user_id):
    def timer_task():
        time.sleep(240)
        with db_lock:
            cursor.execute("SELECT status, claimed_by FROM tasks WHERE task_id=?", (task_id,))
            task = cursor.fetchone()
            if task and task[0] == 'claimed' and task[1] == user_id:
                cursor.execute("UPDATE tasks SET status='expired', claimed_by=NULL WHERE task_id=?", (task_id,))
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("INSERT INTO history (user_id, work_no, task_no, reward, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                               (user_id, task_id, task_id, REWARD_PER_TASK, "EXPIRED", now))
                conn.commit()
                try:
                    bot.send_message(user_id, "⚠️ **Task Expired!**\n\n4 minutes completed but you didn't submit task.")
                except Exception:
                    pass

    threading.Thread(target=timer_task, daemon=True).start()

def get_user_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("📩 Get QR")
    btn2 = types.KeyboardButton("💰 Balance")
    btn3 = types.KeyboardButton("💸 Withdrawal")
    btn4 = types.KeyboardButton("📜 History")
    btn5 = types.KeyboardButton("🆘 Support")
    markup.add(btn1, btn2, btn3, btn4)
    markup.add(btn5)
    return markup

# ==================== 🚀 /START COMMAND ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    
    # MAIN ADMIN BYPASS
    if user_id == MAIN_ADMIN_ID:
        with db_lock:
            cursor.execute("UPDATE users SET status='approved' WHERE user_id=?", (user_id,))
            conn.commit()
        bot.send_message(user_id, "👑 **Welcome Main Admin!**\n\nSend /admin anytime to open the Admin Panel.", reply_markup=get_user_keyboard())
        return

    with db_lock:
        cursor.execute("SELECT status FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()

        if not user:
            cursor.execute("INSERT INTO users (user_id, status) VALUES (?, 'pending_approval')", (user_id,))
            conn.commit()
            status = 'pending_approval'
        else:
            status = user[0]

    if status == 'banned':
        bot.send_message(user_id, "🚫 **Your account is permanently banned by administrator.**")
        return

    if status == 'approved':
        bot.send_message(user_id, "👋 **Welcome Back!**\nSelect an option from menu below:", reply_markup=get_user_keyboard())
        return

    # IF PENDING APPROVAL
    bot.send_message(user_id, "⏳ **Your request has been sent to the admin for approval.**\n\nPlease wait until an administrator approves your account.")

    # NOTIFY ADMIN
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"app_{user_id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user_id}"),
        types.InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{user_id}")
    )
    try:
        bot.send_message(MAIN_ADMIN_ID, f"👤 **New User Approval Request:**\n\nUser ID: `{user_id}`\nName: {message.from_user.first_name}", reply_markup=markup)
    except Exception:
        pass

# ==================== 👑 /ADMIN CONTROL PANEL ====================
@bot.message_handler(commands=['admin'])
def admin_panel_cmd(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ You are not authorized to use admin commands.")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    b1 = types.InlineKeyboardButton("📸 Upload QR", callback_data="p_uploadqr")
    b2 = types.InlineKeyboardButton("📊 Bot Stats", callback_data="p_stats")
    b3 = types.InlineKeyboardButton("📢 Broadcast", callback_data="p_broadcast")
    b4 = types.InlineKeyboardButton("💸 Withdrawals", callback_data="p_withdrawals")
    b5 = types.InlineKeyboardButton("👥 Pending Users", callback_data="p_pendingusers")
    markup.add(b1, b2, b3, b4, b5)

    bot.send_message(message.chat.id, "👑 **MAIN ADMIN CONTROL PANEL**\n\nSelect an operation from below:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("p_"))
def admin_panel_callbacks(call):
    if not is_admin(call.from_user.id):
        return

    action = call.data

    if action == "p_uploadqr":
        msg = bot.send_message(call.message.chat.id, "📸 **Send the QR Code Photo now to broadcast to all users:**")
        bot.register_next_step_handler(msg, process_qr_upload)

    elif action == "p_stats":
        with db_lock:
            cursor.execute("SELECT count(*) FROM users")
            total_users = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM users WHERE status='approved'")
            approved_users = cursor.fetchone()[0]
            cursor.execute("SELECT sum(balance) FROM users")
            total_bal = cursor.fetchone()[0] or 0.0
        bot.send_message(call.message.chat.id, f"📊 **BOT STATISTICS**\n\n👥 Total Users: {total_users}\n✅ Approved Users: {approved_users}\n💰 Total User Balances: ₹{total_bal:.2f}")

    elif action == "p_broadcast":
        msg = bot.send_message(call.message.chat.id, "📢 **Send the message you want to broadcast to all users:**")
        bot.register_next_step_handler(msg, process_broadcast)

    elif action == "p_withdrawals":
        with db_lock:
            cursor.execute("SELECT id, user_id, upi_id, amount FROM withdrawals WHERE status='PENDING' LIMIT 10")
            pending = cursor.fetchall()
        if not pending:
            bot.send_message(call.message.chat.id, "✅ No pending withdrawals!")
            return
        for w in pending:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Mark Paid", callback_data=f"pay_{w[0]}"))
            bot.send_message(call.message.chat.id, f"💸 **Pending Withdrawal #{w[0]}**\nUser: `{w[1]}`\nUPI: `{w[2]}`\nAmount: ₹{w[3]:.2f}", reply_markup=markup)

    elif action == "p_pendingusers":
        with db_lock:
            cursor.execute("SELECT user_id FROM users WHERE status='pending_approval' LIMIT 10")
            users = cursor.fetchall()
        if not users:
            bot.send_message(call.message.chat.id, "✅ No pending user approvals!")
            return
        for u in users:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"app_{u[0]}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{u[0]}"),
                types.InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{u[0]}")
            )
            bot.send_message(call.message.chat.id, f"👤 **Pending User:** `{u[0]}`", reply_markup=markup)

# ==================== 👮 APPROVE / REJECT / BAN HANDLERS ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith(("app_", "rej_", "ban_")))
def user_action_callback(call):
    if not is_admin(call.from_user.id):
        return

    act, target = call.data.split("_")
    target = int(target)

    if act == "app":
        with db_lock:
            cursor.execute("UPDATE users SET status='approved' WHERE user_id=?", (target,))
            conn.commit()
        bot.edit_message_text(f"✅ User `{target}` Approved!", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(target, "🎉 **Congratulations!** Your account has been approved by Admin.", reply_markup=get_user_keyboard())
        except Exception:
            pass

    elif act == "rej":
        with db_lock:
            cursor.execute("UPDATE users SET status='rejected' WHERE user_id=?", (target,))
            conn.commit()
        bot.edit_message_text(f"❌ User `{target}` Rejected!", call.message.chat.id, call.message.message_id)

    elif act == "ban":
        with db_lock:
            cursor.execute("UPDATE users SET status='banned' WHERE user_id=?", (target,))
            conn.commit()
        bot.edit_message_text(f"🚫 User `{target}` Banned!", call.message.chat.id, call.message.message_id)

# ==================== 📱 USER MENU HANDLER ====================
@bot.message_handler(func=lambda msg: msg.text in ["📩 Get QR", "💰 Balance", "💸 Withdrawal", "📜 History", "🆘 Support"])
def user_menu_handler(message):
    user_id = message.from_user.id
    
    with db_lock:
        cursor.execute("SELECT status, balance FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()

    if not user or user[0] != 'approved':
        bot.send_message(user_id, "⏳ **Your account is not approved yet.**")
        return

    text = message.text

    if text == "📩 Get QR":
        bot.send_message(user_id, "📍 **Get QR**\n\nThere is no QR available right now. Please wait for the next task.")

    elif text == "💰 Balance":
        bot.send_message(user_id, f"💰 **Your Balance:** ₹{user[1]:.2f}")

    elif text == "💸 Withdrawal":
        if user[1] < MIN_WITHDRAWAL:
            bot.send_message(user_id, f"💸 **Withdrawal**\n\n📌 Minimum withdrawal: ₹{int(MIN_WITHDRAWAL)}\n\nYour balance is below ₹{int(MIN_WITHDRAWAL)}.")
        else:
            msg = bot.send_message(user_id, f"💸 **Withdrawal**\n\nMinimum withdrawal: ₹{int(MIN_WITHDRAWAL)}\n\n**Enter your UPI ID:**")
            bot.register_next_step_handler(msg, process_upi_step)

    elif text == "📜 History":
        with db_lock:
            cursor.execute("SELECT count(*) FROM history WHERE user_id=? AND status='SUCCESS'", (user_id,))
            success = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM history WHERE user_id=? AND status='FAILED'", (user_id,))
            failed = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM history WHERE user_id=? AND status='EXPIRED'", (user_id,))
            expired = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM history WHERE user_id=? AND status='PENDING'", (user_id,))
            pending = cursor.fetchone()[0]

            cursor.execute("SELECT work_no, task_no, reward, status, timestamp FROM history WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
            last_act = cursor.fetchone()

        act_text = "No recent activity"
        if last_act:
            act_text = f"📂 Work #{last_act[0]}\n📌 Task: #{last_act[1]}\n💰 Reward: ₹{last_act[2]:.2f}\n📊 Status: {last_act[3]}\n🕒 {last_act[4]}"

        history_msg = f"📊 **MY HISTORY**\n\n✅ Success: {success}\n❌ Failed: {failed}\n⏳ Expired: {expired}\n⏳ Pending: {pending}\n\n📜 **RECENT ACTIVITY**\n__________________\n\n{act_text}"
        bot.send_message(user_id, history_msg)

    elif text == "🆘 Support":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🆘 Contact Support", url=SUPPORT_USERNAME))
        bot.send_message(user_id, "🆘 **Support Center**\n\nIf you need help or face any issues, contact support:", reply_markup=markup)

# ==================== 💳 WITHDRAWAL PROCESS ====================
def process_upi_step(message):
    upi_id = message.text.strip()
    msg = bot.send_message(message.chat.id, f"Enter amount to withdraw (Min ₹{int(MIN_WITHDRAWAL)}):")
    bot.register_next_step_handler(msg, lambda m: process_amount_step(m, upi_id))

def process_amount_step(message, upi_id):
    try:
        amount = float(message.text.strip())
        user_id = message.from_user.id
        
        with db_lock:
            cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
            bal = cursor.fetchone()[0]

            if amount < MIN_WITHDRAWAL or amount > bal:
                bot.send_message(user_id, "❌ **Invalid amount or insufficient balance.**")
                return

            cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, user_id))
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO withdrawals (user_id, upi_id, amount, timestamp) VALUES (?, ?, ?, ?)", (user_id, upi_id, amount, now))
            conn.commit()

        try:
            bot.send_message(MAIN_ADMIN_ID, f"💸 **NEW WITHDRAWAL REQUEST**\n\n👤 User ID: `{user_id}`\n💳 UPI ID: `{upi_id}`\n💰 Amount: ₹{amount:.2f}")
        except Exception:
            pass

        bot.send_message(user_id, "✅ **Withdrawal request submitted successfully!**\nAdmin will process it soon.")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Please enter a valid numerical amount.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def mark_paid_handler(call):
    if not is_admin(call.from_user.id):
        return
    wid = int(call.data.split("_")[1])
    with db_lock:
        cursor.execute("UPDATE withdrawals SET status='PAID' WHERE id=?", (wid,))
        conn.commit()
    bot.edit_message_text(f"✅ Withdrawal #{wid} marked as PAID!", call.message.chat.id, call.message.message_id)

# ==================== 🔒 FIRST-CLAIM QR SYSTEM ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_"))
def claim_qr_callback(call):
    task_id = int(call.data.split("_")[1])
    user_id = call.from_user.id

    with db_lock:
        cursor.execute("SELECT qr_file_id, status FROM tasks WHERE task_id=?", (task_id,))
        task = cursor.fetchone()

        if not task or task[1] != 'open':
            bot.answer_callback_query(call.id, "❌ QR already claimed by someone!", show_alert=True)
            return

        cursor.execute("UPDATE tasks SET status='claimed', claimed_by=?, claim_time=? WHERE task_id=? AND status='open'",
                       (user_id, datetime.now(), task_id))
        conn.commit()
        success = cursor.rowcount > 0

    if not success:
        bot.answer_callback_query(call.id, "❌ QR already claimed by someone!", show_alert=True)
        return

    bot.answer_callback_query(call.id, "✅ QR Claimed Successfully!")
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📤 Submit Task", callback_data=f"submittask_{task_id}"),
               types.InlineKeyboardButton("🔄 Release Task", callback_data=f"releasetask_{task_id}"))

    bot.send_photo(user_id, task[0], caption=f"📷 **QR CLAIMED**\n\nTask ID: #{task_id}\nYou have **4 minutes** to complete the payment and submit.", reply_markup=markup)
    start_4min_timer(task_id, user_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("submittask_", "releasetask_")))
def submit_release_handler(call):
    action, task_id = call.data.split("_")
    task_id = int(task_id)
    user_id = call.from_user.id

    if action == "releasetask":
        with db_lock:
            cursor.execute("UPDATE tasks SET status='open', claimed_by=NULL WHERE task_id=?", (task_id,))
            conn.commit()
        bot.edit_message_caption("🔄 Task released! Anyone else can claim it now.", call.message.chat.id, call.message.message_id)
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with db_lock:
            cursor.execute("UPDATE tasks SET status='submitted' WHERE task_id=?", (task_id,))
            cursor.execute("INSERT INTO history (user_id, work_no, task_no, reward, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                           (user_id, task_id, task_id, REWARD_PER_TASK, "PENDING", now))
            conn.commit()

        bot.edit_message_caption("✅ **Task submitted successfully!**\nWaiting for admin review.", call.message.chat.id, call.message.message_id)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Accept", callback_data=f"taskaccept_{task_id}_{user_id}"),
                   types.InlineKeyboardButton("❌ Reject", callback_data=f"taskreject_{task_id}_{user_id}"))
        try:
            bot.send_message(MAIN_ADMIN_ID, f"📑 **TASK SUBMISSION REVIEW**\n\n👤 User ID: `{user_id}`\n📌 Task ID: #{task_id}", reply_markup=markup)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith(("taskaccept_", "taskreject_")))
def task_review_handler(call):
    if not is_admin(call.from_user.id):
        return

    parts = call.data.split("_")
    action, task_id, user_id = parts[0], int(parts[1]), int(parts[2])

    if action == "taskaccept":
        with db_lock:
            cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (REWARD_PER_TASK, user_id))
            cursor.execute("UPDATE history SET status='SUCCESS' WHERE user_id=? AND work_no=?", (user_id, task_id))
            conn.commit()
        bot.edit_message_text(f"✅ Task #{task_id} Accepted for user `{user_id}`", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(user_id, f"🎉 **Task Accepted!**\n\n₹{REWARD_PER_TASK:.2f} has been added to your balance.")
        except Exception:
            pass
    else:
        with db_lock:
            cursor.execute("UPDATE history SET status='FAILED' WHERE user_id=? AND work_no=?", (user_id, task_id))
            conn.commit()
        bot.edit_message_text(f"❌ Task #{task_id} Rejected for user `{user_id}`", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(user_id, f"❌ **Task Rejected!**\n\nYour submission for Task #{task_id} was rejected by admin.")
        except Exception:
            pass

# ==================== 🛠️ HELPER PROCESSORS ====================
def process_qr_upload(message):
    if not message.photo:
        bot.send_message(message.chat.id, "❌ No photo detected.")
        return

    file_id = message.photo[-1].file_id
    with db_lock:
        cursor.execute("INSERT INTO tasks (qr_file_id, reward, status) VALUES (?, ?, 'open')", (file_id, REWARD_PER_TASK))
        task_id = cursor.lastrowid
        cursor.execute("SELECT user_id FROM users WHERE status='approved'")
        users = cursor.fetchall()
        conn.commit()

    # EXACT BROADCAST MESSAGE MATCHING SCREENSHOT
    qr_broadcast_msg = (
        "📢 **NEW QR AVAILABLE**\n\n"
        "Tap 💳 **Make Payment** to claim the QR.\n"
        "Only the first eligible member can claim it."
    )

    for u in users:
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Make Payment", callback_data=f"claim_{task_id}"))
            bot.send_message(u[0], qr_broadcast_msg, reply_markup=markup)
        except Exception:
            pass

    bot.send_message(message.chat.id, f"✅ **QR Task #{task_id} announced to all users!**")

def process_broadcast(message):
    text = message.text
    if not text:
        return
    with db_lock:
        cursor.execute("SELECT user_id FROM users WHERE status='approved'")
        users = cursor.fetchall()

    sent = 0
    for u in users:
        try:
            bot.send_message(u[0], text)
            sent += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"📢 Broadcast sent to {sent} users!")

# ==================== 🔄 RUN BOT ====================
logging.info("Bot is starting...")
bot.infinity_polling(timeout=20, long_polling_timeout=10)


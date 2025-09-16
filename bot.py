import asyncio
import os
import random
import json
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1003074172205
ADMIN_IDS = [1953766793]

# ---------------- STORAGE ----------------
GIVEAWAY_FILE = "giveaways.json"

def load_giveaways():
    if os.path.exists(GIVEAWAY_FILE):
        with open(GIVEAWAY_FILE, "r") as f:
            data = json.load(f)
            # Convert end_time strings back to datetime objects
            for g in data.values():
                g["end_time"] = datetime.fromisoformat(g["end_time"])
            return data
    return {}

def save_giveaways():
    with open(GIVEAWAY_FILE, "w") as f:
        # Convert datetime objects to ISO format strings
        data_to_save = {k: {**v, "end_time": v["end_time"].isoformat()} for k, v in active_giveaways.items()}
        json.dump(data_to_save, f, indent=2)

# ---------------- GIVEAWAYS ----------------
active_giveaways = load_giveaways()

TITLE, WINNERS, DURATION, KEYS = range(4)

# ---------------- ADMIN COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized!")
        return
    keyboard = [
        [InlineKeyboardButton("Host Giveaway", callback_data="host_giveaway")],
        [InlineKeyboardButton("View Stats", callback_data="view_stats")]
    ]
    await update.message.reply_text("⚡ Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

# ---------------- HOST GIVEAWAY FLOW ----------------
async def host_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Enter giveaway title:")
    return TITLE

async def host_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Enter number of winners:")
    return WINNERS

async def host_winners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['winners'] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number:")
        return WINNERS
    await update.message.reply_text("Enter duration in minutes:")
    return DURATION

async def host_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['duration'] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid duration:")
        return DURATION
    await update.message.reply_text("Enter digital keys (comma-separated):")
    return KEYS

async def host_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keys_input = update.message.text
    keys_list = [k.strip() for k in keys_input.split(",") if k.strip()]
    if not keys_list:
        await update.message.reply_text("❌ No keys entered. Please enter at least one key:")
        return KEYS

    context.user_data['keys'] = keys_list

    # Post giveaway in channel
    title = context.user_data['title']
    winners = context.user_data['winners']
    duration = context.user_data['duration']
    end_time = datetime.now() + timedelta(minutes=duration)

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎟 JOIN", callback_data="join_inline")]])
    msg = await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"🎁 **GIVEAWAY** 🎁\n\n"
             f"🏷 Prize: {title}\n"
             f"🎯 Winners: {winners}\n"
             f"👥 Participants: 0\n"
             f"⏳ Time Left: {duration:02}:00:00\n\n"
             f"✅ Tap JOIN to participate!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    # Save giveaway
    active_giveaways[str(msg.message_id)] = {
        "title": title,
        "winners": winners,
        "participants": {},
        "end_time": end_time,
        "channel_id": CHANNEL_ID,
        "keys": keys_list,
        "used_keys": []
    }
    save_giveaways()

    asyncio.create_task(countdown_task(str(msg.message_id), context.bot))
    await update.message.reply_text(f"✅ Giveaway hosted successfully! Message ID: {msg.message_id}")
    return ConversationHandler.END

# ---------------- PARTICIPATION ----------------
async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg_id = str(query.message.message_id)
    giveaway = active_giveaways.get(msg_id)
    if not giveaway:
        await query.answer("❌ Giveaway not found", show_alert=True)
        return

    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    if user_id not in giveaway["participants"]:
        giveaway["participants"][user_id] = username
        save_giveaways()
        await update_message(giveaway, msg_id, query.message.chat.id)

    await query.answer("🎟 You joined the giveaway!", show_alert=True)

# ---------------- UPDATE MESSAGE ----------------
async def update_message(giveaway, msg_id, chat_id):
    remaining = giveaway["end_time"] - datetime.now()
    total_seconds = max(0, int(remaining.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎟 JOIN", callback_data="join_inline")]])
    try:
        await Bot(TOKEN).edit_message_text(
            chat_id=chat_id,
            message_id=int(msg_id),
            text=f"🎁 **GIVEAWAY** 🎁\n\n"
                 f"🏷 Prize: {giveaway['title']}\n"
                 f"🎯 Winners: {giveaway['winners']}\n"
                 f"👥 Participants: {len(giveaway['participants'])}\n"
                 f"⏳ Time Left: {hours:02}:{minutes:02}:{seconds:02}\n\n"
                 f"✅ Tap JOIN to participate!",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except:
        pass

# ---------------- COUNTDOWN TASK ----------------
async def countdown_task(msg_id, bot_instance):
    while msg_id in active_giveaways:
        giveaway = active_giveaways[msg_id]
        remaining = giveaway["end_time"] - datetime.now()
        if remaining.total_seconds() <= 0:
            await end_giveaway(msg_id, bot_instance)
            break
        else:
            await update_message(giveaway, msg_id, giveaway["channel_id"])
        await asyncio.sleep(60)

# ---------------- END GIVEAWAY ----------------
async def end_giveaway(msg_id, bot_instance):
    giveaway = active_giveaways.get(msg_id)
    if not giveaway:
        return

    participants = list(giveaway["participants"].values())
    winners = random.sample(participants, min(giveaway["winners"], len(participants)))
    winner_text = "\n".join([f"@{w}" for w in winners]) if winners else "No winners"

    # Send keys to winners
    for winner_username in winners:
        if giveaway["keys"]:
            key = giveaway["keys"].pop(0)
            giveaway["used_keys"].append(key)
            try:
                user = [uid for uid, uname in giveaway["participants"].items() if uname == winner_username][0]
                await bot_instance.send_message(chat_id=user, text=f"🎉 Congratulations! You won **{giveaway['title']}**\nYour reward: `{key}`", parse_mode="Markdown")
            except:
                pass

    await bot_instance.edit_message_text(
        chat_id=giveaway["channel_id"],
        message_id=int(msg_id),
        text=f"🎉 **GIVEAWAY ENDED** 🎉\n\n🏷 Prize: {giveaway['title']}\n👥 Total Participants: {len(giveaway['participants'])}\n🏆 Winners:\n{winner_text}",
        parse_mode="Markdown"
    )

    # Remove giveaway from memory and save
    del active_giveaways[msg_id]
    save_giveaways()

# ---------------- MAIN ----------------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(host_start, pattern="host_giveaway")],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_title)],
            WINNERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_winners)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_duration)],
            KEYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_keys)],
        },
        fallbacks=[]
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(join_callback, pattern="join_inline"))

    # Resume countdowns for active giveaways after restart
    for msg_id in list(active_giveaways.keys()):
        asyncio.create_task(countdown_task(msg_id, app.bot))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

import threading
import asyncio
import random
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

TOKEN = "8234483503:AAHqzO3yQH3zR7zTNrTQDgy0WGCspYEhwuM"
bot = Bot(TOKEN)
active_giveaways = {}  # message_id: {title, winners, participants, end_time, channel_id}

app = Flask(__name__)

# ---------------- TELEGRAM BOT HANDLER ----------------
async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    msg_id = query.message.message_id
    chat_id = query.message.chat.id

    giveaway = active_giveaways.get(msg_id)
    if giveaway and giveaway["channel_id"] == chat_id:
        if user_id not in giveaway["participants"]:
            giveaway["participants"][user_id] = username
            await update_message(giveaway, msg_id, chat_id)
        await query.answer("🎟 You joined the giveaway!", show_alert=True)
    else:
        await query.answer("❌ Giveaway not found", show_alert=True)

async def update_message(giveaway, msg_id, chat_id):
    remaining = giveaway["end_time"] - datetime.now()
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎟 JOIN", callback_data="join_inline")]])
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=f"🎁 **GIVEAWAY** 🎁\n\n🏷️ Prize: {giveaway['title']}\n🎯 Winners: {giveaway['winners']}\n👥 Participants: {len(giveaway['participants'])}\n⏳ Time Left: {hours:02}:{minutes:02}:{seconds:02}\n\n✅ Tap JOIN to participate!",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except:
        pass

async def giveaway_countdown(msg_id):
    while msg_id in active_giveaways:
        giveaway = active_giveaways[msg_id]
        remaining = giveaway["end_time"] - datetime.now()
        if remaining.total_seconds() <= 0:
            participants = list(giveaway["participants"].values())
            winners = random.sample(participants, min(giveaway["winners"], len(participants)))
            winner_text = "\n".join([f"@{w}" for w in winners]) if winners else "No winners"
            await bot.edit_message_text(
                chat_id=giveaway["channel_id"],
                message_id=msg_id,
                text=f"🎉 **GIVEAWAY ENDED** 🎉\n\n🏷️ Prize: {giveaway['title']}\n👥 Total Participants: {len(giveaway['participants'])}\n🏆 Winners:\n{winner_text}",
                parse_mode="Markdown"
            )
            del active_giveaways[msg_id]
            break
        else:
            await update_message(giveaway, msg_id, giveaway["channel_id"])
        await asyncio.sleep(60)

# ---------------- FLASK API ----------------
@app.route("/create_giveaway", methods=["POST"])
def create_giveaway():
    data = request.json
    title = data.get("title")
    winners = data.get("winners")
    duration = data.get("duration")
    channel_id = int(data.get("channel_id"))
    if not all([title, winners, duration, channel_id]):
        return {"status": "error", "message": "Missing fields"}, 400

    end_time = datetime.now() + timedelta(minutes=duration)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎟 JOIN", callback_data="join_inline")]])
    msg = asyncio.run(bot.send_message(
        chat_id=channel_id,
        text=f"🎁 **GIVEAWAY** 🎁\n\n🏷️ Prize: {title}\n🎯 Winners: {winners}\n👥 Participants: 0\n⏳ Time Left: {duration:02}:00:00\n\n✅ Tap JOIN to participate!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    ))
    active_giveaways[msg.message_id] = {
        "title": title,
        "winners": winners,
        "participants": {},
        "end_time": end_time,
        "channel_id": channel_id
    }
    asyncio.create_task(giveaway_countdown(msg.message_id))
    return {"status": "success", "message_id": msg.message_id}

# ---------------- RUN TELEGRAM BOT ----------------
async def start_bot():
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CallbackQueryHandler(join_callback))
    await bot_app.run_polling()

if __name__ == "__main__":
    # Start bot in background
    threading.Thread(target=lambda: asyncio.run(start_bot()), daemon=True).start()
    # Run Flask API
    app.run(host="0.0.0.0", port=5000)

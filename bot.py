import asyncio
from flask import Flask, request, jsonify
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

import os, random
from datetime import datetime, timedelta

TOKEN = os.environ.get("BOT_TOKEN")
bot = Bot(TOKEN)
active_giveaways = {}

app = Flask(__name__)

# ---------------- TELEGRAM HANDLERS ----------------
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
            text=f"🎁 **GIVEAWAY** 🎁\n\n"
                 f"🏷️ Prize: {giveaway['title']}\n"
                 f"🎯 Winners: {giveaway['winners']}\n"
                 f"👥 Participants: {len(giveaway['participants'])}\n"
                 f"⏳ Time Left: {hours:02}:{minutes:02}:{seconds:02}\n\n"
                 f"✅ Tap JOIN to participate!",
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
                text=f"🎉 **GIVEAWAY ENDED** 🎉\n\n"
                     f"🏷️ Prize: {giveaway['title']}\n"
                     f"👥 Total Participants: {len(giveaway['participants'])}\n"
                     f"🏆 Winners:\n{winner_text}",
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
        return jsonify({"status": "error", "message": "Missing fields"}), 400

    end_time = datetime.now() + timedelta(minutes=duration)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎟 JOIN", callback_data="join_inline")]])
    try:
        msg = asyncio.run(bot.send_message(
            chat_id=channel_id,
            text=f"🎁 **GIVEAWAY** 🎁\n\n"
                 f"🏷️ Prize: {title}\n"
                 f"🎯 Winners: {winners}\n"
                 f"👥 Participants: 0\n"
                 f"⏳ Time Left: {duration:02}:00:00\n\n"
                 f"✅ Tap JOIN to participate!",
            reply_markup=keyboard,
            parse_mode="Markdown"
        ))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    active_giveaways[msg.message_id] = {
        "title": title,
        "winners": winners,
        "participants": {},
        "end_time": end_time,
        "channel_id": channel_id
    }
    asyncio.create_task(giveaway_countdown(msg.message_id))
    return jsonify({"status": "success", "message_id": msg.message_id})

# ---------------- MAIN ----------------
async def main():
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CallbackQueryHandler(join_callback))
    # Run Flask in executor
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))))
    await bot_app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

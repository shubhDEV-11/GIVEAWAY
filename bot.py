import json
import random
from datetime import datetime, timedelta
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

# ---------------- CONFIG ---------------- #
TOKEN = "8234483503:AAHqzO3yQH3zR7zTNrTQDgy0WGCspYEhwuM"
CHANNEL_ID = -1002219330498   # 🔹 your channel ID
ADMIN_ID = 1953766793          # 🔹 your Telegram user ID
GIVEAWAY_FILE = "giveaway.json"

# ---------------- JSON helpers ---------------- #
def load_giveaways():
    try:
        with open(GIVEAWAY_FILE, "r") as f:
            data = json.load(f)
        if data.get("active_giveaway"):
            g = data["active_giveaway"]
            if isinstance(g.get("end_time"), str):
                g["end_time"] = datetime.fromisoformat(g["end_time"])
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active_giveaway": None, "participants": []}

def save_giveaways(data):
    if data.get("active_giveaway"):
        g = data["active_giveaway"]
        if isinstance(g.get("end_time"), datetime):
            g["end_time"] = g["end_time"].isoformat()
    with open(GIVEAWAY_FILE, "w") as f:
        json.dump(data, f, indent=2)

data = load_giveaways()

# ---------------- Bot Handlers ---------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! Stay tuned for giveaways!")

async def host(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to host giveaways.")
        return

    if data["active_giveaway"]:
        await update.message.reply_text("⚠️ A giveaway is already active!")
        return

    try:
        title = context.args[0]
        winners = int(context.args[1])
        duration = int(context.args[2])
        reward_keys = context.args[3:]  # keys entered inline
    except Exception:
        await update.message.reply_text("Usage: /host <title> <winners> <duration-minutes> <key1> <key2> ...")
        return

    if len(reward_keys) < winners:
        await update.message.reply_text("⚠️ Not enough keys for winners.")
        return

    end_time = datetime.utcnow() + timedelta(minutes=duration)

    # create giveaway object
    data["active_giveaway"] = {
        "title": title,
        "winners": winners,
        "reward_keys": reward_keys,
        "end_time": end_time,
        "participants": [],
        "message_id": None,
        "chat_id": CHANNEL_ID
    }
    save_giveaways(data)

    # post giveaway in channel
    keyboard = [[InlineKeyboardButton("🎉 Join Giveaway", callback_data="join")]]
    msg = await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"🎁 **{title}** 🎁\n\nReward: 🎟 Digital Keys\nWinners: {winners}\n\nParticipants: 0\nTime left: {duration}:00",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    data["active_giveaway"]["message_id"] = msg.message_id
    save_giveaways(data)

    asyncio.create_task(update_giveaway(context))

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not data.get("active_giveaway"):
        await query.edit_message_text("❌ No active giveaway!")
        return

    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    if user_id not in [p["id"] for p in data["active_giveaway"]["participants"]]:
        data["active_giveaway"]["participants"].append({"id": user_id, "username": username})
        save_giveaways(data)

    await query.answer("✅ You joined the giveaway!")

async def update_giveaway(context: ContextTypes.DEFAULT_TYPE):
    while data.get("active_giveaway"):
        g = data["active_giveaway"]
        now = datetime.utcnow()
        remaining = g["end_time"] - now

        if remaining.total_seconds() <= 0:
            await end_giveaway(context)
            break

        mins, secs = divmod(int(remaining.total_seconds()), 60)
        text = (
            f"🎁 **{g['title']}** 🎁\n\n"
            f"Reward: 🎟 Digital Keys\n"
            f"Winners: {g['winners']}\n\n"
            f"Participants: {len(g['participants'])}\n"
            f"Time left: {mins:02}:{secs:02}"
        )

        keyboard = [[InlineKeyboardButton("🎉 Join Giveaway", callback_data="join")]]
        try:
            await context.bot.edit_message_text(
                chat_id=g["chat_id"],
                message_id=g["message_id"],
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except Exception:
            pass

        await asyncio.sleep(60)

async def end_giveaway(context: ContextTypes.DEFAULT_TYPE):
    g = data["active_giveaway"]
    if not g:
        return

    winners = []
    if g["participants"]:
        winners = random.sample(g["participants"], min(len(g["participants"]), g["winners"]))

    win_text = "🏆 **Giveaway Ended!** 🏆\n\n"
    win_text += f"🎁 {g['title']}\n\n"
    if winners:
        win_text += "👑 Winners:\n"
        for i, w in enumerate(winners):
            key = g["reward_keys"][i]
            win_text += f"@{w['username']} — 🎟 `{key}`\n"
            try:
                # auto deliver key in DM
                await context.bot.send_message(
                    chat_id=w["id"],
                    text=f"🎉 Congratulations! You won **{g['title']}** 🎁\n\nHere is your reward key:\n`{key}`",
                    parse_mode="Markdown"
                )
            except Exception:
                win_text += f"(❌ Could not DM {w['username']})\n"
    else:
        win_text += "❌ No participants joined."

    await context.bot.send_message(chat_id=g["chat_id"], text=win_text, parse_mode="Markdown")

    data["active_giveaway"] = None
    save_giveaways(data)

# ---------------- Main ---------------- #
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("host", host))
    app.add_handler(CallbackQueryHandler(join, pattern="join"))

    app.run_polling()

if __name__ == "__main__":
    main()

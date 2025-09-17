import telegram
print(">>> python-telegram-bot version:", telegram.__version__)
import json
import os
import random
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------------- CONFIG ----------------
TOKEN = os.getenv("BOT_TOKEN")  # put in Render env
ADMIN_ID = int(os.getenv("ADMIN_ID", "1953766793"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002219330498"))  # Giveaway channel

GIVEAWAYS_FILE = "giveaways.json"


# ---------------- STORAGE ----------------
def load_giveaways():
    if not os.path.exists(GIVEAWAYS_FILE):
        return []
    with open(GIVEAWAYS_FILE, "r") as f:
        data = json.load(f)
        for g in data:
            if g.get("end_time"):
                g["end_time"] = datetime.fromisoformat(g["end_time"])
        return data


def save_giveaways(giveaways):
    data = []
    for g in giveaways:
        g_copy = g.copy()
        if isinstance(g_copy.get("end_time"), datetime):
            g_copy["end_time"] = g_copy["end_time"].isoformat()
        data.append(g_copy)
    with open(GIVEAWAYS_FILE, "w") as f:
        json.dump(data, f, indent=4)


active_giveaways = load_giveaways()


# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎉 Welcome to the Giveaway Bot!\nAdmins can use /start_giveaway to create one.")


async def start_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ You are not authorized.")

    if len(context.args) < 3:
        return await update.message.reply_text("Usage: /start_giveaway <duration_minutes> <reward> <key>")

    try:
        duration = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("❌ Duration must be a number.")

    reward = context.args[1]
    key = " ".join(context.args[2:])
    end_time = datetime.utcnow() + timedelta(minutes=duration)

    giveaway = {
        "id": len(active_giveaways) + 1,
        "reward": reward,
        "key": key,
        "participants": [],
        "end_time": end_time,
        "message_id": None,
    }
    active_giveaways.append(giveaway)
    save_giveaways(active_giveaways)

    # Post in channel
    keyboard = [[InlineKeyboardButton("🎁 Join Giveaway", callback_data=f"join_{giveaway['id']}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"🎉 **Giveaway Started!** 🎉\n\n🏆 Reward: {reward}\n⏰ Ends in {duration} minutes\n\nClick below to join!",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    giveaway["message_id"] = msg.message_id
    save_giveaways(active_giveaways)

    await update.message.reply_text("✅ Giveaway started & posted in channel!")


async def join_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    giveaway_id = int(query.data.split("_")[1])

    giveaway = next((g for g in active_giveaways if g["id"] == giveaway_id), None)
    if not giveaway:
        return await query.message.reply_text("⚠️ This giveaway has ended or is invalid.")

    if user_id in giveaway["participants"]:
        return await query.answer("You already joined!")

    giveaway["participants"].append(user_id)
    save_giveaways(active_giveaways)

    await query.answer("✅ You joined the giveaway!")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ You are not authorized.")
    if not active_giveaways:
        return await update.message.reply_text("⚠️ No active giveaways.")
    g = active_giveaways[-1]
    await update.message.reply_text(
        f"📊 Giveaway Stats\n\n🏆 Reward: {g['reward']}\n👥 Participants: {len(g['participants'])}"
    )


# ---------------- JOBS ----------------
async def check_giveaways(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow()
    ended = [g for g in active_giveaways if g["end_time"] <= now]

    for g in ended:
        if g["participants"]:
            winner_id = random.choice(g["participants"])
            try:
                await context.bot.send_message(
                    chat_id=winner_id,
                    text=f"🎉 Congratulations! You won the giveaway!\n\n🏆 Reward: {g['reward']}\n🔑 Key: {g['key']}",
                )
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=f"🏆 Giveaway Ended!\n\nWinner: [{winner_id}](tg://user?id={winner_id})\nReward: {g['reward']}",
                    parse_mode="Markdown",
                )
            except Exception as e:
                print(f"Error sending reward: {e}")
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"⚠️ Giveaway Ended! No participants for {g['reward']}.",
            )

        active_giveaways.remove(g)
        save_giveaways(active_giveaways)


# ---------------- MAIN ----------------
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_giveaway", start_giveaway))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(join_giveaway))

    app.job_queue.run_repeating(check_giveaways, interval=30)

    app.run_polling()


if __name__ == "__main__":
    main()

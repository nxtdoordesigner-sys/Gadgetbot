import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from bot import handle_message, add_to_cart, view_cart
from catalog import get_all_books, search_books, format_catalog
from admin import register_admin_handlers

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"⚡ Hey {name}! Welcome to *VoltStore* 📱💻\n\n"
        "I'm Volt, your personal gadget assistant.\n\n"
        "Here's what I can do:\n"
        "• /catalog — Browse all products\n"
        "• /search <product name> — Find a gadget\n"
        "• /cart — View your cart\n"
        "• /orders — Your order history\n\n"
        "Or just tell me what you're looking for — I got you! ⚡",
        parse_mode="Markdown"
    )


async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = get_all_books()
    if not products:
        await update.message.reply_text("😔 No products in stock right now. Check back soon!")
        return

    text = format_catalog(products)
    await update.message.reply_text(
        f"📱 *VoltStore Catalog*\n\n{text}\n\n"
        "To order, just tell me the product name or ID!",
        parse_mode="Markdown"
    )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <product name>")
        return

    products = search_books(query)
    if not products:
        await update.message.reply_text(f"😔 No results for *{query}*.", parse_mode="Markdown")
        return

    text = format_catalog(products)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = view_cart(user_id)
    await update.message.reply_text(text, parse_mode="Markdown")


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args

    if not args:
        await update.message.reply_text("Usage: /add <product_id> [quantity]\nExample: /add 3 2")
        return

    try:
        product_id = int(args[0])
        quantity = int(args[1]) if len(args) > 1 else 1
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Use: /add <product_id> [quantity]")
        return

    reply = await add_to_cart(user_id, product_id, quantity)
    await update.message.reply_text(reply, parse_mode="Markdown")


async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from orders import get_orders_by_user, format_order_summary
    user_id = str(update.effective_user.id)
    user_orders = get_orders_by_user(user_id)

    if not user_orders:
        await update.message.reply_text("📭 You have no orders yet.")
        return

    text = "\n\n".join([format_order_summary(o) for o in user_orders[:5]])
    await update.message.reply_text(text, parse_mode="Markdown")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    reply = await handle_message(user_id, user_message, bot=context.bot)
    await update.message.reply_text(reply, parse_mode="Markdown")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("catalog", catalog))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("cart", cart))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    register_admin_handlers(app)

    logger.info("⚡ VoltStore bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

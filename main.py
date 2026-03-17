import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from bot import handle_message, add_to_cart, view_cart, ADMIN_IDS
from catalog import get_all_books, search_books, format_catalog, get_book_by_id
from supabase_client import supabase

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ── /start ────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    user_id = update.effective_user.id
    is_admin = user_id in ADMIN_IDS

    if is_admin:
        keyboard = [
            [InlineKeyboardButton("📦 View Orders", callback_data="admin_orders"),
             InlineKeyboardButton("📚 Inventory", callback_data="admin_inventory")],
            [InlineKeyboardButton("➕ Add Product", callback_data="admin_add_product"),
             InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        ]
        await update.message.reply_text(
            f"👋 Hey {name}! VoltStore Admin Panel ⚡\n\nWhat would you like to do?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        keyboard = [
            [InlineKeyboardButton("📱 Browse Catalog", callback_data="browse_catalog"),
             InlineKeyboardButton("🔍 Search", callback_data="browse_search")],
            [InlineKeyboardButton("🛒 My Cart", callback_data="browse_cart"),
             InlineKeyboardButton("📦 My Orders", callback_data="browse_orders")],
        ]
        await update.message.reply_text(
            f"⚡ Hey {name}! Welcome to *VoltStore* 📱💻\n\nI'm Volt — what are you looking for?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )


# ── /catalog — show products with photos ─────────────────
async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = get_all_books()
    if not products:
        await update.message.reply_text("😔 No products in stock right now!")
        return
    await send_catalog(update.message, products)


async def send_catalog(message, products):
    for product in products[:10]:  # Cap at 10 to avoid spam
        keyboard = [[InlineKeyboardButton("🛒 Order This", callback_data=f"order_{product['id']}")]]
        caption = (
            f"*{product['title']}*\n"
            f"🏷️ {product['author']}\n"
            f"📂 {product.get('category', '')}\n"
            f"💰 ₦{product['price']:,}\n"
            f"{'✅ In Stock' if product['in_stock'] else '❌ Out of Stock'}"
        )
        image_url = product.get("image_url")
        try:
            if image_url:
                await message.reply_photo(
                    photo=image_url,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await message.reply_text(
                    caption,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception:
            await message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# ── /search ───────────────────────────────────────────────
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <product name>")
        return
    from catalog import search_books
    products = search_books(query)
    if not products:
        await update.message.reply_text(f"😔 No results for *{query}*.", parse_mode="Markdown")
        return
    await send_catalog(update.message, products)


# ── /cart ─────────────────────────────────────────────────
async def cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = view_cart(user_id)
    await update.message.reply_text(text, parse_mode="Markdown")


# ── /orders ───────────────────────────────────────────────
async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from orders import get_orders_by_user, format_order_summary
    user_id = str(update.effective_user.id)
    user_orders = get_orders_by_user(user_id)
    if not user_orders:
        await update.message.reply_text("📭 You have no orders yet.")
        return
    text = "\n\n".join([format_order_summary(o) for o in user_orders[:5]])
    await update.message.reply_text(text, parse_mode="Markdown")


# ── /admin ────────────────────────────────────────────────
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Access denied.")
        return
    keyboard = [
        [InlineKeyboardButton("📦 Pending Orders", callback_data="admin_orders"),
         InlineKeyboardButton("📚 Inventory", callback_data="admin_inventory")],
        [InlineKeyboardButton("➕ Add Product", callback_data="admin_add_product"),
         InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
    ]
    await update.message.reply_text(
        "🛠 *VoltStore Admin Panel*\n\nChoose an action:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ── Callback query handler ────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    is_admin = user_id in ADMIN_IDS

    # ── Customer callbacks
    if data == "browse_catalog":
        products = get_all_books()
        await query.message.reply_text("📱 Here's our catalog:")
        await send_catalog(query.message, products)

    elif data == "browse_cart":
        text = view_cart(str(user_id))
        await query.message.reply_text(text, parse_mode="Markdown")

    elif data == "browse_orders":
        from orders import get_orders_by_user, format_order_summary
        user_orders = get_orders_by_user(str(user_id))
        if not user_orders:
            await query.message.reply_text("📭 No orders yet.")
        else:
            text = "\n\n".join([format_order_summary(o) for o in user_orders[:5]])
            await query.message.reply_text(text, parse_mode="Markdown")

    elif data == "browse_search":
        await query.message.reply_text("🔍 Just type what you're looking for and I'll find it!")

    elif data.startswith("order_"):
        product_id = int(data.split("_")[1])
        product = get_book_by_id(product_id)
        if product:
            context.user_data["pending_order"] = product_id
            await query.message.reply_text(
                f"Nice choice! 🔥 *{product['title']}* — ₦{product['price']:,}\n\n"
                "Just tell me your full name and delivery address to place the order.",
                parse_mode="Markdown"
            )

    # ── Admin callbacks
    elif data == "admin_orders" and is_admin:
        res = supabase.table("orders").select("*").eq("status", "pending").order("created_at", desc=True).execute()
        pending = res.data or []
        if not pending:
            await query.message.reply_text("📭 No pending orders.")
            return
        for o in pending[:5]:
            items_text = "\n".join([f"  • {i['title']} x{i['quantity']}" for i in o["items"]])
            keyboard = [
                [InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{o['id']}"),
                 InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{o['id']}")]
            ]
            await query.message.reply_text(
                f"🧾 *Order #{o['id']}*\n"
                f"👤 {o['customer_name']}\n"
                f"📍 {o.get('location', 'N/A')}\n"
                f"{items_text}\n"
                f"💰 ₦{o['total']:,}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif data == "admin_inventory" and is_admin:
        products = supabase.table("books").select("*").order("id").execute().data or []
        for p in products[:10]:
            status = "✅" if p["in_stock"] else "❌"
            keyboard = [
                [InlineKeyboardButton("❌ Out of Stock" if p["in_stock"] else "✅ Restock",
                                      callback_data=f"toggle_{p['id']}"),
                 InlineKeyboardButton("🖼 Add Photo", callback_data=f"addphoto_{p['id']}"),
                 InlineKeyboardButton("🗑 Delete", callback_data=f"delete_{p['id']}")]
            ]
            caption = f"{status} *{p['title']}*\n₦{p['price']:,} | ID: `{p['id']}`"
            image_url = p.get("image_url")
            try:
                if image_url:
                    await query.message.reply_photo(
                        photo=image_url,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await query.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                await query.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_add_product" and is_admin:
        context.user_data["admin_action"] = "add_product"
        await query.message.reply_text(
            "➕ Send product details in this format:\n\n"
            "`Title | Author/Brand | Category | Price`\n\n"
            "Example: `iPhone 15 Pro | Apple | Phones | 1350000`",
            parse_mode="Markdown"
        )

    elif data == "admin_stats" and is_admin:
        from bot import build_admin_data_context
        stats = build_admin_data_context()
        await query.message.reply_text(f"```{stats}```", parse_mode="Markdown")

    elif data.startswith("confirm_") and is_admin:
        order_id = int(data.split("_")[1])
        res = supabase.table("orders").update({"status": "confirmed"}).eq("id", order_id).execute()
        if res.data:
            order = res.data[0]
            await query.message.reply_text(f"✅ Order #{order_id} confirmed!")
            try:
                await context.bot.send_message(
                    chat_id=int(order["telegram_id"]),
                    text=f"🎉 Your order #{order_id} has been confirmed! We'll process it right away. Thank you for shopping with VoltStore! ⚡"
                )
            except Exception:
                pass

    elif data.startswith("cancel_") and is_admin:
        order_id = int(data.split("_")[1])
        supabase.table("orders").update({"status": "cancelled"}).eq("id", order_id).execute()
        await query.message.reply_text(f"🚫 Order #{order_id} cancelled.")

    elif data.startswith("toggle_") and is_admin:
        product_id = int(data.split("_")[1])
        product = get_book_by_id(product_id)
        if product:
            new_status = not product["in_stock"]
            supabase.table("books").update({"in_stock": new_status}).eq("id", product_id).execute()
            status = "✅ back in stock" if new_status else "❌ marked out of stock"
            await query.message.reply_text(f"*{product['title']}* is now {status}.", parse_mode="Markdown")

    elif data.startswith("delete_") and is_admin:
        product_id = int(data.split("_")[1])
        keyboard = [[
            InlineKeyboardButton("Yes, delete", callback_data=f"confirmdelete_{product_id}"),
            InlineKeyboardButton("Cancel", callback_data="admin_inventory")
        ]]
        await query.message.reply_text(
            f"Are you sure you want to delete product ID `{product_id}`?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("confirmdelete_") and is_admin:
        product_id = int(data.split("_")[1])
        supabase.table("books").delete().eq("id", product_id).execute()
        await query.message.reply_text(f"🗑 Product `{product_id}` deleted.", parse_mode="Markdown")

    elif data.startswith("addphoto_") and is_admin:
        product_id = int(data.split("_")[1])
        context.user_data["admin_action"] = "add_photo"
        context.user_data["photo_product_id"] = product_id
        await query.message.reply_text(
            f"🖼 Send a photo for product ID `{product_id}`.\n"
            "Just send the image directly in this chat.",
            parse_mode="Markdown"
        )


# ── Photo handler (for adding product images) ─────────────
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    if context.user_data.get("admin_action") == "add_photo":
        product_id = context.user_data.get("photo_product_id")
        photo = update.message.photo[-1]  # Highest resolution
        file = await context.bot.get_file(photo.file_id)
        image_url = file.file_path  # Telegram CDN URL

        supabase.table("books").update({"image_url": image_url}).eq("id", product_id).execute()
        context.user_data.pop("admin_action", None)
        context.user_data.pop("photo_product_id", None)
        await update.message.reply_text(f"✅ Photo added to product ID `{product_id}`!", parse_mode="Markdown")


# ── Natural language messages ─────────────────────────────
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    # Handle admin add_product flow
    if user_id in ADMIN_IDS and context.user_data.get("admin_action") == "add_product":
        parts = [p.strip() for p in user_message.split("|")]
        if len(parts) == 4:
            title, author, category, price_str = parts
            try:
                price = float(price_str.replace(",", "").replace("₦", "").strip())
                res = supabase.table("books").insert({
                    "title": title, "author": author,
                    "category": category, "price": price, "in_stock": True
                }).execute()
                if res.data:
                    book = res.data[0]
                    context.user_data.pop("admin_action", None)
                    keyboard = [[InlineKeyboardButton("🖼 Add Photo", callback_data=f"addphoto_{book['id']}")]]
                    await update.message.reply_text(
                        f"✅ *{book['title']}* added! ID: `{book['id']}`\n\nWant to add a photo?",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return
            except Exception:
                pass
        await update.message.reply_text("❌ Wrong format. Use: `Title | Brand | Category | Price`", parse_mode="Markdown")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await handle_message(str(user_id), user_message, bot=context.bot)
    await update.message.reply_text(reply, parse_mode="Markdown")


# ── Main ──────────────────────────────────────────────────
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("catalog", catalog))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("cart", cart))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("⚡ VoltStore bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

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
from bot import handle_message, add_to_cart, view_cart, get_admin_ids
from admin import register_admin_handlers
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
    is_admin = user_id in get_admin_ids()

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
    for product in products[:10]:
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
    if update.effective_user.id not in get_admin_ids():
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


# ── /addstock — bulk import iPhone price list ─────────────
async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Bulk-insert the Nigerian used iPhone price list.
    Usage: /addstock iphones
    Only admins can run this.
    """
    if update.effective_user.id not in get_admin_ids():
        await update.message.reply_text("⛔ Access denied.")
        return

    arg = " ".join(context.args).strip().lower()
    if arg != "iphones":
        await update.message.reply_text(
            "Usage: `/addstock iphones` — bulk-import the Nigerian used iPhone price list.",
            parse_mode="Markdown"
        )
        return

    # Nigerian used iPhone prices
    # list_price = upper end of vendor range (starting ask)
    # base_price = lower end of vendor range (negotiation floor — never go below this)
    iphone_list = [
        # (model, storage, list_price=upper, base_price=lower)
        ("iPhone X", "64GB",    200000, 190000),
        ("iPhone X", "256GB",   235000, 220000),
        ("iPhone XR", "64GB",   230000, 220000),
        ("iPhone XR", "128GB",  245000, 230000),
        ("iPhone XR", "256GB",  255000, 240000),
        ("iPhone XS Max", "64GB",   260000, 250000),
        ("iPhone XS Max", "256GB",  290000, 270000),
        ("iPhone 11", "64GB",   270000, 260000),
        ("iPhone 11", "128GB",  310000, 300000),
        ("iPhone 11", "256GB",  340000, 320000),
        ("iPhone 12", "64GB",   320000, 300000),
        ("iPhone 12", "128GB",  360000, 340000),
        ("iPhone 12", "256GB",  390000, 360000),
        ("iPhone 13", "128GB",  470000, 460000),
        ("iPhone 13", "256GB",  490000, 480000),
        ("iPhone 13", "512GB",  510000, 490000),
        ("iPhone 14", "128GB",  580000, 560000),
        ("iPhone 14", "256GB",  630000, 590000),
        ("iPhone 14", "512GB",  670000, 630000),
        ("iPhone 15", "128GB",  750000, 700000),
        ("iPhone 15", "256GB",  800000, 750000),
        ("iPhone 16", "128GB",  1000000,  950000),
        ("iPhone 16", "256GB",  1080000, 1000000),
        ("iPhone 16", "512GB",  1150000, 1080000),
        ("iPhone 17", "256GB",  1869660, 1650000),
        ("iPhone 17", "512GB",  2337660, 2100000),
        ("iPhone 17", "1TB",    3273660, 2900000),
    ]

    await update.message.reply_text(
        f"⏳ Importing {len(iphone_list)} iPhone models... please wait."
    )

    inserted = 0
    skipped = 0
    errors = []

    for (model, storage, list_price, base_price) in iphone_list:
        title = f"{model} {storage}"
        try:
            # Check if already exists to avoid duplicates
            existing = supabase.table("books").select("id").eq("title", title).eq("condition", "Nigeria Used").execute()
            if existing.data:
                skipped += 1
                continue

            res = supabase.table("books").insert({
                "title": title,
                "author": "Apple",
                "category": "Smartphones",
                "price": list_price,
                "list_price": list_price,
                "base_price": base_price,
                "condition": "Nigeria Used",
                "stock_qty": 1,
                "negotiable": True,
                "in_stock": True,
                "specs": f"{storage} storage",
            }).execute()

            if res.data:
                inserted += 1
            else:
                errors.append(title)
        except Exception as e:
            errors.append(f"{title} ({e})")

    summary = f"✅ *Bulk import done!*\n\n📦 Inserted: {inserted}\n⏭ Skipped (already exist): {skipped}"
    if errors:
        summary += f"\n❌ Errors ({len(errors)}): " + ", ".join(errors[:5])
    summary += "\n\nAll iPhones are marked *negotiable* and *Nigeria Used*. Add photos via /admin → Inventory."

    await update.message.reply_text(summary, parse_mode="Markdown")


# ── Callback query handler ────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    is_admin = user_id in get_admin_ids()

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
                f"📞 {o.get('phone_number', 'N/A')}\n"
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
            photo_badge = "📸" if p.get("image_url") else "🚫 No photo"
            caption = f"{status} *{p['title']}*\n₦{p['price']:,} | {photo_badge} | ID: `{p['id']}`"
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
        await query.message.reply_text(
            "➕ Just tell me what product you want to add! Give me the name, brand, category, and price and I'll sort it out."
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
        # Clear last_added so there's no conflict
        context.user_data.pop("last_added_product_id", None)
        await query.message.reply_text(
            f"🖼 Send a photo for product ID `{product_id}`.\n"
            "Just send the image directly in this chat.",
            parse_mode="Markdown"
        )


# ── Photo handler (for adding product images) ─────────────
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in get_admin_ids():
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id

    # Only save if admin explicitly triggered addphoto via the button
    if context.user_data.get("admin_action") == "add_photo":
        product_id = context.user_data.get("photo_product_id")
        supabase.table("books").update({"image_url": file_id}).eq("id", product_id).execute()
        context.user_data.pop("admin_action", None)
        context.user_data.pop("photo_product_id", None)
        product = get_book_by_id(product_id)
        name = product["title"] if product else f"ID {product_id}"
        await update.message.reply_text(
            f"✅ Photo saved for *{name}*! (ID: `{product_id}`)",
            parse_mode="Markdown"
        )
        return

    # Pending photo waiting for a product name / ID to be typed
    if context.user_data.get("pending_photo"):
        # Already waiting for a name — remind admin
        await update.message.reply_text(
            "⏳ Still waiting for the product name or ID for the previous photo. Type it now.",
            parse_mode="Markdown"
        )
        return

    # No active context — store and ask which product
    context.user_data["pending_photo"] = file_id
    await update.message.reply_text(
        "📸 Got the photo! Which product is this for? Type the product name or ID.",
        parse_mode="Markdown"
    )


# ── Natural language messages ─────────────────────────────
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    # Admin: resolve a pending photo by product name or ID
    if user_id in get_admin_ids() and context.user_data.get("pending_photo"):
        file_id = context.user_data.get("pending_photo")

        # Try match by numeric ID first
        matched_product = None
        if user_message.strip().isdigit():
            matched_product = get_book_by_id(int(user_message.strip()))
        else:
            from catalog import search_books
            results = search_books(user_message)
            if results:
                matched_product = results[0]

        if matched_product:
            supabase.table("books").update({"image_url": file_id}).eq("id", matched_product["id"]).execute()
            context.user_data.pop("pending_photo", None)
            await update.message.reply_text(
                f"✅ Photo attached to *{matched_product['title']}*! (ID: `{matched_product['id']}`)",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❓ Couldn't find '{user_message}'. Try a different name or the product ID.",
                parse_mode="Markdown"
            )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await handle_message(str(user_id), user_message, bot=context.bot)

    # Extract ##LASTADDED## marker if present (admin only)
    last_added_id = None
    if "##LASTADDED##" in reply:
        try:
            last_added_id = int(reply.split("##LASTADDED##")[1].strip())
            reply = reply.split("##LASTADDED##")[0].strip()
            # Store in user_data so photo_handler can pick it up
            context.user_data["last_added_product_id"] = last_added_id
        except Exception:
            pass

    await update.message.reply_text(reply, parse_mode="Markdown")

    # Send product photo for customers when bot recommends a specific product
    if user_id not in get_admin_ids():
        await send_relevant_photos(update.message, reply)


# ── Send product photo when bot recommends a product ─────
async def send_relevant_photos(message, reply_text: str):
    """
    Send a photo if the bot's reply mentions an exact product title.
    If the product has no photo, send a brief "photo coming soon" note with an order button.
    Sends at most 1 match per reply.
    """
    try:
        products = get_all_books()
        reply_lower = reply_text.lower()

        best_match = None
        best_match_len = 0

        for product in products:
            title_lower = product["title"].lower()
            if title_lower in reply_lower:
                if len(title_lower) > best_match_len:
                    best_match = product
                    best_match_len = len(title_lower)

        if not best_match:
            return

        keyboard = [[InlineKeyboardButton("🛒 Order This", callback_data=f"order_{best_match['id']}")]]
        neg = " | 💬 Negotiable" if best_match.get("negotiable") else ""
        caption = f"*{best_match['title']}*\n💰 ₦{best_match['price']:,}{neg}"

        image_url = best_match.get("image_url")
        if image_url:
            try:
                await message.reply_photo(
                    photo=image_url,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logger.info(f"Photo sent for product {best_match['id']}: {best_match['title']}")
            except Exception as e:
                logger.error(f"Failed to send photo for product {best_match['id']}: {e}")
                # Fall back to text card
                await message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            # No photo available — send text card with note
            no_photo_caption = (
                f"{caption}\n\n"
                f"📸 _Photo will be sent shortly._\n"
                f"Want to go ahead with the order, or do you have any questions?"
            )
            await message.reply_text(
                no_photo_caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"No photo for product {best_match['id']} — sent no-photo card")

    except Exception as e:
        logger.error(f"send_relevant_photos error: {e}")


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
    app.add_handler(CommandHandler("addstock", addstock))
    register_admin_handlers(app)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("⚡ VoltStore bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

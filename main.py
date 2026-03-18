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


# ── Callback query handler ────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    is_admin = user_id in get_admin_ids()

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

    # Determine which product to attach the photo to
    product_id = None

    # Priority 1: admin clicked "Add Photo" button from inventory
    if context.user_data.get("admin_action") == "add_photo":
        product_id = context.user_data.get("photo_product_id")

    # Priority 2: admin just added a product via chat (##LASTADDED## flow)
    elif context.user_data.get("last_added_product_id"):
        product_id = context.user_data.get("last_added_product_id")

    if not product_id:
        await update.message.reply_text(
            "❓ Not sure which product this photo is for.\n"
            "Use the 🖼 Add Photo button from inventory, or add a product first."
        )
        return

    await update.message.reply_text("⏳ Uploading photo to Supabase...")

    try:
        # Step 1: Get highest resolution photo from Telegram
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)

        # Step 2: Download image bytes from Telegram
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(tg_file.file_path)
            image_bytes = response.content

        # Step 3: Upload to Supabase Storage bucket "product-images"
        file_name = f"products/{product_id}_{photo.file_unique_id}.jpg"
        supabase.storage.from_("product-images").upload(
            path=file_name,
            file=image_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"}
        )

        # Step 4: Get the public URL
        public_url = supabase.storage.from_("product-images").get_public_url(file_name)

        # Step 5: Save the public URL to the books table
        supabase.table("books").update({"image_url": public_url}).eq("id", product_id).execute()

        # Clean up context flags
        context.user_data.pop("admin_action", None)
        context.user_data.pop("photo_product_id", None)
        context.user_data.pop("last_added_product_id", None)

        await update.message.reply_text(
            f"✅ Photo uploaded for product ID `{product_id}`!\n\n"
            f"🔗 `{public_url}`",
            parse_mode="Markdown"
        )
        logger.info(f"Photo uploaded for product {product_id}: {public_url}")

    except Exception as e:
        logger.error(f"Photo upload failed for product {product_id}: {e}")
        await update.message.reply_text(f"❌ Upload failed: {e}")


# ── Natural language messages ─────────────────────────────
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    # Handle pending photo attachment (admin typed product name after sending photo)
    if user_id in get_admin_ids() and context.user_data.get("pending_photo"):
        from catalog import search_books
        results = search_books(user_message)
        if results:
            product = results[0]
            file_id = context.user_data.pop("pending_photo")
            supabase.table("books").update({"image_url": file_id}).eq("id", product["id"]).execute()
            await update.message.reply_text(
                f"✅ Photo attached to *{product['title']}*!",
                parse_mode="Markdown"
            )
            return
        else:
            await update.message.reply_text(
                f"❓ Couldn't find '{user_message}'. Try a different name.",
                parse_mode="Markdown"
            )
            return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await handle_message(str(user_id), user_message, bot=context.bot)

    # Extract ##LASTADDED## marker if present — store product ID for next photo upload
    last_added_id = None
    if "##LASTADDED##" in reply:
        try:
            last_added_id = int(reply.split("##LASTADDED##")[1].strip())
            reply = reply.split("##LASTADDED##")[0].strip()
            context.user_data["last_added_product_id"] = last_added_id
        except Exception:
            pass

    # Send reply text
    await update.message.reply_text(reply, parse_mode="Markdown")

    # Proactively send product photos if bot mentioned specific products (customers only)
    if user_id not in get_admin_ids():
        await send_relevant_photos(update.message, reply, bot=context.bot)


# ── Send product photos based on bot reply ───────────────
async def send_relevant_photos(message, reply_text: str, bot=None):
    """Scan bot reply for product names and send their photos if available."""
    try:
        products = get_all_books()
        sent = set()
        for product in products:
            title_lower = product["title"].lower()
            reply_lower = reply_text.lower()
            image_url = product.get("image_url")
            if not image_url:
                continue
            # Match any significant word of product title in reply
            title_words = [w for w in title_lower.split() if len(w) > 3]
            if not any(w in reply_lower for w in title_words):
                continue
            if product["id"] in sent:
                continue

            keyboard = [[InlineKeyboardButton("🛒 Order This", callback_data=f"order_{product['id']}")]]
            title = product["title"]
            price = product["price"]
            neg = " | 💬 Negotiable" if product.get("negotiable") else ""
            caption = f"*{title}*\n💰 ₦{price:,}{neg}"

            try:
                await message.reply_photo(
                    photo=image_url,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                sent.add(product["id"])
                logger.info(f"Photo sent for product {product['id']}: {image_url[:50]}")
            except Exception as e:
                logger.error(f"Failed to send photo for product {product['id']}: {e}")

            if len(sent) >= 3:
                break
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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("⚡ VoltStore bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

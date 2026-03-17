import os
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from supabase_client import supabase
from orders import get_orders_by_user, format_order_summary

# ── Admin IDs (add more as needed) ───────────────────────
ADMIN_IDS = [5851987998]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_only(func):
    """Decorator to restrict commands to admins only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ You don't have permission to use this command.")
            return
        return await func(update, context)
    return wrapper


# ── /admin ────────────────────────────────────────────────
@admin_only
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *Admin Panel — Cupabooks*\n\n"
        "*Inventory:*\n"
        "• `/addbook <title> | <author> | <category> | <price>` — Add a book\n"
        "• `/outofstock <id>` — Mark book as out of stock\n"
        "• `/restock <id>` — Mark book back in stock\n"
        "• `/deletebook <id>` — Delete a book permanently\n"
        "• `/books` — List all books (including out of stock)\n\n"
        "*Orders:*\n"
        "• `/pending` — View all pending orders\n"
        "• `/confirm <order_id>` — Confirm a manual payment\n"
        "• `/cancelorder <order_id>` — Cancel an order\n",
        parse_mode="Markdown"
    )


# ── /addbook ──────────────────────────────────────────────
@admin_only
async def add_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /addbook Title | Author | Category | Price"""
    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) != 4:
        await update.message.reply_text(
            "❌ Wrong format.\n"
            "Usage: `/addbook Title | Author | Category | Price`\n"
            "Example: `/addbook Shoe Dog | Phil Knight | Business | 6500`",
            parse_mode="Markdown"
        )
        return

    title, author, category, price_str = parts

    try:
        price = float(price_str.replace(",", "").replace("₦", "").strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid price. Use numbers only, e.g. `6500`", parse_mode="Markdown")
        return

    response = supabase.table("books").insert({
        "title": title,
        "author": author,
        "category": category,
        "price": price,
        "in_stock": True
    }).execute()

    if response.data:
        book = response.data[0]
        await update.message.reply_text(
            f"✅ Book added!\n\n"
            f"📚 *{book['title']}*\n"
            f"✍️ {book['author']}\n"
            f"📂 {book['category']}\n"
            f"💰 ₦{book['price']:,.0f}\n"
            f"🆔 ID: `{book['id']}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Failed to add book. Try again.")


# ── /outofstock ───────────────────────────────────────────
@admin_only
async def out_of_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/outofstock <book_id>`", parse_mode="Markdown")
        return

    try:
        book_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid book ID.")
        return

    response = supabase.table("books").update({"in_stock": False}).eq("id", book_id).execute()

    if response.data:
        await update.message.reply_text(f"✅ Book ID `{book_id}` marked as out of stock.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Book ID `{book_id}` not found.")


# ── /restock ──────────────────────────────────────────────
@admin_only
async def restock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/restock <book_id>`", parse_mode="Markdown")
        return

    try:
        book_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid book ID.")
        return

    response = supabase.table("books").update({"in_stock": True}).eq("id", book_id).execute()

    if response.data:
        await update.message.reply_text(f"✅ Book ID `{book_id}` is back in stock.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Book ID `{book_id}` not found.")


# ── /deletebook ───────────────────────────────────────────
@admin_only
async def delete_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/deletebook <book_id>`", parse_mode="Markdown")
        return

    try:
        book_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid book ID.")
        return

    response = supabase.table("books").delete().eq("id", book_id).execute()

    if response.data:
        await update.message.reply_text(f"🗑 Book ID `{book_id}` deleted permanently.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Book ID `{book_id}` not found.")


# ── /books (admin view - all books incl out of stock) ─────
@admin_only
async def admin_list_books(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = supabase.table("books").select("*").order("id").execute()
    books = response.data or []

    if not books:
        await update.message.reply_text("No books in the database.")
        return

    lines = []
    for b in books:
        status = "✅" if b["in_stock"] else "❌"
        lines.append(f"{status} `{b['id']}` | *{b['title']}* — ₦{b['price']:,.0f}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /pending ──────────────────────────────────────────────
@admin_only
async def pending_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = (
        supabase.table("orders")
        .select("*")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .execute()
    )
    orders = response.data or []

    if not orders:
        await update.message.reply_text("📭 No pending orders.")
        return

    for order in orders[:10]:
        items_text = "\n".join(
            [f"  • {i['title']} x{i['quantity']} — ₦{i['price']:,}" for i in order["items"]]
        )
        text = (
            f"🧾 *Order #{order['id']}*\n"
            f"👤 {order['customer_name']} (TG: `{order['telegram_id']}`)\n"
            f"{items_text}\n"
            f"💰 Total: ₦{order['total']:,}\n"
            f"🕐 {order['created_at'][:16]}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")


# ── /confirm ──────────────────────────────────────────────
@admin_only
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/confirm <order_id>`", parse_mode="Markdown")
        return

    try:
        order_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid order ID.")
        return

    response = supabase.table("orders").update({"status": "confirmed"}).eq("id", order_id).execute()

    if response.data:
        order = response.data[0]
        await update.message.reply_text(
            f"✅ Order #{order_id} confirmed!\n"
            f"Customer TG ID: `{order['telegram_id']}`",
            parse_mode="Markdown"
        )
        # Notify customer
        try:
            await context.bot.send_message(
                chat_id=int(order["telegram_id"]),
                text=f"🎉 Your order #{order_id} has been confirmed! We'll process it right away. Thank you for shopping with Cupabooks! 📚"
            )
        except Exception:
            pass  # Customer may have blocked the bot
    else:
        await update.message.reply_text(f"❌ Order #{order_id} not found.")


# ── /cancelorder ──────────────────────────────────────────
@admin_only
async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/cancelorder <order_id>`", parse_mode="Markdown")
        return

    try:
        order_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid order ID.")
        return

    response = supabase.table("orders").update({"status": "cancelled"}).eq("id", order_id).execute()

    if response.data:
        await update.message.reply_text(f"🚫 Order #{order_id} cancelled.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Order #{order_id} not found.")


# ── Register all admin handlers ───────────────────────────
def register_admin_handlers(app):
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler("addbook", add_book))
    app.add_handler(CommandHandler("outofstock", out_of_stock))
    app.add_handler(CommandHandler("restock", restock))
    app.add_handler(CommandHandler("deletebook", delete_book))
    app.add_handler(CommandHandler("books", admin_list_books))
    app.add_handler(CommandHandler("pending", pending_orders))
    app.add_handler(CommandHandler("confirm", confirm_order))
    app.add_handler(CommandHandler("cancelorder", cancel_order))

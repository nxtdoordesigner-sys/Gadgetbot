import os
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from supabase_client import supabase
from orders import get_orders_by_user, format_order_summary
from bot import notify_order_confirmed, get_admin_ids


def is_admin(user_id: int) -> bool:
    # Single source of truth — always reads from Supabase via get_admin_ids()
    return user_id in get_admin_ids()


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
        "🛠 *Admin Panel — VoltStore*\n\n"
        "*Inventory:*\n"
        "• `/addproduct <name> | <brand> | <category> | <price>` — Add a product\n"
        "• `/outofstock <id>` — Mark product as out of stock\n"
        "• `/restock <id>` — Mark product back in stock\n"
        "• `/deleteproduct <id>` — Delete a product permanently\n"
        "• `/products` — List all products (including out of stock)\n\n"
        "*Orders:*\n"
        "• `/pending` — View all pending orders\n"
        "• `/confirm <order_id>` — Confirm a manual payment\n"
        "• `/cancelorder <order_id>` — Cancel an order\n",
        parse_mode="Markdown"
    )


# ── /addproduct ───────────────────────────────────────────
@admin_only
async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /addproduct Name | Brand | Category | Price"""
    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) != 4:
        await update.message.reply_text(
            "❌ Wrong format.\n"
            "Usage: `/addproduct Name | Brand | Category | Price`\n"
            "Example: `/addproduct iPhone 15 | Apple | Smartphones | 950000`",
            parse_mode="Markdown"
        )
        return

    name, brand, category, price_str = parts

    try:
        price = float(price_str.replace(",", "").replace("₦", "").strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid price. Use numbers only, e.g. `950000`", parse_mode="Markdown")
        return

    response = supabase.table("books").insert({
        "title": name,
        "author": brand,
        "category": category,
        "price": price,
        "list_price": price,
        "base_price": price * 0.85,
        "in_stock": True,
        "stock_qty": 1,
        "negotiable": False,
        "condition": "Brand New"
    }).execute()

    if response.data:
        product = response.data[0]
        await update.message.reply_text(
            f"✅ Product added!\n\n"
            f"📱 *{product['title']}*\n"
            f"🏷️ {product['author']}\n"
            f"📂 {product['category']}\n"
            f"💰 ₦{product['price']:,.0f}\n"
            f"🆔 ID: `{product['id']}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Failed to add product. Try again.")


# ── /outofstock ───────────────────────────────────────────
@admin_only
async def out_of_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/outofstock <product_id>`", parse_mode="Markdown")
        return

    try:
        product_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid product ID.")
        return

    response = supabase.table("books").update({"in_stock": False, "stock_qty": 0}).eq("id", product_id).execute()

    if response.data:
        await update.message.reply_text(f"✅ Product ID `{product_id}` marked as out of stock.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Product ID `{product_id}` not found.")


# ── /restock ──────────────────────────────────────────────
@admin_only
async def restock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/restock <product_id>`", parse_mode="Markdown")
        return

    try:
        product_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid product ID.")
        return

    response = supabase.table("books").update({"in_stock": True, "stock_qty": 1}).eq("id", product_id).execute()

    if response.data:
        await update.message.reply_text(f"✅ Product ID `{product_id}` is back in stock.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Product ID `{product_id}` not found.")


# ── /deleteproduct ────────────────────────────────────────
@admin_only
async def delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/deleteproduct <product_id>`", parse_mode="Markdown")
        return

    try:
        product_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid product ID.")
        return

    response = supabase.table("books").delete().eq("id", product_id).execute()

    if response.data:
        await update.message.reply_text(f"🗑 Product ID `{product_id}` deleted permanently.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Product ID `{product_id}` not found.")


# ── /products (admin view - all products incl out of stock) ──
@admin_only
async def admin_list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = supabase.table("books").select("*").order("id").execute()
    products = response.data or []

    if not products:
        await update.message.reply_text("No products in the database.")
        return

    lines = []
    for p in products:
        status = "✅" if p["in_stock"] else "❌"
        neg = " 💬" if p.get("negotiable") else ""
        lines.append(f"{status} `{p['id']}` | *{p['title']}* — ₦{p['price']:,.0f}{neg}")

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
            f"📞 {order.get('phone_number', 'N/A')}\n"
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
        await update.message.reply_text(f"✅ Order #{order_id} confirmed!")
        await notify_order_confirmed(order_id, context.bot)
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
    app.add_handler(CommandHandler("addproduct", add_product))
    app.add_handler(CommandHandler("outofstock", out_of_stock))
    app.add_handler(CommandHandler("restock", restock))
    app.add_handler(CommandHandler("deleteproduct", delete_product))
    app.add_handler(CommandHandler("products", admin_list_products))
    app.add_handler(CommandHandler("pending", pending_orders))
    app.add_handler(CommandHandler("confirm", confirm_order))
    app.add_handler(CommandHandler("cancelorder", cancel_order))

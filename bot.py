import os
from datetime import datetime, timezone
from groq import Groq
from catalog import get_all_books, get_book_by_id
from orders import create_order
from supabase_client import supabase
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

ADMIN_IDS = [5851987998]
sessions = {}

CUSTOMER_PROMPT = """
You are Volt, the smart AI sales assistant for VoltStore — a premium Nigerian gadget and electronics store.
Your job is to help customers find the right gadget, answer questions, and place orders.

IMPORTANT RULES:
- Never make up products. Only reference products from the catalog provided below.
- When a customer wants to order, collect in this order: (1) full name, (2) delivery address/location, (3) confirm the products and quantities.
- Once you have all three, output a special line at the END of your reply in this exact format:
  ##ORDER## customer_name | product_id:quantity,product_id:quantity | delivery_address
  Example: ##ORDER## Chidi Okonkwo | 3:1,5:2 | 14 Rumuola Road, Port Harcourt
- Only output ##ORDER## when the customer has explicitly confirmed they want to place the order.
- After outputting ##ORDER##, tell the customer their order has been received and give payment details.

Payment options:
- Bank Transfer: Account Name: VoltStore NG, Bank: GTBank, Account: 0123456789
- Send payment receipt to this chat after transfer.

Delivery: 1-2 business days within your city. Interstate: 3-5 days.
Warranty: All products come with a minimum 6-month VoltStore warranty.

Always be knowledgeable, energetic, and helpful. You know your gadgets well.
Help customers compare products if they're unsure. Recommend based on their budget and needs.
Respond in plain text — only use *bold* for product names and prices.
"""

ADMIN_PROMPT = """
You are Volt, the AI business assistant for VoltStore — a Nigerian gadget store.
You are speaking with an admin/staff member.

You have access to real business data provided below. Use it to answer questions accurately.
Be concise, direct, and professional. Format numbers clearly with ₦ for naira.

You can answer questions about:
- Orders (today, this week, this month, pending, confirmed, cancelled)
- Revenue (daily, weekly, monthly totals)
- Top selling products
- Specific order lookups
- Customer activity
- Inventory status

Always base your answers strictly on the data provided. If data isn't available, say so.
Use markdown formatting — bold key numbers, use bullet points for lists.
"""


def get_session(user_id: str) -> dict:
    if user_id not in sessions:
        sessions[user_id] = {"history": [], "cart": [], "name": ""}
    return sessions[user_id]


def build_catalog_context() -> str:
    products = get_all_books()
    if not products:
        return "No products currently in stock."
    lines = [f"ID:{p['id']} | {p['title']} by {p['author']} | ₦{p['price']:,} | {p.get('category','')}" for p in products]
    return "CURRENT CATALOG:\n" + "\n".join(lines)


def build_admin_data_context() -> str:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    orders_res = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    all_orders = orders_res.data or []

    books_res = supabase.table("books").select("*").execute()
    all_products = books_res.data or []

    today_orders = [o for o in all_orders if o["created_at"][:10] == today]
    pending = [o for o in all_orders if o["status"] == "pending"]
    confirmed = [o for o in all_orders if o["status"] == "confirmed"]
    cancelled = [o for o in all_orders if o["status"] == "cancelled"]

    this_month = now.strftime("%Y-%m")
    month_orders = [o for o in all_orders if o["created_at"][:7] == this_month]
    month_revenue = sum(o["total"] for o in month_orders if o["status"] == "confirmed")
    today_revenue = sum(o["total"] for o in today_orders if o["status"] == "confirmed")
    total_revenue = sum(o["total"] for o in all_orders if o["status"] == "confirmed")

    product_counts = {}
    for order in all_orders:
        for item in order.get("items", []):
            title = item.get("title", "Unknown")
            product_counts[title] = product_counts.get(title, 0) + item.get("quantity", 1)
    top_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    recent = all_orders[:10]
    recent_lines = [
        f"  Order #{o['id']} | {o['customer_name']} | ₦{o['total']:,} | {o['status']} | {o['created_at'][:10]}"
        for o in recent
    ]

    in_stock = len([p for p in all_products if p["in_stock"]])
    out_of_stock = len([p for p in all_products if not p["in_stock"]])

    return f"""
BUSINESS DATA (as of {now.strftime('%Y-%m-%d %H:%M')} UTC):

ORDERS SUMMARY:
- Total orders: {len(all_orders)}
- Today ({today}): {len(today_orders)} orders
- This month ({this_month}): {len(month_orders)} orders
- Pending: {len(pending)}
- Confirmed: {len(confirmed)}
- Cancelled: {len(cancelled)}

REVENUE:
- Today: ₦{today_revenue:,}
- This month: ₦{month_revenue:,}
- All time (confirmed): ₦{total_revenue:,}

TOP SELLING PRODUCTS:
{chr(10).join([f"  {i+1}. {title} — {count} sold" for i, (title, count) in enumerate(top_products)])}

INVENTORY:
- Total products: {len(all_products)}
- In stock: {in_stock}
- Out of stock: {out_of_stock}

RECENT 10 ORDERS:
{chr(10).join(recent_lines) if recent_lines else "  No orders yet"}
"""


def parse_order_signal(reply: str):
    for line in reply.split("\n"):
        if line.strip().startswith("##ORDER##"):
            try:
                data = line.replace("##ORDER##", "").strip()
                parts = [p.strip() for p in data.split("|")]
                customer_name = parts[0]
                items = []
                for item_str in parts[1].strip().split(","):
                    product_id, quantity = item_str.strip().split(":")
                    items.append({"book_id": int(product_id), "quantity": int(quantity)})
                location = parts[2] if len(parts) > 2 else "Not provided"
                return customer_name, items, location
            except Exception:
                return None, None, None
    return None, None, None


async def handle_message(user_id: str, user_message: str, bot=None) -> str:
    session = get_session(user_id)
    is_admin = int(user_id) in ADMIN_IDS

    if is_admin:
        return await handle_admin_message(user_id, user_message, session)
    else:
        return await handle_customer_message(user_id, user_message, session, bot)


async def handle_admin_message(user_id: str, user_message: str, session: dict) -> str:
    admin_data = build_admin_data_context()
    admin_key = f"admin_{user_id}"
    if admin_key not in sessions:
        sessions[admin_key] = {"history": []}
    admin_session = sessions[admin_key]

    admin_session["history"].append({"role": "user", "content": user_message})
    messages = [
        {"role": "system", "content": f"{ADMIN_PROMPT}\n\n{admin_data}"},
        *admin_session["history"][-10:],
    ]

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.3,
        max_tokens=700,
    )

    reply = response.choices[0].message.content.strip()
    admin_session["history"].append({"role": "assistant", "content": reply})
    return reply


async def handle_customer_message(user_id: str, user_message: str, session: dict, bot=None) -> str:
    catalog_context = build_catalog_context()
    session["history"].append({"role": "user", "content": user_message})

    messages = [
        {"role": "system", "content": f"{CUSTOMER_PROMPT}\n\n{catalog_context}"},
        *session["history"][-10:],
    ]

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.7,
        max_tokens=600,
    )

    reply = response.choices[0].message.content.strip()
    session["history"].append({"role": "assistant", "content": reply})

    customer_name, order_items, location = parse_order_signal(reply)
    if customer_name and order_items:
        await save_order(user_id, customer_name, order_items, bot, location)
        clean_reply = "\n".join(
            line for line in reply.split("\n")
            if not line.strip().startswith("##ORDER##")
        ).strip()
        return clean_reply

    return reply


async def save_order(user_id: str, customer_name: str, items: list, bot=None, location: str = "Not provided"):
    enriched_items = []
    total = 0

    for item in items:
        product = get_book_by_id(item["book_id"])
        if product:
            enriched_items.append({
                "book_id": product["id"],
                "title": product["title"],
                "quantity": item["quantity"],
                "price": product["price"],
            })
            total += product["price"] * item["quantity"]

    if not enriched_items:
        return None

    order = create_order(
        customer_name=customer_name,
        telegram_id=user_id,
        items=enriched_items,
        total=total,
        location=location,
    )

    if order and bot:
        items_text = "\n".join(
            [f"  • {i['title']} x{i['quantity']} — ₦{i['price']:,}" for i in enriched_items]
        )
        admin_msg = (
            f"🛎 *New Order #{order['id']}!*\n\n"
            f"👤 *{customer_name}*\n"
            f"📱 TG ID: `{user_id}`\n\n"
            f"{items_text}\n\n"
            f"💰 Total: ₦{total:,}\n"
            f"📍 Delivery: {location}\n\n"
            f"Use `/confirm {order['id']}` to confirm after payment."
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown")
            except Exception:
                pass

    return order


async def add_to_cart(user_id: str, product_id: int, quantity: int = 1) -> str:
    session = get_session(user_id)
    product = get_book_by_id(product_id)

    if not product:
        return f"❌ Product with ID {product_id} not found."

    for item in session["cart"]:
        if item["book_id"] == product_id:
            item["quantity"] += quantity
            return f"✅ Updated cart: *{product['title']}* x{item['quantity']}"

    session["cart"].append({
        "book_id": product["id"],
        "title": product["title"],
        "quantity": quantity,
        "price": product["price"],
    })

    return f"✅ Added to cart: *{product['title']}* — ₦{product['price']:,}"


def view_cart(user_id: str) -> str:
    session = get_session(user_id)
    cart = session.get("cart", [])

    if not cart:
        return "🛒 Your cart is empty."

    lines = [f"  • {i['title']} x{i['quantity']} — ₦{i['price'] * i['quantity']:,}" for i in cart]
    total = sum(i["price"] * i["quantity"] for i in cart)
    return "🛒 *Your Cart:*\n" + "\n".join(lines) + f"\n\n💰 Total: ₦{total:,}"

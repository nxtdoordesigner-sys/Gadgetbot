import os
import asyncio
from reports import generate_report
from datetime import datetime, timezone
import google.generativeai as genai
from catalog import get_all_books, get_book_by_id
from orders import create_order
from supabase_client import supabase
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
PAYSTACK_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")

sessions = {}
SESSION_TIMEOUT_MINUTES = 30


def get_admin_ids() -> list:
    try:
        res = supabase.table("admins").select("telegram_id").execute()
        return [int(a["telegram_id"]) for a in (res.data or [])]
    except Exception:
        return [5851987998]


CUSTOMER_PROMPT = """
You are Volt, AI sales assistant for VoltStore — a Nigerian gadget store.
You have full access to the product catalog provided below.

PERSONALITY:
- Sound like a knowledgeable friend, not a bot
- Match customer energy — if they're casual, be casual
- Use natural Nigerian expressions (e.g. "sharp sharp", "no wahala", "e go be")
- Keep replies short — 2-3 sentences max unless explaining specs
- Never be robotic or formal

BUDGET-FIRST APPROACH:
- When a customer asks for a product type (e.g. "I want a phone"), ALWAYS ask their budget first
- Use budget to filter and recommend from catalog
- If their budget is below all options, tell them honestly and show closest option
- If budget fits multiple options, show top 2-3 and let them choose

NEGOTIATION (for products marked NEGOTIABLE in catalog):
- You can negotiate price — stay between list_price and base_price (floor)
- If customer asks for discount: make them feel special, offer ₦5-10k off first
- If they push: meet somewhere fair in the middle
- If they go below base_price: hold firm warmly ("I wan help you but e no go work below this price o")
- Never tell customer what the base_price is
- For NON-NEGOTIABLE products: politely say price is fixed, offer alternatives if they complain

OUT OF STOCK:
- If product is out of stock, say so immediately
- Suggest similar alternatives from catalog based on category and price range
- Never recommend something way outside their budget unless you explain why

PHOTOS:
- ONLY mention a product photo ONCE per conversation — the first time you recommend or describe that product
- After that, NEVER reference or trigger the photo again even if you mention the product again
- If a customer explicitly asks "can I see a picture?" or "send me photo" — mention the product name clearly so the photo sends
- Do NOT say "photo is attached" or "here's the photo" on every message — say it only the first time

ORDER FLOW — follow this STRICTLY, one step at a time, no skipping:

STEP 1 — PRODUCT CONFIRMATION:
When customer shows interest in buying, confirm exactly which product and quantity.
Do NOT ask for name or address yet.

STEP 2 — LOCATION CHECK:
Ask: "Are you in Port Harcourt or another state?"
- If Port Harcourt: ask if they want DELIVERY or PICKUP
  - Pickup address: A16 Everyday Plaza, Choba, Port Harcourt
  - Delivery: collect their full address
- If another state: tell them we do interstate delivery and ask for their full address

STEP 3 — FULL NAME:
Ask ONLY for their full name. Nothing else.

STEP 4 — PHONE NUMBER:
Ask ONLY for their phone number. Nothing else.

STEP 5 — ORDER SUMMARY:
Show a clean summary:
  Product, quantity, agreed price
  Delivery/Pickup address
  Name, phone
Then ask: "Shall I confirm this order?"

STEP 6 — AFTER CONFIRMATION:
Output at END of reply (hidden from customer view):
##ORDER## customer_name | product_id:quantity:agreed_price | delivery_address | phone_number

For pickup orders, use "Pickup — A16 Everyday Plaza, Choba, PH" as the delivery_address.
Use list_price as agreed_price if no negotiation happened.

IMPORTANT:
- Never ask for name and address in the same message
- Never skip steps
- Never ask for payment before confirming the order
- If customer goes off-topic mid-order, gently bring them back to the current step

PAYMENT (after order confirmed):
- Bank Transfer: GTBank — VoltStore NG, Acct: 0123456789. Send receipt here.
- For card payment: type "pay with card"

SHOP INFO:
- Pickup address: A16 Everyday Plaza, Choba, Port Harcourt
- If customer asks for shop location or address, give them the above

Only reference products from the catalog. Never make up products or prices.
"""


ADMIN_PROMPT = """
You are Volt, smart AI business assistant for VoltStore.
You're chatting with store admin. Be helpful, conversational, and proactive.

PERSONALITY:
- Talk like a smart business partner
- Be concise but thorough
- Proactively ask follow-up questions when info is missing
- Confirm actions before executing

WHAT YOU CAN DO:
1. Add/update/remove products conversationally
2. Update prices, stock, negotiation settings
3. Mark orders as delivered — triggers rating request to customer
4. Broadcast messages to all customers
5. Answer business questions (orders, revenue, stats)
6. Add/remove admins
7. Attach photos to products by name or ID

ADDING PRODUCTS:
Collect: name, brand, category, price, condition, stock_qty, negotiable (always ask), specs (optional)
Then output: ##ADDPRODUCT## name | brand | category | price | condition | stock_qty | negotiable | base_price | specs

UPDATING PRODUCTS:
##UPDATEPRODUCT## product_id | field | new_value

REMOVING PRODUCTS:
##REMOVEPRODUCT## product_id

ADDING PRODUCT PHOTO:
When admin says anything like:
- "add photo for iPhone 11"
- "I want to add pics for id 5"
- "attach image to Samsung Galaxy"
- "add picture for the laptop"
- "send photo for product 3"

Look up the product name or ID from the catalog, find its ID, then output:
##ADDPHOTO## product_id

Use the product ID (number), never the name, in the signal.
After outputting the signal, tell admin: "Go ahead, send the photo! 📸"

MARKING ORDER DELIVERED:
When admin says "[product] delivered to [customer name]" or "confirm delivery of order #X":
##DELIVERED## order_id

BROADCASTING:
When admin wants to send message to all customers:
##BROADCAST## message text here

ADDING ADMIN:
##ADDADMIN## telegram_id | name

REPORTS (admin can trigger these by saying):
- "send me the orders report"
- "send inventory sheet"
- "send revenue report"
- "send customer list"
- "send low stock report"
- "send full report" (all sheets)

Base answers on business data provided.
"""


def get_session(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    if user_id not in sessions:
        sessions[user_id] = {"history": [], "cart": [], "name": "", "last_active": now, "photos_sent": set()}
    else:
        last = sessions[user_id].get("last_active", now)
        if (now - last).total_seconds() > SESSION_TIMEOUT_MINUTES * 60:
            sessions[user_id] = {"history": [], "cart": [], "name": "", "last_active": now, "photos_sent": set()}
        else:
            sessions[user_id]["last_active"] = now
            if "photos_sent" not in sessions[user_id]:
                sessions[user_id]["photos_sent"] = set()
    return sessions[user_id]


def reset_session(user_id: str):
    sessions[user_id] = {
        "history": [], "cart": [], "name": "",
        "last_active": datetime.now(timezone.utc),
        "photos_sent": set()
    }


def build_catalog_context() -> str:
    products = get_all_books()
    if not products:
        return "No products currently in stock."
    lines = []
    for p in products:
        negotiable_info = f" | NEGOTIABLE (floor: ₦{p['base_price']:,})" if p.get("negotiable") and p.get("base_price") else ""
        stock = p.get("stock_qty", 1)
        condition = p.get("condition", "Brand New")
        specs = p.get("specs", "")
        lines.append(
            f"ID:{p['id']} | {p['title']} | {p['author']} | ₦{p['price']:,} | "
            f"{p.get('category','')} | {condition} | Stock:{stock}{negotiable_info}"
            + (f" | {specs}" if specs else "")
        )
    return "CURRENT CATALOG:\n" + "\n".join(lines)


def build_admin_data_context() -> str:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    orders_res = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    all_orders = orders_res.data or []
    products_res = supabase.table("books").select("*").execute()
    all_products = products_res.data or []

    today_orders = [o for o in all_orders if o["created_at"][:10] == today]
    pending = [o for o in all_orders if o["status"] == "pending"]
    confirmed = [o for o in all_orders if o["status"] == "confirmed"]
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
    low_stock = [p for p in all_products if p.get("stock_qty", 1) <= 2 and p["in_stock"]]

    recent = all_orders[:5]
    recent_lines = [
        f"  #{o['id']} | {o['customer_name']} | {o.get('location','N/A')} | ₦{o['total']:,} | {o['status']}"
        for o in recent
    ]

    return f"""
BUSINESS DATA ({now.strftime('%Y-%m-%d %H:%M')} UTC):
Orders today: {len(today_orders)} | This month: {len(month_orders)} | Pending: {len(pending)} | Confirmed: {len(confirmed)}
Revenue today: ₦{today_revenue:,} | This month: ₦{month_revenue:,} | All time: ₦{total_revenue:,}
In stock: {len([p for p in all_products if p['in_stock']])} | Out of stock: {len([p for p in all_products if not p['in_stock']])}
Low stock (≤2): {', '.join([p['title'] for p in low_stock]) or 'none'}
Top products: {', '.join([f"{t}({c})" for t,c in top_products]) or 'none yet'}
Recent orders:
{chr(10).join(recent_lines) or '  None yet'}
"""


def parse_signal(reply: str, signal: str):
    for line in reply.split("\n"):
        if line.strip().startswith(f"##{signal}##"):
            return line.replace(f"##{signal}##", "").strip()
    return None


def clean_reply(reply: str, signals: list) -> str:
    lines = reply.split("\n")
    cleaned = [l for l in lines if not any(l.strip().startswith(f"##{s}##") for s in signals)]
    return "\n".join(cleaned).strip()


def parse_order_signal(reply: str):
    data = parse_signal(reply, "ORDER")
    if not data:
        return None, None, None, None, None
    try:
        parts = [p.strip() for p in data.split("|")]
        customer_name = parts[0]
        items = []
        agreed_prices = {}
        for item_str in parts[1].strip().split(","):
            item_parts = item_str.strip().split(":")
            product_id = int(item_parts[0])
            quantity = int(item_parts[1])
            agreed_price = float(item_parts[2]) if len(item_parts) > 2 else None
            items.append({"book_id": product_id, "quantity": quantity})
            if agreed_price:
                agreed_prices[product_id] = agreed_price
        location = parts[2] if len(parts) > 2 else None
        phone = parts[3] if len(parts) > 3 else None
        return customer_name, items, location, phone, agreed_prices
    except Exception:
        return None, None, None, None, None


def resolve_product_from_signal(value: str):
    value = value.strip()
    if value.isdigit():
        return get_book_by_id(int(value))
    all_products = get_all_books()
    value_lower = value.lower()
    for p in all_products:
        if p["title"].lower() == value_lower:
            return p
    for p in all_products:
        if value_lower in p["title"].lower():
            return p
    return None


def _call_gemini(system_prompt: str, history: list, temperature: float = 0.7, max_tokens: int = 500) -> str:
    """
    Calls Gemini 1.5 Flash with a system prompt and conversation history.
    History format: [{"role": "user"/"assistant", "content": "..."}]
    Returns the reply text.
    """
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
    )

    # Convert history to Gemini format
    # Gemini uses "user" and "model" roles (not "assistant")
    gemini_history = []
    for msg in history[:-1]:  # all but last message
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_history.append({"role": role, "parts": [msg["content"]]})

    chat = model.start_chat(history=gemini_history)

    # Send the last user message
    last_message = history[-1]["content"] if history else ""
    response = chat.send_message(last_message)
    return response.text.strip()


async def handle_message(user_id: str, user_message: str, bot=None) -> str:
    admin_ids = get_admin_ids()
    session = get_session(user_id)
    is_admin = int(user_id) in admin_ids

    if any(w in user_message.lower() for w in ["start over", "reset", "cancel everything"]):
        reset_session(user_id)
        return "No wahala! 😊 We're starting fresh. What can I help you with?"

    if "my order" in user_message.lower() and "status" in user_message.lower():
        return await get_order_status(user_id)

    if "pay with card" in user_message.lower():
        return (
            "To pay with card, use this Paystack link:\n"
            f"https://paystack.com/pay/voltstore\n\n"
            "After payment, screenshot your receipt and send it here so we can confirm your order quickly ⚡"
        )

    if is_admin:
        return await handle_admin_message(user_id, user_message, session, bot, admin_ids)
    else:
        return await handle_customer_message(user_id, user_message, session, bot)


async def get_order_status(user_id: str) -> str:
    res = supabase.table("orders").select("*").eq("telegram_id", str(user_id)).order("created_at", desc=True).limit(1).execute()
    if not res.data:
        return "I don't see any orders from you yet. Want to shop? 😊"
    order = res.data[0]
    status_map = {
        "pending": "⏳ Pending payment confirmation",
        "confirmed": "✅ Confirmed — being prepared for delivery",
        "delivered": "📦 Delivered!",
        "cancelled": "❌ Cancelled"
    }
    status = status_map.get(order["status"], order["status"])
    items_text = ", ".join([f"{i['title']} x{i['quantity']}" for i in order.get("items", [])])
    return (
        f"📦 *Your latest order (#{order['id']}):*\n\n"
        f"Items: {items_text}\n"
        f"Total: ₦{order['total']:,}\n"
        f"Status: {status}\n"
        f"Delivery: {order.get('location', 'N/A')}"
    )


async def handle_admin_message(user_id: str, user_message: str, session: dict, bot=None, admin_ids=[]) -> str:
    admin_data = build_admin_data_context()
    catalog_context = build_catalog_context()
    admin_key = f"admin_{user_id}"
    if admin_key not in sessions:
        sessions[admin_key] = {"history": []}
    admin_session = sessions[admin_key]
    admin_session["history"].append({"role": "user", "content": user_message})

    msg_lower = user_message.lower()

    if msg_lower.startswith("show me ") or msg_lower.startswith("show "):
        query = msg_lower.replace("show me ", "").replace("show ", "").strip()
        from catalog import search_books
        results = search_books(query)
        if results:
            lines = []
            for p in results[:5]:
                neg = " | 💬 Negotiable" if p.get("negotiable") else ""
                stock = p.get("stock_qty", 0)
                title = p["title"]
                pid = p["id"]
                price = p["price"]
                condition = p.get("condition", "Brand New")
                lines.append(
                    f"*{title}* (ID: {pid})\n"
                    f"  💰 ₦{price:,}{neg}\n"
                    f"  📦 Stock: {stock} | 🔧 {condition}"
                )
            return "\n\n".join(lines)
        return f"No products found matching '{query}'."

    photo_triggers = ["i have the picture", "i have the photo", "i have pictures",
                      "sending the picture", "sending the photo", "ready to send",
                      "i have it", "here's the pic", "here is the pic"]
    if any(t in msg_lower for t in photo_triggers):
        return "Go ahead, send it! 📸"

    report_map = {
        "orders report": "orders",
        "inventory sheet": "inventory",
        "revenue report": "revenue",
        "customer list": "customers",
        "low stock": "lowstock",
        "full report": "full",
        "send me the report": "full",
        "send report": "full",
    }
    for trigger, rtype in report_map.items():
        if trigger in msg_lower:
            if bot:
                try:
                    fpath = generate_report(rtype)
                    await bot.send_document(
                        chat_id=int(user_id),
                        document=open(fpath, "rb"),
                        filename=f"VoltStore_{rtype.capitalize()}_Report.xlsx",
                        caption=f"📊 Here's your {rtype} report! Generated just now."
                    )
                    return f"📊 {rtype.capitalize()} report sent!"
                except Exception as e:
                    return f"❌ Error generating report: {e}"

    system_content = (
        f"{ADMIN_PROMPT}\n\n"
        f"=== BUSINESS STATS ===\n{admin_data}\n\n"
        f"=== FULL PRODUCT CATALOG ===\n{catalog_context}\n\n"
        f"Use the catalog above to answer ANY questions about products, prices, stock, categories etc."
    )

    try:
        reply = _call_gemini(system_content, admin_session["history"][-12:], temperature=0.4, max_tokens=800)
    except Exception as e:
        admin_session["history"].pop()
        err = str(e).lower()
        if "quota" in err or "rate" in err or "429" in err:
            return "⚡ Gemini rate limit hit. Try again in a moment!"
        return f"😔 AI error: {e}"

    admin_session["history"].append({"role": "assistant", "content": reply})

    addphoto_data = parse_signal(reply, "ADDPHOTO")
    if addphoto_data:
        product = resolve_product_from_signal(addphoto_data)
        if product:
            clean = clean_reply(reply, ["ADDPHOTO"])
            return clean + f"\n##ADDPHOTO##{product['id']}"
        else:
            return clean_reply(reply, ["ADDPHOTO"]) + f"\n\n❓ Couldn't find a product matching '{addphoto_data}'. Try the exact name or ID."

    add_data = parse_signal(reply, "ADDPRODUCT")
    if add_data:
        try:
            parts = [p.strip() for p in add_data.split("|")]
            name, brand, category = parts[0], parts[1], parts[2]
            price = float(parts[3].replace(",","").replace("₦",""))
            condition = parts[4] if len(parts) > 4 else "Brand New"
            stock_qty = int(parts[5]) if len(parts) > 5 and parts[5] else 1
            negotiable = parts[6].lower() in ["true", "yes", "1"] if len(parts) > 6 else False
            base_price = float(parts[7].replace(",","").replace("₦","")) if len(parts) > 7 and parts[7] else price * 0.85
            specs = parts[8] if len(parts) > 8 else None
            res = supabase.table("books").insert({
                "title": name, "author": brand, "category": category,
                "price": price, "list_price": price, "base_price": base_price,
                "condition": condition, "stock_qty": stock_qty,
                "negotiable": negotiable, "in_stock": True, "specs": specs
            }).execute()
            if res.data:
                new_id = res.data[0]['id']
                suffix = f"\n\n✅ *{name}* added!\n\nNow send me the product photos and I'll attach them automatically 📸"
                return clean_reply(reply, ["ADDPRODUCT"]) + suffix + f"##LASTADDED##{new_id}"
            return clean_reply(reply, ["ADDPRODUCT"]) + "\n\n❌ Failed to add."
        except Exception as e:
            return clean_reply(reply, ["ADDPRODUCT"]) + f"\n\n❌ Error: {e}"

    update_data = parse_signal(reply, "UPDATEPRODUCT")
    if update_data:
        try:
            parts = [p.strip() for p in update_data.split("|")]
            product_id, field, value = int(parts[0]), parts[1], parts[2]
            if field in ["image_url", "image", "photo"]:
                return clean_reply(reply, ["UPDATEPRODUCT"]) + "\n\nSend the photo directly in chat and I'll attach it! 📸"
            if field in ["price", "base_price", "list_price"]:
                value = float(value.replace(",","").replace("₦",""))
            elif field == "stock_qty":
                value = int(value)
                supabase.table("books").update({"in_stock": value > 0}).eq("id", product_id).execute()
            elif field == "negotiable":
                value = value.lower() in ["true", "yes", "1"]
            supabase.table("books").update({field: value}).eq("id", product_id).execute()
            return clean_reply(reply, ["UPDATEPRODUCT"]) + "\n\n✅ Updated!"
        except Exception as e:
            return clean_reply(reply, ["UPDATEPRODUCT"]) + f"\n\n❌ Error: {e}"

    remove_data = parse_signal(reply, "REMOVEPRODUCT")
    if remove_data:
        try:
            supabase.table("books").delete().eq("id", int(remove_data.strip())).execute()
            return clean_reply(reply, ["REMOVEPRODUCT"]) + "\n\n🗑 Product removed."
        except Exception as e:
            return clean_reply(reply, ["REMOVEPRODUCT"]) + f"\n\n❌ Error: {e}"

    delivered_data = parse_signal(reply, "DELIVERED")
    if delivered_data and bot:
        try:
            order_id = int(delivered_data.strip())
            res = supabase.table("orders").update({
                "status": "delivered",
                "delivered_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", order_id).execute()
            if res.data:
                order = res.data[0]
                tg_id = order["telegram_id"]
                customer_name = order["customer_name"]
                items_text = ", ".join([i["title"] for i in order.get("items", [])])
                try:
                    await bot.send_message(
                        chat_id=int(tg_id),
                        text=(
                            f"📦 Hey {customer_name}! Your order has been delivered!\n\n"
                            f"Items: {items_text}\n\n"
                            f"Hope you love it! 🔥 How was your experience shopping with VoltStore?\n\n"
                            f"Reply with a number:\n"
                            f"⭐ 1 - Poor\n⭐⭐ 2 - Fair\n⭐⭐⭐ 3 - Good\n⭐⭐⭐⭐ 4 - Great\n⭐⭐⭐⭐⭐ 5 - Amazing!"
                        )
                    )
                    if str(tg_id) not in sessions:
                        sessions[str(tg_id)] = {"history": [], "cart": [], "name": "", "photos_sent": set()}
                    sessions[str(tg_id)]["awaiting_rating"] = order_id
                except Exception:
                    pass
                return clean_reply(reply, ["DELIVERED"]) + f"\n\n✅ Order #{order_id} marked as delivered. Customer notified and asked for a rating!"
        except Exception as e:
            return clean_reply(reply, ["DELIVERED"]) + f"\n\n❌ Error: {e}"

    broadcast_data = parse_signal(reply, "BROADCAST")
    if broadcast_data and bot:
        try:
            res = supabase.table("orders").select("telegram_id, customer_name").execute()
            orders = res.data or []
            seen = set()
            recipients = []
            for o in orders:
                tid = o["telegram_id"]
                if tid not in seen:
                    seen.add(tid)
                    recipients.append(o)
            sent = 0
            for r in recipients:
                try:
                    await bot.send_message(
                        chat_id=int(r["telegram_id"]),
                        text=f"📢 *VoltStore Update*\n\n{broadcast_data}",
                        parse_mode="Markdown"
                    )
                    sent += 1
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
            supabase.table("broadcasts").insert({
                "message": broadcast_data, "sent_by": str(user_id), "recipient_count": sent
            }).execute()
            return clean_reply(reply, ["BROADCAST"]) + f"\n\n📢 Broadcast sent to {sent} customer(s)!"
        except Exception as e:
            return clean_reply(reply, ["BROADCAST"]) + f"\n\n❌ Error: {e}"

    addadmin_data = parse_signal(reply, "ADDADMIN")
    if addadmin_data:
        try:
            parts = [p.strip() for p in addadmin_data.split("|")]
            tid, name = parts[0], parts[1] if len(parts) > 1 else "Admin"
            supabase.table("admins").insert({"telegram_id": tid, "name": name}).execute()
            return clean_reply(reply, ["ADDADMIN"]) + f"\n\n✅ {name} added as admin!"
        except Exception as e:
            return clean_reply(reply, ["ADDADMIN"]) + f"\n\n❌ Error: {e}"

    return reply


async def handle_customer_message(user_id: str, user_message: str, session: dict, bot=None) -> str:
    awaiting_rating = session.get("awaiting_rating")
    if awaiting_rating and user_message.strip() in ["1", "2", "3", "4", "5"]:
        rating = int(user_message.strip())
        supabase.table("orders").update({"rating": rating}).eq("id", awaiting_rating).execute()
        session.pop("awaiting_rating", None)
        stars = "⭐" * rating
        responses = {
            1: "Sorry to hear that 😔 We'll do better. Thanks for the feedback.",
            2: "Thanks for being honest. We're working on improving 🙏",
            3: "Glad it was decent! We're always improving ⚡",
            4: "Great to hear! 🔥 Come back anytime!",
            5: "Yesss! 🎉 You made our day! Tell your people about us!"
        }
        return f"{stars}\n\n{responses[rating]}"

    catalog_context = build_catalog_context()
    session["history"].append({"role": "user", "content": user_message})

    photos_sent = session.get("photos_sent", set())
    photos_sent_note = ""
    if photos_sent:
        photos_sent_note = f"\n\nPHOTOS ALREADY SENT THIS SESSION (do NOT trigger again): product IDs {', '.join(str(i) for i in photos_sent)}"

    system_prompt = (
        f"{CUSTOMER_PROMPT}\n\n"
        f"=== PRODUCT CATALOG ===\n{catalog_context}\n\n"
        f"Always reference actual products and prices from the catalog above.{photos_sent_note}"
    )

    try:
        reply = _call_gemini(system_prompt, session["history"][-12:], temperature=0.7, max_tokens=500)
    except Exception as e:
        session["history"].pop()
        err = str(e).lower()
        if "quota" in err or "rate" in err or "429" in err:
            return (
                "⚡ We're experiencing very high traffic right now and I need a quick breather!\n\n"
                "Please try again in a few minutes — I'll be right back. No wahala! 🙏"
            )
        return "😔 Something went wrong on my end. Please try again in a moment!"

    session["history"].append({"role": "assistant", "content": reply})

    customer_name, order_items, location, phone, agreed_prices = parse_order_signal(reply)
    if customer_name and order_items and location:
        await save_order(user_id, customer_name, order_items, bot, location, phone or "N/A", agreed_prices or {})
        return clean_reply(reply, ["ORDER"])

    return reply


async def save_order(user_id: str, customer_name: str, items: list, bot=None,
                     location: str = "Not provided", phone: str = "N/A", agreed_prices: dict = {}):
    enriched_items = []
    total = 0

    for item in items:
        product = get_book_by_id(item["book_id"])
        if product:
            price = agreed_prices.get(item["book_id"], product.get("list_price") or product["price"])
            enriched_items.append({
                "book_id": product["id"], "title": product["title"],
                "quantity": item["quantity"], "price": price,
            })
            total += price * item["quantity"]
            new_stock = max(0, product.get("stock_qty", 1) - item["quantity"])
            supabase.table("books").update({
                "stock_qty": new_stock, "in_stock": new_stock > 0
            }).eq("id", product["id"]).execute()

    if not enriched_items:
        return None

    order = create_order(
        customer_name=customer_name, telegram_id=user_id,
        items=enriched_items, total=total, location=location,
    )

    if order:
        supabase.table("orders").update({"phone_number": phone}).eq("id", order["id"]).execute()

    if order and bot:
        items_text = "\n".join([f"  • {i['title']} x{i['quantity']} — ₦{i['price']:,}" for i in enriched_items])
        negotiated = " *(negotiated)*" if agreed_prices else ""
        admin_ids = get_admin_ids()

        admin_msg = (
            f"🛎 *New Order #{order['id']}!*\n\n"
            f"👤 *{customer_name}*\n"
            f"📞 {phone}\n"
            f"📱 TG ID: `{user_id}` (t.me/user?id={user_id})\n"
            f"📍 *{location}*\n\n"
            f"{items_text}\n\n"
            f"💰 Total: ₦{total:,}{negotiated}\n\n"
            f"✅ Confirm: `/confirm {order['id']}`\n"
            f"🚚 Mark delivered: just tell me \"order #{order['id']} delivered to {customer_name}\""
        )
        for admin_id in admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown")
            except Exception:
                pass

        asyncio.create_task(order_timeout(order["id"], user_id, bot, enriched_items))

    return order


async def order_timeout(order_id: int, user_id: str, bot, items: list):
    await asyncio.sleep(24 * 60 * 60)
    try:
        res = supabase.table("orders").select("status").eq("id", order_id).single().execute()
        if res.data and res.data["status"] == "pending":
            supabase.table("orders").update({"status": "cancelled"}).eq("id", order_id).execute()
            for item in items:
                product = get_book_by_id(item["book_id"])
                if product:
                    new_stock = product.get("stock_qty", 0) + item["quantity"]
                    supabase.table("books").update({
                        "stock_qty": new_stock, "in_stock": True
                    }).eq("id", item["book_id"]).execute()
            try:
                await bot.send_message(
                    chat_id=int(user_id),
                    text=(
                        f"⚠️ Your order #{order_id} has been cancelled because we didn't receive payment within 24 hours.\n\n"
                        "If you still want to order, just start a new conversation. No wahala! 😊"
                    )
                )
            except Exception:
                pass
    except Exception:
        pass


async def notify_order_confirmed(order_id: int, bot):
    try:
        res = supabase.table("orders").select("*").eq("id", order_id).single().execute()
        if res.data:
            order = res.data
            tg_id = order["telegram_id"]
            customer_name = order["customer_name"]
            location = order.get("location", "your address")
            items_text = ", ".join([i["title"] for i in order.get("items", [])])
            await bot.send_message(
                chat_id=int(tg_id),
                text=(
                    f"🎉 Great news {customer_name}!\n\n"
                    f"Your order has been *confirmed* ✅\n\n"
                    f"Items: {items_text}\n"
                    f"Delivery to: {location}\n\n"
                    f"We'll be in touch shortly for delivery. Thank you for shopping with VoltStore! ⚡"
                ),
                parse_mode="Markdown"
            )
    except Exception:
        pass


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
        "book_id": product["id"], "title": product["title"],
        "quantity": quantity, "price": product.get("list_price") or product["price"],
    })
    return f"✅ Added: *{product['title']}* — ₦{product['price']:,}"


def view_cart(user_id: str) -> str:
    session = get_session(user_id)
    cart = session.get("cart", [])
    if not cart:
        return "🛒 Your cart is empty."
    lines = [f"  • {i['title']} x{i['quantity']} — ₦{i['price'] * i['quantity']:,}" for i in cart]
    total = sum(i["price"] * i["quantity"] for i in cart)
    return "🛒 *Your Cart:*\n" + "\n".join(lines) + f"\n\n💰 Total: ₦{total:,}"

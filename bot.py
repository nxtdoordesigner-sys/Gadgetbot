import os
import asyncio
import json
import logging
from reports import generate_report
from datetime import datetime, timezone, timedelta
from groq import Groq
from catalog import get_all_books, get_book_by_id
from orders import create_order
from supabase_client import supabase
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
PAYSTACK_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")

# NOTE: Sessions are persisted in Supabase — in-memory dict is a fast local cache only
sessions = {}
SESSION_TIMEOUT_MINUTES = 30

# ── Catalog cache to avoid pulling full catalog on every message ──
_catalog_cache = {"data": None, "updated_at": None}
CATALOG_CACHE_TTL_SECONDS = 60  # refresh every 60s


def get_admin_ids() -> list:
    try:
        res = supabase.table("admins").select("telegram_id").execute()
        return [int(a["telegram_id"]) for a in (res.data or [])]
    except Exception as e:
        logger.error(f"get_admin_ids failed: {e}", exc_info=True)
        return [5851987998]


CUSTOMER_PROMPT = """
You are Volt, AI sales assistant for VoltStore — a Nigerian gadget store.
You have full access to the product catalog provided below.

PERSONALITY:
- Sound like a knowledgeable, friendly assistant — not a bot, not a market seller
- Speak plain, clear English. No pidgin, no slang, no Nigerian expressions
- Be warm and conversational, like a helpful friend who knows their tech
- Keep replies short — 2-3 sentences max unless explaining specs
- Never be robotic or overly formal

BUDGET-FIRST APPROACH:
- When a customer mentions a budget, pick the SINGLE best product at or just under that budget
- Recommend ONE product confidently. Do not list multiple options upfront
- Only offer alternatives if the customer says they don't like your recommendation, or asks to see other options
- Never mention negotiation unless the customer asks to reduce the price

NEGOTIATION (for products marked NEGOTIABLE in catalog):
- ONLY bring up negotiation if the customer asks "can you do better?", "can you reduce?", "any discount?" or similar
- You can negotiate price — stay between list_price and base_price (floor)
- If customer asks for discount: offer ₦5-10k off first
- If they push: meet somewhere fair in the middle
- If they go below base_price: hold firm warmly ("I'd love to help but I can't go below this price")
- Never tell customer what the base_price is
- For NON-NEGOTIABLE products: politely say price is fixed if they ask

OUT OF STOCK:
- If product is out of stock, say so immediately
- Suggest ONE similar alternative based on category and price range
- Never recommend something way outside their budget unless you explain why

ORDER FLOW — follow strictly:
STEP 1: Confirm which product and quantity
STEP 2: Ask ONLY for full name
STEP 3: Ask ONLY for phone number
STEP 4: Ask ONLY for delivery address
STEP 5: Show order summary with agreed price, ask to confirm
STEP 6: After confirmation, output ONLY valid JSON at the END of your reply, like this:

```json
{
  "order": {
    "customer_name": "Full Name",
    "phone": "08012345678",
    "delivery_address": "Full address here",
    "items": [
      {"product_id": 3, "quantity": 1, "agreed_price": 75000}
    ]
  }
}
```

Use list_price as agreed_price if no negotiation happened.

PAYMENT (after order placed):
- Bank Transfer: GTBank — VoltStore NG, Acct: 0123456789. Send receipt here.
- For card payment: type "pay with card"

Only reference products from the catalog. Never make up products or prices.
CRITICAL: The catalog below is always the source of truth for prices, stock and availability.
If a price or detail in the conversation history conflicts with the catalog, ALWAYS use the catalog.

PHOTOS:
- Do NOT tell the customer a photo is being sent or reference photos at all
- Photos are sent automatically in the background — just recommend the product naturally
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

For ANY action, output valid JSON at the END of your reply (after your conversational text).

ACTION JSON FORMAT — pick the matching action:

Add product:
```json
{"action": "ADDPRODUCT", "name": "", "brand": "", "category": "", "price": 0, "condition": "Brand New", "stock_qty": 1, "negotiable": false, "base_price": 0, "specs": ""}
```

Update product:
```json
{"action": "UPDATEPRODUCT", "product_id": 0, "field": "", "value": ""}
```

Remove product:
```json
{"action": "REMOVEPRODUCT", "product_id": 0}
```

Mark delivered:
```json
{"action": "DELIVERED", "order_id": 0}
```

Broadcast:
```json
{"action": "BROADCAST", "message": ""}
```

Add admin:
```json
{"action": "ADDADMIN", "telegram_id": "", "name": ""}
```

If no action is needed, output NO json block at all.

REPORTS (admin can trigger these by saying):
- "send me the orders report"
- "send inventory sheet"
- "send revenue report"
- "send customer list"
- "send low stock report"
- "send full report" (all sheets)

Base answers on business data provided.
"""


# ── Session helpers — persist to Supabase, cache in memory ──

def _load_session_from_db(user_id: str) -> dict | None:
    try:
        res = supabase.table("sessions").select("*").eq("user_id", user_id).single().execute()
        if res.data:
            data = res.data
            return {
                "history": json.loads(data.get("history", "[]")),
                "cart": json.loads(data.get("cart", "[]")),
                "name": data.get("name", ""),
                "last_active": datetime.fromisoformat(data["last_active"]) if data.get("last_active") else datetime.now(timezone.utc),
                "awaiting_rating": data.get("awaiting_rating"),
                "awaiting_receipt": data.get("awaiting_receipt", False),
                "last_order_id": data.get("last_order_id"),
            }
    except Exception as e:
        logger.warning(f"_load_session_from_db failed for {user_id}: {e}")
    return None


def _save_session_to_db(user_id: str, session: dict):
    try:
        supabase.table("sessions").upsert({
            "user_id": user_id,
            "history": json.dumps(session.get("history", [])[-12:]),
            "cart": json.dumps(session.get("cart", [])),
            "name": session.get("name", ""),
            "last_active": session.get("last_active", datetime.now(timezone.utc)).isoformat(),
            "awaiting_rating": session.get("awaiting_rating"),
            "awaiting_receipt": session.get("awaiting_receipt", False),
            "last_order_id": session.get("last_order_id"),
        }).execute()
    except Exception as e:
        logger.error(f"Session save failed for {user_id}: {e}", exc_info=True)


def get_session(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    if user_id in sessions:
        last = sessions[user_id].get("last_active", now)
        if (now - last).total_seconds() > SESSION_TIMEOUT_MINUTES * 60:
            reset_session(user_id)
        else:
            sessions[user_id]["last_active"] = now
        return sessions[user_id]

    # Fall back to Supabase — treat it as source of truth
    db_session = _load_session_from_db(user_id)
    if db_session:
        last = db_session.get("last_active", now)
        if (now - last).total_seconds() > SESSION_TIMEOUT_MINUTES * 60:
            sessions[user_id] = {"history": [], "cart": [], "name": "", "last_active": now}
        else:
            db_session["last_active"] = now
            sessions[user_id] = db_session
    else:
        sessions[user_id] = {"history": [], "cart": [], "name": "", "last_active": now}

    return sessions[user_id]


def reset_session(user_id: str):
    sessions[user_id] = {
        "history": [], "cart": [], "name": "",
        "last_active": datetime.now(timezone.utc)
    }
    _save_session_to_db(user_id, sessions[user_id])


def build_catalog_context() -> str:
    """Returns cached catalog string, refreshing every CATALOG_CACHE_TTL_SECONDS seconds."""
    now = datetime.now(timezone.utc)
    cached = _catalog_cache["updated_at"]
    if cached and (now - cached).total_seconds() < CATALOG_CACHE_TTL_SECONDS and _catalog_cache["data"]:
        return _catalog_cache["data"]

    try:
        products = get_all_books()
    except Exception as e:
        logger.error(f"build_catalog_context: get_all_books failed: {e}", exc_info=True)
        return _catalog_cache["data"] or "No products currently in stock."

    if not products:
        return "No products currently in stock."

    lines = []
    for p in products:
        name = p.get("title", "Unknown")
        brand = p.get("author", "")
        negotiable_info = f" | NEGOTIABLE (floor: ₦{p['base_price']:,})" if p.get("negotiable") and p.get("base_price") else ""
        stock = p.get("stock_qty", 1)
        condition = p.get("condition", "Brand New")
        specs = p.get("specs", "")
        lines.append(
            f"ID:{p['id']} | {name} | {brand} | ₦{p['price']:,} | "
            f"{p.get('category', '')} | {condition} | Stock:{stock}{negotiable_info}"
            + (f" | {specs}" if specs else "")
        )

    result = "CURRENT CATALOG:\n" + "\n".join(lines)
    _catalog_cache["data"] = result
    _catalog_cache["updated_at"] = now
    return result


# ── Admin stats cache ──
_admin_cache = {"data": None, "updated_at": None}
ADMIN_CACHE_TTL_SECONDS = 30


def build_admin_data_context() -> str:
    """Returns cached admin stats, refreshing every ADMIN_CACHE_TTL_SECONDS seconds."""
    now = datetime.now(timezone.utc)
    cached = _admin_cache["updated_at"]
    if cached and (now - cached).total_seconds() < ADMIN_CACHE_TTL_SECONDS and _admin_cache["data"]:
        return _admin_cache["data"]

    try:
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
            f"  #{o['id']} | {o['customer_name']} | {o.get('location', 'N/A')} | ₦{o['total']:,} | {o['status']}"
            for o in recent
        ]

        result = f"""
BUSINESS DATA ({now.strftime('%Y-%m-%d %H:%M')} UTC):
Orders today: {len(today_orders)} | This month: {len(month_orders)} | Pending: {len(pending)} | Confirmed: {len(confirmed)}
Revenue today: ₦{today_revenue:,} | This month: ₦{month_revenue:,} | All time: ₦{total_revenue:,}
In stock: {len([p for p in all_products if p['in_stock']])} | Out of stock: {len([p for p in all_products if not p['in_stock']])}
Low stock (≤2): {', '.join([p['title'] for p in low_stock]) or 'none'}
Top products: {', '.join([f"{t}({c})" for t, c in top_products]) or 'none yet'}
Recent orders:
{chr(10).join(recent_lines) or '  None yet'}
"""
        _admin_cache["data"] = result
        _admin_cache["updated_at"] = now
        return result

    except Exception as e:
        logger.error(f"build_admin_data_context failed: {e}", exc_info=True)
        return _admin_cache["data"] or "Business data unavailable."


def _extract_json_block(text: str) -> dict | None:
    """
    Extract and parse the LAST ```json ... ``` block from model output.
    Returns parsed dict or None if not found / invalid.
    """
    import re
    matches = re.findall(r"```json\s*(.*?)```", text, re.DOTALL)
    if not matches:
        return None
    raw = matches[-1].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"_extract_json_block: JSON parse failed: {e} | raw: {raw[:300]}")
        return None


def clean_reply(reply: str) -> str:
    """Strip trailing ```json ... ``` block(s) from the reply before sending to user."""
    import re
    cleaned = re.sub(r"```json\s*.*?```", "", reply, flags=re.DOTALL).strip()
    return cleaned


def _validate_order_data(data: dict, source: str = "customer") -> bool:
    """Basic validation on parsed order JSON."""
    try:
        order = data.get("order", {})
        assert isinstance(order.get("customer_name"), str) and order["customer_name"].strip()
        assert isinstance(order.get("delivery_address"), str) and order["delivery_address"].strip()
        assert isinstance(order.get("items"), list) and len(order["items"]) > 0
        for item in order["items"]:
            pid = item.get("product_id")
            qty = item.get("quantity", 1)
            price = item.get("agreed_price")
            assert isinstance(pid, int) and pid > 0, f"bad product_id: {pid}"
            assert isinstance(qty, int) and qty > 0, f"bad quantity: {qty}"
            assert price is None or (isinstance(price, (int, float)) and price > 0), f"bad price: {price}"
            # Validate product actually exists
            product = get_book_by_id(pid)
            assert product is not None, f"product_id {pid} not found in catalog"
        return True
    except AssertionError as e:
        logger.warning(f"_validate_order_data ({source}) failed: {e} | data: {data}")
        return False


async def _call_groq(messages: list, temperature: float = 0.5, max_tokens: int = 600,
                     retries: int = 2, timeout: float = 20.0) -> str | None:
    """
    Groq call with timeout and retry logic.
    Returns the reply string or None if all attempts fail.
    """
    for attempt in range(retries + 1):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    groq_client.chat.completions.create,
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=timeout,
            )
            return response.choices[0].message.content.strip()
        except asyncio.TimeoutError:
            logger.warning(f"_call_groq: timeout on attempt {attempt + 1}/{retries + 1}")
        except Exception as e:
            logger.error(f"_call_groq: attempt {attempt + 1} failed: {e}", exc_info=True)
        if attempt < retries:
            await asyncio.sleep(1.5 * (attempt + 1))  # simple backoff
    return None


async def handle_message(user_id: str, user_message: str, bot=None) -> str:
    admin_ids = get_admin_ids()
    session = get_session(user_id)
    is_admin = int(user_id) in admin_ids

    if any(w in user_message.lower() for w in ["start over", "reset", "cancel everything"]):
        reset_session(user_id)
        return "Sure! We're starting fresh. What can I help you with?"

    if "my order" in user_message.lower() and "status" in user_message.lower():
        return await get_order_status(user_id)

    if "pay with card" in user_message.lower():
        return (
            "To pay with card, use this Paystack link:\n"
            f"https://paystack.com/pay/voltstore\n\n"
            "After payment, screenshot your receipt and send it here so we can confirm your order quickly."
        )

    if is_admin:
        return await handle_admin_message(user_id, user_message, session, bot, admin_ids)
    else:
        return await handle_customer_message(user_id, user_message, session, bot)


async def get_order_status(user_id: str) -> str:
    try:
        res = supabase.table("orders").select("*").eq("telegram_id", str(user_id)).order("created_at", desc=True).limit(1).execute()
        if not res.data:
            return "I don't see any orders from you yet. Want to browse what we have?"
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
    except Exception as e:
        logger.error(f"get_order_status failed for {user_id}: {e}", exc_info=True)
        return "Couldn't fetch your order status right now. Try again in a moment."


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
        try:
            from catalog import search_books
            results = search_books(query)
            if results:
                lines = []
                for p in results[:5]:
                    neg = " | 💬 Negotiable" if p.get("negotiable") else ""
                    stock = p.get("stock_qty", 0)
                    pid = p["id"]
                    price = p["price"]
                    condition = p.get("condition", "Brand New")
                    lines.append(
                        f"*{p['title']}* (ID: {pid})\n"
                        f"  💰 ₦{price:,}{neg}\n"
                        f"  📦 Stock: {stock} | 🔧 {condition}"
                    )
                return "\n\n".join(lines)
            return f"No products found matching '{query}'."
        except Exception as e:
            logger.error(f"Admin search failed: {e}", exc_info=True)
            return "Search failed — please try again."

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
                    logger.error(f"Report generation failed: {e}", exc_info=True)
                    return f"❌ Error generating report: {e}"

    system_content = (
        f"{ADMIN_PROMPT}\n\n"
        f"=== BUSINESS STATS ===\n{admin_data}\n\n"
        f"=== FULL PRODUCT CATALOG ===\n{catalog_context}\n\n"
        f"Use the catalog above to answer ANY questions about products, prices, stock, categories etc."
    )
    messages = [
        {"role": "system", "content": system_content},
        *admin_session["history"][-8:],
    ]

    reply = await _call_groq(messages, temperature=0.4, max_tokens=800)
    if reply is None:
        return "⚠️ I'm having trouble connecting right now. Please try again in a moment."

    admin_session["history"].append({"role": "assistant", "content": reply})

    # ── Parse structured JSON action ──
    action_data = _extract_json_block(reply)
    action = action_data.get("action") if action_data else None

    if action == "ADDPRODUCT" and action_data:
        try:
            d = action_data
            name = str(d["name"]).strip()
            brand = str(d.get("brand", "")).strip()
            category = str(d.get("category", "")).strip()
            price = float(str(d["price"]).replace(",", "").replace("₦", ""))
            condition = str(d.get("condition", "Brand New")).strip()
            stock_qty = int(d.get("stock_qty", 1))
            negotiable = bool(d.get("negotiable", False))
            base_price = float(str(d.get("base_price", price * 0.85)).replace(",", "").replace("₦", ""))
            specs = d.get("specs") or None

            assert name, "Product name is required"
            assert price > 0, "Price must be positive"
            assert stock_qty >= 0, "Stock qty must be non-negative"

            res = supabase.table("books").insert({
                "title": name, "author": brand, "category": category,
                "price": price, "list_price": price, "base_price": base_price,
                "condition": condition, "stock_qty": stock_qty,
                "negotiable": negotiable, "in_stock": True, "specs": specs
            }).execute()

            if res.data:
                new_id = res.data[0]["id"]
                # Invalidate catalog cache
                _catalog_cache["updated_at"] = None
                suffix = f"\n\n✅ *{name}* added! (ID: {new_id})\n\nSend me the product photos and I'll attach them automatically 📸"
                return clean_reply(reply) + suffix + f"##LASTADDED##{new_id}"
            return clean_reply(reply) + "\n\n❌ Failed to add product — database returned no data."
        except (AssertionError, KeyError, ValueError, TypeError) as e:
            logger.error(f"ADDPRODUCT failed: {e} | data: {action_data}", exc_info=True)
            return clean_reply(reply) + f"\n\n❌ Error adding product: {e}"

    if action == "UPDATEPRODUCT" and action_data:
        try:
            product_id = int(action_data["product_id"])
            field = str(action_data["field"]).strip()
            value = action_data["value"]

            assert product_id > 0, "Invalid product_id"
            assert field, "Field name is required"

            # Verify product exists before updating
            existing = get_book_by_id(product_id)
            assert existing is not None, f"Product ID {product_id} not found"

            if field in ["image_url", "image", "photo"]:
                return clean_reply(reply) + "\n\nSend the photo directly in chat and I'll attach it! 📸"

            if field in ["price", "base_price", "list_price"]:
                value = float(str(value).replace(",", "").replace("₦", ""))
                assert value > 0, "Price must be positive"
            elif field == "stock_qty":
                value = int(value)
                assert value >= 0, "Stock qty must be non-negative"
                supabase.table("books").update({"in_stock": value > 0}).eq("id", product_id).execute()
            elif field == "negotiable":
                value = str(value).lower() in ["true", "yes", "1"]

            supabase.table("books").update({field: value}).eq("id", product_id).execute()
            # Invalidate catalog cache
            _catalog_cache["updated_at"] = None

            # Invalidate stale session history mentioning this product
            product = get_book_by_id(product_id)
            if product:
                title_lower = product["title"].lower()
                for uid, sess in sessions.items():
                    if "history" in sess:
                        sess["history"] = [
                            msg for msg in sess["history"]
                            if title_lower not in msg.get("content", "").lower()
                            or msg["role"] == "user"
                        ]

            return clean_reply(reply) + "\n\n✅ Updated!"
        except (AssertionError, KeyError, ValueError, TypeError) as e:
            logger.error(f"UPDATEPRODUCT failed: {e} | data: {action_data}", exc_info=True)
            return clean_reply(reply) + f"\n\n❌ Error updating product: {e}"

    if action == "REMOVEPRODUCT" and action_data:
        try:
            product_id = int(action_data["product_id"])
            assert product_id > 0, "Invalid product_id"
            existing = get_book_by_id(product_id)
            assert existing is not None, f"Product ID {product_id} not found"
            supabase.table("books").delete().eq("id", product_id).execute()
            _catalog_cache["updated_at"] = None
            return clean_reply(reply) + "\n\n🗑 Product removed."
        except (AssertionError, KeyError, ValueError) as e:
            logger.error(f"REMOVEPRODUCT failed: {e} | data: {action_data}", exc_info=True)
            return clean_reply(reply) + f"\n\n❌ Error removing product: {e}"

    if action == "DELIVERED" and action_data and bot:
        try:
            order_id = int(action_data["order_id"])
            assert order_id > 0, "Invalid order_id"
            res = supabase.table("orders").update({
                "status": "delivered",
                "delivered_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", order_id).execute()

            if not res.data:
                return clean_reply(reply) + f"\n\n❌ Order #{order_id} not found."

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
                        f"Hope you're loving it! 🔥 How was your experience shopping with VoltStore?\n\n"
                        f"Reply with a number:\n"
                        f"⭐ 1 - Poor\n⭐⭐ 2 - Fair\n⭐⭐⭐ 3 - Good\n⭐⭐⭐⭐ 4 - Great\n⭐⭐⭐⭐⭐ 5 - Amazing!"
                    )
                )
                if str(tg_id) not in sessions:
                    sessions[str(tg_id)] = {"history": [], "cart": [], "name": ""}
                sessions[str(tg_id)]["awaiting_rating"] = order_id
                _save_session_to_db(str(tg_id), sessions[str(tg_id)])
            except Exception as e:
                logger.error(f"Failed to send delivery notification to {tg_id}: {e}", exc_info=True)

            return clean_reply(reply) + f"\n\n✅ Order #{order_id} marked as delivered. Customer notified and asked for a rating!"
        except (AssertionError, KeyError, ValueError) as e:
            logger.error(f"DELIVERED failed: {e} | data: {action_data}", exc_info=True)
            return clean_reply(reply) + f"\n\n❌ Error marking delivery: {e}"

    if action == "BROADCAST" and action_data and bot:
        try:
            message = str(action_data["message"]).strip()
            assert message, "Broadcast message cannot be empty"
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
                        text=f"📢 *VoltStore Update*\n\n{message}",
                        parse_mode="Markdown"
                    )
                    sent += 1
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.warning(f"Broadcast failed for {r['telegram_id']}: {e}")

            try:
                supabase.table("broadcasts").insert({
                    "message": message, "sent_by": str(user_id), "recipient_count": sent
                }).execute()
            except Exception as e:
                logger.error(f"Broadcast DB log failed: {e}", exc_info=True)

            return clean_reply(reply) + f"\n\n📢 Broadcast sent to {sent} customer(s)!"
        except (AssertionError, KeyError) as e:
            logger.error(f"BROADCAST failed: {e} | data: {action_data}", exc_info=True)
            return clean_reply(reply) + f"\n\n❌ Error sending broadcast: {e}"

    if action == "ADDADMIN" and action_data:
        try:
            tid = str(action_data["telegram_id"]).strip()
            name = str(action_data.get("name", "Admin")).strip()
            assert tid.isdigit(), "telegram_id must be a number"
            supabase.table("admins").insert({"telegram_id": tid, "name": name}).execute()
            return clean_reply(reply) + f"\n\n✅ {name} added as admin!"
        except (AssertionError, KeyError) as e:
            logger.error(f"ADDADMIN failed: {e} | data: {action_data}", exc_info=True)
            return clean_reply(reply) + f"\n\n❌ Error adding admin: {e}"

    return clean_reply(reply)


async def handle_customer_message(user_id: str, user_message: str, session: dict, bot=None) -> str:
    awaiting_rating = session.get("awaiting_rating")
    if awaiting_rating and user_message.strip() in ["1", "2", "3", "4", "5"]:
        try:
            rating = int(user_message.strip())
            supabase.table("orders").update({"rating": rating}).eq("id", awaiting_rating).execute()
            session.pop("awaiting_rating", None)
            _save_session_to_db(user_id, session)
            stars = "⭐" * rating
            responses = {
                1: "Sorry to hear that. We'll do better next time — thanks for the honest feedback.",
                2: "Thanks for being honest. We're always working to improve.",
                3: "Glad it was a decent experience! We're always getting better.",
                4: "Great to hear! Come back anytime. 🔥",
                5: "That's amazing! 🎉 Thank you so much — we really appreciate it!"
            }
            return f"{stars}\n\n{responses[rating]}"
        except Exception as e:
            logger.error(f"Rating save failed for {user_id}: {e}", exc_info=True)
            return "Thanks for the feedback!"

    catalog_context = build_catalog_context()
    session["history"].append({"role": "user", "content": user_message})

    messages = [
        {"role": "system", "content": f"{CUSTOMER_PROMPT}\n\n=== PRODUCT CATALOG ===\n{catalog_context}\n\nAlways reference actual products and prices from the catalog above."},
        *session["history"][-12:],
    ]

    reply = await _call_groq(messages, temperature=0.75, max_tokens=450)
    if reply is None:
        return "⚠️ I'm having a connection issue. Please try again in a moment!"

    session["history"].append({"role": "assistant", "content": reply})
    _save_session_to_db(user_id, session)

    # ── Parse structured order JSON ──
    order_data = _extract_json_block(reply)
    if order_data and "order" in order_data:
        if _validate_order_data(order_data, source=f"customer:{user_id}"):
            order_info = order_data["order"]
            customer_name = order_info["customer_name"]
            phone = order_info.get("phone", "N/A")
            location = order_info["delivery_address"]
            items = [
                {"book_id": i["product_id"], "quantity": i.get("quantity", 1)}
                for i in order_info["items"]
            ]
            agreed_prices = {
                i["product_id"]: i["agreed_price"]
                for i in order_info["items"]
                if i.get("agreed_price")
            }
            order = await save_order(user_id, customer_name, items, bot, location, phone, agreed_prices)
            if order:
                session["awaiting_receipt"] = True
                session["last_order_id"] = order["id"]
                _save_session_to_db(user_id, session)
                logger.info(f"Order #{order['id']} saved for user {user_id}")
            else:
                logger.error(f"save_order returned None for user {user_id}")
        else:
            logger.warning(f"Order JSON found but failed validation for user {user_id}: {order_data}")
    elif order_data:
        logger.debug(f"JSON block found but no 'order' key for user {user_id}: {order_data}")

    return clean_reply(reply)


async def save_order(user_id: str, customer_name: str, items: list, bot=None,
                     location: str = "Not provided", phone: str = "N/A", agreed_prices: dict = {}):
    enriched_items = []
    total = 0

    for item in items:
        try:
            product = get_book_by_id(item["book_id"])
            if not product:
                logger.warning(f"save_order: product {item['book_id']} not found, skipping")
                continue
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
            # Invalidate catalog cache since stock changed
            _catalog_cache["updated_at"] = None
        except Exception as e:
            logger.error(f"save_order: error enriching item {item}: {e}", exc_info=True)

    if not enriched_items:
        logger.error(f"save_order: no enriched items for user {user_id}, raw items: {items}")
        return None

    try:
        order = create_order(
            customer_name=customer_name, telegram_id=user_id,
            items=enriched_items, total=total, location=location,
        )
    except Exception as e:
        logger.error(f"save_order: create_order failed for {user_id}: {e}", exc_info=True)
        return None

    if order:
        try:
            supabase.table("orders").update({"phone_number": phone}).eq("id", order["id"]).execute()
        except Exception as e:
            logger.warning(f"save_order: phone update failed: {e}")

        items_text = "\n".join([f"  • {i['title']} x{i['quantity']} — ₦{i['price']:,}" for i in enriched_items])
        negotiated = " *(negotiated)*" if agreed_prices else ""
        admin_ids = get_admin_ids()
        logger.info(f"Order #{order['id']} created. Notifying admins: {admin_ids}")

        admin_msg = (
            f"🛎 *New Order #{order['id']}!*\n\n"
            f"👤 *{customer_name}*\n"
            f"📞 {phone}\n"
            f"📱 TG: `{user_id}`\n"
            f"📍 *{location}*\n\n"
            f"{items_text}\n\n"
            f"💰 Total: ₦{total:,}{negotiated}\n\n"
            f"✅ Confirm: /confirm {order['id']}\n"
            f"🚚 Delivered? Just tell me in chat"
        )

        if bot:
            for admin_id in admin_ids:
                try:
                    await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown")
                    logger.info(f"Admin notification sent to {admin_id} for order #{order['id']}")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}", exc_info=True)
        else:
            logger.error(f"bot is None in save_order — admin notification not sent for order #{order['id']}")

        # Schedule timeout via Supabase (survives restarts)
        timeout_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        try:
            supabase.table("order_timeouts").upsert({
                "order_id": order["id"],
                "user_id": user_id,
                "timeout_at": timeout_at,
                "items": enriched_items,
                "processed": False
            }).execute()
        except Exception as e:
            logger.warning(f"Could not save order timeout to DB: {e}")
            asyncio.create_task(order_timeout(order["id"], user_id, bot, enriched_items))

    return order


async def order_timeout(order_id: int, user_id: str, bot, items: list):
    """Fallback in-memory timeout. Prefer DB-based scheduling via order_timeouts table."""
    await asyncio.sleep(24 * 60 * 60)
    try:
        res = supabase.table("orders").select("status").eq("id", order_id).single().execute()
        if res.data and res.data["status"] == "pending":
            supabase.table("orders").update({"status": "cancelled"}).eq("id", order_id).execute()
            for item in items:
                try:
                    product = get_book_by_id(item["book_id"])
                    if product:
                        new_stock = product.get("stock_qty", 0) + item["quantity"]
                        supabase.table("books").update({
                            "stock_qty": new_stock, "in_stock": True
                        }).eq("id", item["book_id"]).execute()
                        _catalog_cache["updated_at"] = None
                except Exception as e:
                    logger.error(f"order_timeout: stock restore failed for item {item}: {e}", exc_info=True)
            try:
                await bot.send_message(
                    chat_id=int(user_id),
                    text=(
                        f"⚠️ Your order #{order_id} has been cancelled because we didn't receive payment within 24 hours.\n\n"
                        "If you still want to order, just start a new conversation anytime!"
                    )
                )
            except Exception as e:
                logger.error(f"order_timeout: failed to notify user {user_id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"order_timeout: failed for order #{order_id}: {e}", exc_info=True)


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
    except Exception as e:
        logger.error(f"notify_order_confirmed failed for order #{order_id}: {e}", exc_info=True)


async def add_to_cart(user_id: str, product_id: int, quantity: int = 1) -> str:
    try:
        session = get_session(user_id)
        product = get_book_by_id(product_id)
        if not product:
            return f"❌ Product with ID {product_id} not found."
        for item in session["cart"]:
            if item["book_id"] == product_id:
                item["quantity"] += quantity
                _save_session_to_db(user_id, session)
                return f"✅ Updated cart: *{product['title']}* x{item['quantity']}"
        session["cart"].append({
            "book_id": product["id"], "title": product["title"],
            "quantity": quantity, "price": product.get("list_price") or product["price"],
        })
        _save_session_to_db(user_id, session)
        return f"✅ Added: *{product['title']}* — ₦{product['price']:,}"
    except Exception as e:
        logger.error(f"add_to_cart failed for {user_id}: {e}", exc_info=True)
        return "❌ Couldn't update cart. Please try again."


def view_cart(user_id: str) -> str:
    try:
        session = get_session(user_id)
        cart = session.get("cart", [])
        if not cart:
            return "🛒 Your cart is empty."
        lines = [f"  • {i['title']} x{i['quantity']} — ₦{i['price'] * i['quantity']:,}" for i in cart]
        total = sum(i["price"] * i["quantity"] for i in cart)
        return "🛒 *Your Cart:*\n" + "\n".join(lines) + f"\n\n💰 Total: ₦{total:,}"
    except Exception as e:
        logger.error(f"view_cart failed for {user_id}: {e}", exc_info=True)
        return "❌ Couldn't load your cart. Please try again."

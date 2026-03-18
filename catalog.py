from supabase_client import supabase


def get_all_books():
    response = supabase.table("books").select("*").eq("in_stock", True).order("id").execute()
    return response.data or []


def get_books_by_category(category: str):
    response = (
        supabase.table("books")
        .select("*")
        .eq("category", category)
        .eq("in_stock", True)
        .execute()
    )
    return response.data or []


def search_books(query: str):
    response = (
        supabase.table("books")
        .select("*")
        .or_(f"title.ilike.%{query}%,author.ilike.%{query}%,category.ilike.%{query}%")
        .eq("in_stock", True)
        .execute()
    )
    return response.data or []


def get_book_by_id(book_id: int):
    response = supabase.table("books").select("*").eq("id", book_id).single().execute()
    return response.data


def format_book(product: dict) -> str:
    negotiable = "💬 Price negotiable" if product.get("negotiable") else ""
    condition = product.get("condition", "Brand New")
    stock = product.get("stock_qty", 1)
    specs = product.get("specs", "")

    lines = [
        f"📱 *{product['title']}*",
        f"🏷️ {product['author']}",
        f"📂 {product.get('category', 'General')}",
        f"🔧 {condition}",
        f"💰 ₦{product['price']:,}",
        f"📦 {stock} unit(s) available" if stock > 0 else "❌ Out of Stock",
    ]
    if negotiable:
        lines.append(negotiable)
    if specs:
        lines.append(f"📋 {specs}")
    return "\n".join(lines)


def format_catalog(products: list) -> str:
    if not products:
        return "No products found."
    return "\n\n".join([format_book(p) for p in products])

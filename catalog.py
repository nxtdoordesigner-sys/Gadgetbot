from supabase_client import supabase


def get_all_books():
    response = supabase.table("books").select("*").eq("in_stock", True).execute()
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
        .or_(f"title.ilike.%{query}%,author.ilike.%{query}%")
        .eq("in_stock", True)
        .execute()
    )
    return response.data or []


def get_book_by_id(book_id: int):
    response = supabase.table("books").select("*").eq("id", book_id).single().execute()
    return response.data


def format_book(book: dict) -> str:
    return (
        f"📱 *{book['title']}*\n"
        f"🏷️ {book['author']}\n"
        f"📂 {book.get('category', 'General')}\n"
        f"💰 ₦{book['price']:,}\n"
        f"{'✅ In Stock' if book['in_stock'] else '❌ Out of Stock'}\n"
        f"🆔 ID: `{book['id']}`"
    )


def format_catalog(books: list) -> str:
    if not books:
        return "No products found."
    return "\n\n".join([format_book(b) for b in books])

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DB_NAME = "marketplace.db"
VALID_STATUSES = {"available", "sold"}
VALID_MESSAGE_ROLES = {"buyer", "seller"}

CATEGORY_ALIASES = {
    "3C": ["3C"],
    "furniture": ["furniture", "家具"],
    "clothing": ["clothing", "服飾"],
    "books": ["books", "書籍"],
    "sports": ["sports", "運動"],
    "other": ["other", "其他"],
}

CONDITION_ALIASES = {
    "mint": ["mint", "近全新"],
    "good": ["good", "良好"],
    "fair": ["fair", "普通"],
    "cleanup": ["cleanup", "待整理"],
}

SEED_LISTINGS = [
    {
        "title": "二手 iPad Air",
        "category": "3C",
        "price": 9800,
        "condition": "good",
        "description": "功能正常，附保護殼與充電器。",
        "seller_name": "王小明",
        "contact": "0912-345-678",
        "location": "台北市",
        "myship_url": None,
        "photos": [],
        "status": "available",
    },
    {
        "title": "木質書桌",
        "category": "furniture",
        "price": 2500,
        "condition": "fair",
        "description": "有正常使用痕跡，適合租屋族。",
        "seller_name": "林小姐",
        "contact": "line: desk-sale",
        "location": "新北市",
        "myship_url": None,
        "photos": [],
        "status": "available",
    },
    {
        "title": "公路車安全帽",
        "category": "sports",
        "price": 1200,
        "condition": "mint",
        "description": "只戴過兩次，尺寸 M。",
        "seller_name": "陳先生",
        "contact": "0988-888-123",
        "location": "桃園市",
        "myship_url": None,
        "photos": [],
        "status": "sold",
    },
]


def get_database_path() -> Path:
    """Allow deployment environments to choose a custom database location."""
    configured_path = os.environ.get("MARKETPLACE_DB_PATH", "").strip()

    if configured_path:
        return Path(configured_path).expanduser()

    return Path(__file__).resolve().parent / DEFAULT_DB_NAME


@contextmanager
def get_connection():
    """Open a short-lived SQLite connection for each database operation."""
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
    finally:
        connection.close()


def initialize_database():
    """Create tables and seed starter data when the database is empty."""
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                price INTEGER NOT NULL,
                condition TEXT NOT NULL,
                description TEXT NOT NULL,
                seller_name TEXT NOT NULL,
                contact TEXT NOT NULL,
                location TEXT NOT NULL,
                myship_url TEXT,
                photos_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'available',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        _ensure_listings_columns(connection)

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                author_name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
            )
            """
        )

        listing_count = connection.execute(
            "SELECT COUNT(*) AS count FROM listings"
        ).fetchone()["count"]

        if listing_count == 0:
            _seed_database(connection)

        connection.commit()


def list_listings(keyword: str = "", category: str = "all", status: str = "all"):
    """Return listings with hydrated message threads."""
    where_clauses = []
    parameters = []

    normalized_keyword = keyword.strip()
    if normalized_keyword:
        like_keyword = f"%{normalized_keyword}%"
        where_clauses.append(
            "(title LIKE ? OR description LIKE ? OR location LIKE ? OR seller_name LIKE ? OR contact LIKE ?)"
        )
        parameters.extend(
            [like_keyword, like_keyword, like_keyword, like_keyword, like_keyword]
        )

    if category != "all":
        category_aliases = CATEGORY_ALIASES.get(category, [category])
        placeholders = ", ".join("?" for _ in category_aliases)
        where_clauses.append(f"category IN ({placeholders})")
        parameters.extend(category_aliases)

    if status != "all":
        where_clauses.append("status = ?")
        parameters.append(status)

    sql = "SELECT * FROM listings"
    if where_clauses:
        sql += f" WHERE {' AND '.join(where_clauses)}"

    sql += " ORDER BY datetime(created_at) DESC, id DESC"

    with get_connection() as connection:
        listing_rows = connection.execute(sql, parameters).fetchall()

        listing_ids = [row["id"] for row in listing_rows]
        message_rows = []

        if listing_ids:
            placeholders = ", ".join("?" for _ in listing_ids)
            message_rows = connection.execute(
                f"""
                SELECT *
                FROM comments
                WHERE listing_id IN ({placeholders})
                ORDER BY datetime(created_at) ASC, id ASC
                """,
                listing_ids,
            ).fetchall()

    messages_by_listing = {}
    for row in message_rows:
        messages_by_listing.setdefault(row["listing_id"], []).append(
            _serialize_message(row)
        )

    return [
        _serialize_listing(row, messages_by_listing.get(row["id"], []))
        for row in listing_rows
    ]


def create_listing(payload: dict):
    """Insert a new listing and return the hydrated row."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO listings (
                title,
                category,
                price,
                condition,
                description,
                seller_name,
                contact,
                location,
                myship_url,
                photos_json,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["title"],
                payload["category"],
                payload["price"],
                payload["condition"],
                payload["description"],
                payload["seller_name"],
                payload["contact"],
                payload["location"],
                payload["myship_url"],
                json.dumps(payload.get("photos", [])),
                payload.get("status", "available"),
            ),
        )
        connection.commit()
        listing_id = cursor.lastrowid

    return get_listing_by_id(listing_id)


def get_listing_by_id(listing_id: int):
    """Fetch one listing and all messages for it."""
    with get_connection() as connection:
        listing_row = connection.execute(
            "SELECT * FROM listings WHERE id = ?",
            (listing_id,),
        ).fetchone()

        if not listing_row:
            return None

        message_rows = connection.execute(
            """
            SELECT *
            FROM comments
            WHERE listing_id = ?
            ORDER BY datetime(created_at) ASC, id ASC
            """,
            (listing_id,),
        ).fetchall()

    return _serialize_listing(
        listing_row,
        [_serialize_message(row) for row in message_rows],
    )


def update_listing_status(listing_id: int, status: str):
    """Switch a listing between available and sold."""
    if status not in VALID_STATUSES:
        raise ValueError("invalid-status")

    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE listings SET status = ? WHERE id = ?",
            (status, listing_id),
        )
        connection.commit()

        if cursor.rowcount == 0:
            return None

    return get_listing_by_id(listing_id)


def update_myship_link(listing_id: int, myship_url):
    """Update or clear the MyShip link for a listing."""
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE listings SET myship_url = ? WHERE id = ?",
            (myship_url, listing_id),
        )
        connection.commit()

        if cursor.rowcount == 0:
            return None

    return get_listing_by_id(listing_id)


def add_message(listing_id: int, role: str, author_name: str, content: str):
    """Create a buyer or seller message."""
    if role not in VALID_MESSAGE_ROLES:
        raise ValueError("invalid-role")

    with get_connection() as connection:
        listing_exists = connection.execute(
            "SELECT 1 FROM listings WHERE id = ?",
            (listing_id,),
        ).fetchone()

        if not listing_exists:
            return None

        cursor = connection.execute(
            """
            INSERT INTO comments (
                listing_id,
                role,
                author_name,
                content
            )
            VALUES (?, ?, ?, ?)
            """,
            (listing_id, role, author_name, content),
        )
        connection.commit()

        message_row = connection.execute(
            "SELECT * FROM comments WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return _serialize_message(message_row)


def delete_listing(listing_id: int):
    """Delete a listing and its child messages."""
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM listings WHERE id = ?",
            (listing_id,),
        )
        connection.commit()
        return cursor.rowcount > 0


def _ensure_listings_columns(connection: sqlite3.Connection):
    """Apply lightweight migrations when an older database file is reused."""
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(listings)").fetchall()
    }

    if "myship_url" not in existing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN myship_url TEXT")

    if "photos_json" not in existing_columns:
        connection.execute(
            "ALTER TABLE listings ADD COLUMN photos_json TEXT NOT NULL DEFAULT '[]'"
        )


def _seed_database(connection: sqlite3.Connection):
    """Provide starter content for first run."""
    connection.executemany(
        """
        INSERT INTO listings (
            title,
            category,
            price,
            condition,
            description,
            seller_name,
            contact,
            location,
            myship_url,
            photos_json,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                listing["title"],
                listing["category"],
                listing["price"],
                listing["condition"],
                listing["description"],
                listing["seller_name"],
                listing["contact"],
                listing["location"],
                listing["myship_url"],
                json.dumps(listing["photos"]),
                listing["status"],
            )
            for listing in SEED_LISTINGS
        ],
    )


def _parse_photos(raw_value):
    """Keep photo parsing tolerant so older rows do not break the UI."""
    if not raw_value:
        return []

    try:
        parsed_value = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    return parsed_value if isinstance(parsed_value, list) else []


def _serialize_listing(row: sqlite3.Row, messages):
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "price": row["price"],
        "condition": row["condition"],
        "description": row["description"],
        "seller_name": row["seller_name"],
        "contact": row["contact"],
        "location": row["location"],
        "myship_url": row["myship_url"],
        "photos": _parse_photos(row["photos_json"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "messages": messages,
    }


def _serialize_message(row: sqlite3.Row):
    return {
        "id": row["id"],
        "listing_id": row["listing_id"],
        "role": row["role"],
        "author_name": row["author_name"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


import sqlite3

DB_NAME = "dukasense.db"


def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            quantity REAL NOT NULL DEFAULT 0,
            buying_price REAL NOT NULL,
            selling_price REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            buying_price REAL NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    cursor.execute("PRAGMA table_info(sales)")
    columns = [row[1] for row in cursor.fetchall()]

    if columns and "product_id" not in columns:
        cursor.execute("ALTER TABLE sales RENAME TO sales_legacy")
        columns = []

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            unit_cost REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL,
            amount_received REAL NOT NULL,
            change_due REAL NOT NULL,
            payment_method TEXT NOT NULL,
            date TEXT NOT NULL,
            receipt_id TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    cursor.execute("PRAGMA table_info(sales)")
    columns = [row[1] for row in cursor.fetchall()]

    if "unit_cost" not in columns:
        cursor.execute("""
            ALTER TABLE sales
            ADD COLUMN unit_cost REAL NOT NULL DEFAULT 0
        """)

    if "receipt_id" not in columns:
        cursor.execute("""
            ALTER TABLE sales
            ADD COLUMN receipt_id TEXT
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS credit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            customer TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            amount_paid REAL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

import aiosqlite
from datetime import datetime

DB_NAME = "orders.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT, 
                photo_file_id TEXT,
                description TEXT,
                phone_number TEXT,
                address TEXT,
                status TEXT DEFAULT 'Новый',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                due_date TEXT,
                notification_sent BOOLEAN DEFAULT FALSE
            )
        ''')
        await db.commit()

# --- НОВАЯ ФУНКЦИЯ ---
async def reset_database():
    """Полностью удаляет таблицу заказов для сброса счетчика."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('DROP TABLE IF EXISTS orders')
        # Сразу же создаем ее заново
        await init_db()

# ... (остальные функции без изменений) ...
async def add_order(data: dict):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            INSERT INTO orders (chat_id, photo_file_id, description, phone_number, address, due_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['chat_id'], data['photo'], data['description'], data['phone'], data['address'], data['due_date']))
        await db.commit()
        return cursor.lastrowid

async def get_all_orders():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT id, description FROM orders WHERE status != "Завершён" ORDER BY id DESC')
        orders = await cursor.fetchall()
        return orders

async def get_order_details(order_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        order_details = await cursor.fetchone()
        return order_details

async def update_order_status(order_id: int, status: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
        await db.commit()

async def update_order_due_date(order_id: int, due_date: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE orders SET due_date = ? WHERE id = ?', (due_date, order_id))
        await db.commit()

async def get_orders_for_notification():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            SELECT id, chat_id, description, due_date FROM orders 
            WHERE status NOT IN ('Завершён', 'Готов') 
            AND notification_sent = FALSE 
            AND due_date IS NOT NULL
        ''')
        orders = await cursor.fetchall()
        return orders

async def mark_notification_sent(order_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE orders SET notification_sent = TRUE WHERE id = ?', (order_id,))
        await db.commit()

async def delete_order(order_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('DELETE FROM orders WHERE id = ?', (order_id,))
        await db.commit()
import aiosqlite
from datetime import datetime

DB_PATH = "students.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                surname TEXT NOT NULL,
                group_number TEXT NOT NULL,
                has_dbk BOOLEAN NOT NULL,
                lat_start TEXT,
                lon_start TEXT,
                lat_end TEXT,
                lon_end TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        await db.commit()

async def save_student(data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO students (
                telegram_id, surname, group_number, has_dbk,
                lat_start, lon_start, lat_end, lon_end, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["telegram_id"],
            data["surname"],
            data["group_number"],
            data["has_dbk"],
            data.get("lat_start"),
            data.get("lon_start"),
            data.get("lat_end"),
            data.get("lon_end"),
            datetime.now().isoformat()
        ))
        await db.commit()

async def get_all_students():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT surname, group_number, has_dbk, lat_start, lon_start, lat_end, lon_end, timestamp 
            FROM students ORDER BY timestamp DESC
        """) as cursor:
            return await cursor.fetchall()
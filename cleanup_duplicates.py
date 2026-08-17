import sqlite3
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent / "data" / "nfe_index.db"

with sqlite3.connect(DATABASE_PATH) as connection:
    deleted = connection.execute("""
        DELETE FROM items
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM items
            GROUP BY access_key, n_item, quantity
        )
    """).rowcount
    connection.commit()
    print(f"Duplicatas removidas: {deleted}")
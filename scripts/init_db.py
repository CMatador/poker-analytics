import duckdb
import os

DB_PATH = "data/poker.db"
SCHEMA_PATH = "schema.sql"


def init_db():
    os.makedirs("data", exist_ok=True)

    conn = duckdb.connect(DB_PATH)
    with open(SCHEMA_PATH, "r") as f:
        conn.execute(f.read())
    conn.close()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()

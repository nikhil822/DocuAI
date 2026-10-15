import os

import psycopg
from pgvector.psycopg import register_vector

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://raguser:local_dev_password@localhost:5433/ragdb")

def get_connection():
    conn = psycopg.connect(DATABASE_URL)
    register_vector(conn)
    return conn

if __name__ == "__main__":
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), version()")
            version = cur.fetchone()
            print("PostgreSQL version:", version[0])
            print("Connected successfully to the database.")
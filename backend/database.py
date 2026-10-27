import os

import psycopg
from pgvector.psycopg import register_vector


def get_connection():
    database_url = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
    )

    if not database_url:
        raise RuntimeError(
            "Set DATABASE_URL or SUPABASE_DB_URL "
            "in the backend environment."
        )

    conn = psycopg.connect(database_url)
    register_vector(conn)

    return conn


if __name__ == "__main__":
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), version()"
            )
            database, version = cur.fetchone()

            print("PostgreSQL database:", database)
            print("PostgreSQL version:", version)
            print("Connected successfully.")
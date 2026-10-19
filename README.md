# DocuAI

## Database connection

The backend uses PostgreSQL with the `pgvector` extension. To connect to Supabase,
copy the PostgreSQL connection string from your project's **Connect** panel and set
it as an environment variable before starting the backend:

```bash
export SUPABASE_DB_URL='postgresql://...'
```

Keep the connection string private; do not commit it to the repository. The
connection helper registers pgvector on each connection. The Supabase database
must have the `vector` extension and the application's `chunks` table/schema.

If `SUPABASE_DB_URL` is unset, the backend uses `DATABASE_URL`, then falls back
to the local PostgreSQL connection configured in `backend/database.py`.
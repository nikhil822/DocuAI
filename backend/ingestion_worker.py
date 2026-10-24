from datetime import datetime, timezone
from pathlib import Path

from database import get_connection
from ingestion import ingest_pdf

def update_job(job_id: str, status: str, error: str | None = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingestion_jobs
                SET status = %s, error_message = %s, started_at = CASE
                WHEN %s = 'processing'
                THEN COALESCE(started_at, NOW())
                ELSE started_at
                END,
                completed_at = CASE
                WHEN %s IN ('completed', 'failed')
                THEN NOW()
                ELSE completed_at
                END
                WHERE id = %s
                """,
                (status, error, status, status, job_id),
            )
            if cur.rowcount == 0:
                raise ValueError(
                    f"Ingestion job {job_id} does not exist."
                )

def process_ingestion_job(job_id: str, file_path: str, document_name: str):
    path = Path(file_path)

    try:
        update_job(job_id, "processing")
        #extract->chunk->embed->store
        pdf_bytes = path.read_bytes()
        ingest_pdf(document_name, pdf_bytes)
        update_job(job_id, "completed")

    except Exception as exc:
        print(f"Error processing ingestion job {job_id}: {exc}")

        try:
            update_job(job_id, "failed", "Document processing failed. Check the server logs for more details.")
        except Exception as update_exc:
            print(f"Error updating job status for {job_id}: {update_exc}")

    finally:
        try:
            path.unlink(missing_ok=True)  # Delete the file after processing
        except Exception as delete_exc:
            print(f"Error deleting file {file_path} for job {job_id}: {delete_exc}")
import logging
from datetime import datetime, timezone
from pathlib import Path

from database import get_connection
from ingestion import ingest_pdf

logger = logging.getLogger(__name__)

def recover_stale_jobs() -> int:
    """
    Mark jobs abandoned by a server restart as failed.

    Intended for the current single-instance, in-process
    BackgroundTasks architecture.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingestion_jobs
                SET
                    status = 'failed',
                    error_message = %s,
                    completed_at = NOW()
                WHERE status IN ('queued', 'processing')
                  AND created_at < NOW() - INTERVAL '15 minutes'
                RETURNING id
                """,
                (
                    "Ingestion was interrupted or timed out. "
                    "Please retry the upload.",
                ),
            )

            recovered_ids = cur.fetchall()

    if recovered_ids:
        logger.warning(
            "Marked %d stale ingestion jobs as failed",
            len(recovered_ids),
        )

    return len(recovered_ids)

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

        logger.info(
            "Document ingestion completed",
            extra={
                "job_id": job_id,
                "document_name": document_name,
                "indexed_chunks": result["indexed_chunks"],
            },
        )

    except Exception as exc:
        logger.exception(
            "Document ingestion failed",
            extra={
                "job_id": job_id,
                "document_name": document_name,
            },
        )

        try:
            update_job(job_id, "failed", "Document processing failed. Check the server logs for more details.")
        except Exception as update_exc:
            logger.exception(
                "Failed to update ingestion job status",
                extra={"job_id": job_id},
            )

    finally:
        try:
            path.unlink(missing_ok=True)  # Delete the file after processing
        except Exception as delete_exc:
            logger.exception(
                "Failed to delete temporary upload",
                extra={"job_id": job_id},
            )
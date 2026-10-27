"""Read-only candidate inspection, confined to the candidate-local database."""
import sqlite3
from pathlib import Path
from .db import DB_PATH
from . import service
from .core_reviews import ReviewError


def list_reviews(scope='all', search='', db_path=DB_PATH):
    conditions = {
        'all': '1=1', 'pending': "r.review_status='PENDING'",
        'reviewed': "r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION')",
        'excluded': "(r.exclude_from_training=1 OR r.review_status IN ('IGNORED','DELETED'))",
        'evaluation': 'r.evaluation_only=1',
        'eligible': "r.training_eligible=1 AND r.review_status IN ('APPROVED','FULL_CORRECTION','DIALECT_CORRECTION','CONTENT_CORRECTION') AND r.exclude_from_training=0 AND r.evaluation_only=0 AND r.contains_sensitive_data=0 AND r.contains_personal_data=0 AND r.needs_fact_check=0",
    }
    if scope not in conditions:
        raise ReviewError('INVALID_SCOPE', 'Choose a supported review filter.')
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        needle = '%' + search + '%'
        rows = conn.execute('SELECT r.*,c.title AS conversation_title,c.demo,m.conversation_id FROM reviews r JOIN messages m ON m.id=r.message_id JOIN conversations c ON c.id=m.conversation_id WHERE ' + conditions[scope] + ' AND (c.title LIKE ? OR r.original_response LIKE ? OR COALESCE(r.corrected_response,\'\') LIKE ? OR EXISTS (SELECT 1 FROM messages x WHERE x.conversation_id=c.id AND x.content LIKE ?)) ORDER BY r.id DESC LIMIT 500', (needle, needle, needle, needle)).fetchall()
        return {'items': [dict(row) for row in rows], 'limit': 500, 'scope': scope}
    finally:
        conn.close()


def get_review(review_id, db_path=DB_PATH):
    try:
        conn = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
    except sqlite3.Error:
        raise ReviewError('STORAGE_UNAVAILABLE', 'Local storage is unavailable; launch the candidate normally first.', 503) from None
    conn.row_factory = sqlite3.Row
    try:
        try:
            return service.get_review(review_id, db_path, conn=conn)
        except service.ValidationError:
            raise ReviewError('REVIEW_NOT_FOUND', 'Review not found.', 404) from None
    finally:
        conn.close()

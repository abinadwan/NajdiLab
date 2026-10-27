"""Candidate-only atomic review policy; original service remains unchanged."""
from datetime import datetime, timedelta, timezone

from . import service
from .db import DB_PATH, connect, transaction

FLAGS = ('training_eligible', 'exclude_from_training', 'evaluation_only',
         'contains_sensitive_data', 'contains_personal_data', 'needs_fact_check')
RESTRICTIVE = FLAGS[1:]

class ReviewError(service.ValidationError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def _next_revision(previous):
    old = datetime.fromisoformat(previous.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    return max(now, old + timedelta(microseconds=1)).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def update_review(review_id, action, data, db_path=DB_PATH):
    """Lock, compare, merge and write as one transaction, including revision/tags."""
    expected = data.get('expected_updated_at')
    if not isinstance(expected, str) or not expected:
        raise ReviewError('REVIEW_PRECONDITION_REQUIRED', 'Reload the review before saving; a saved revision is required.', 428)
    allowed = set(FLAGS) | {'expected_updated_at', 'review_status', 'corrected_response',
                           'review_notes', 'tags', 'reviewer_identity', 'reason'}
    if set(data) - allowed:
        raise ReviewError('INVALID_REVIEW', 'Unsupported review field.')
    for key in FLAGS:
        if key in data and not (type(data[key]) is bool or type(data[key]) is int and data[key] in (0, 1)):
            raise ReviewError('INVALID_REVIEW', 'Review flags must be booleans.')
    for key in ('corrected_response', 'review_notes', 'reason', 'review_status', 'reviewer_identity'):
        if key in data and not isinstance(data[key], str):
            raise ReviewError('INVALID_REVIEW', 'Review text fields must be strings.')
    if 'tags' in data and (not isinstance(data['tags'], list) or any(not isinstance(t, str) or t not in service.ERROR_TAGS for t in data['tags'])):
        raise ReviewError('INVALID_REVIEW', 'Unsupported error tags.')
    conn = connect(db_path)
    try:
        with transaction(conn):
            if service._has_review_events(conn):
                raise ReviewError('SCHEMA_UNSUPPORTED', 'This candidate supports existing migrations 001–004 only.', 503)
            row = conn.execute('SELECT * FROM reviews WHERE id=?', (review_id,)).fetchone()
            if row is None:
                raise ReviewError('REVIEW_NOT_FOUND', 'Review not found.', 404)
            if expected != row['updated_at']:
                raise ReviewError('REVIEW_CONFLICT', 'This review changed. Your edits were not saved. Reload and compare before trying again.', 409)
            current = service.get_review(review_id, db_path, conn=conn)
            revision = _next_revision(current['updated_at'])
            payload = {key: current[key] for key in FLAGS}
            payload.update({'review_notes': current['review_notes'], 'tags': current['tags'],
                            'corrected_response': current['corrected_response'], 'review_status': current['review_status'],
                            'reviewer_identity': current['reviewer']})
            payload.update(data)
            if payload['reviewer_identity'] not in {'human', 'ai_suggestion', 'import'}:
                raise ReviewError('INVALID_REVIEW', 'Unsupported reviewer assertion.')
            payload['reviewer'] = payload['reviewer_identity']
            if action in {'exclude', 'restore', 'ignore', 'delete'}:
                # Lifecycle actions may not also edit text/flags implicitly.
                if set(data) - {'expected_updated_at', 'reason', 'reviewer_identity'}:
                    raise ReviewError('INVALID_REVIEW', 'Save edits separately before this action.')
                reason = data.get('reason', '').strip()
                if not reason:
                    raise ReviewError('INVALID_REVIEW', 'A reason is required.')
                if action == 'restore':
                    if current['review_status'] not in {'IGNORED', 'DELETED'} and not current['exclude_from_training']:
                        raise ReviewError('INVALID_REVIEW', 'Only excluded reviews can be restored.')
                    conn.execute("UPDATE reviews SET review_status='PENDING',training_eligible=0,ignored_at=NULL,ignored_reason=?,deleted_at=NULL,reviewer=?,updated_at=? WHERE id=?", (reason, payload['reviewer'], revision, review_id))
                elif action == 'exclude':
                    # Preserve an existing correction decision; mark it excluded without
                    # creating an inactive/correction contradiction in shared integrity rules.
                    if current['review_status'] == 'PENDING' and current['corrected_response'] is not None:
                        raise ReviewError('INVALID_REVIEW', 'Resolve the retained correction with the exclusion flag selected before excluding again.')
                    state = current['review_status'] if current['corrected_response'] is not None else 'IGNORED'
                    conn.execute('UPDATE reviews SET review_status=?,training_eligible=0,exclude_from_training=1,ignored_at=?,ignored_reason=?,deleted_at=NULL,reviewer=?,updated_at=? WHERE id=?', (state, revision, reason, payload['reviewer'], revision, review_id))
                else:
                    if current['corrected_response'] is not None:
                        raise ReviewError('INVALID_REVIEW', 'Use Exclude to preserve this correction and its integrity.')
                    state = 'IGNORED' if action == 'ignore' else 'DELETED'
                    conn.execute('UPDATE reviews SET review_status=?,training_eligible=0,exclude_from_training=1,ignored_at=?,ignored_reason=?,deleted_at=?,reviewer=?,updated_at=? WHERE id=?', (state, revision if action == 'ignore' else None, reason, revision if action == 'delete' else None, payload['reviewer'], revision, review_id))
                return service.get_review(review_id, db_path, conn=conn)
            if current['review_status'] in {'IGNORED', 'DELETED'}:
                raise ReviewError('INVALID_REVIEW', 'Restore this review before changing its decision.')
            if action == 'approve':
                # Approve is a deliberate decision to use the original, but must not
                # silently discard a previously saved correction.
                if current['corrected_response'] is not None:
                    raise ReviewError('INVALID_REVIEW', 'This review has a saved correction; edit the correction or exclude it.')
                payload['review_status'] = 'APPROVED'
            elif action not in {'correct', 'save'}:
                raise ReviewError('INVALID_REVIEW', 'Unsupported review action.')
            if payload['review_status'] == 'APPROVED' and current['corrected_response'] is not None:
                raise ReviewError('INVALID_REVIEW', 'A saved correction cannot be discarded by approval.')
            if action == 'correct' and payload['review_status'] not in service.CORRECTION_REVIEW_STATUSES:
                raise ReviewError('INVALID_REVIEW', 'Choose a correction type.')
            if payload['review_status'] in service.CORRECTION_REVIEW_STATUSES:
                if not isinstance(payload['corrected_response'], str) or not payload['corrected_response'].strip():
                    raise ReviewError('INVALID_REVIEW', 'A complete correction is required.')
            elif payload['review_status'] != 'APPROVED':
                raise ReviewError('INVALID_REVIEW', 'Choose approve or a correction decision.')
            if any(payload[key] for key in RESTRICTIVE):
                payload['training_eligible'] = False
            service._save_review_conn(conn, review_id, payload, db_path)
            conn.execute('UPDATE reviews SET updated_at=?,ignored_reason=? WHERE id=?', (revision, current['ignored_reason'], review_id))
            return service.get_review(review_id, db_path, conn=conn)
    finally:
        conn.close()

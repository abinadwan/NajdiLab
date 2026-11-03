"""Read-only consent provenance shared by review and dataset boundaries."""
import json


INCOMPLETE_CONTEXT_WARNING = (
    'Earlier chat context was not collected with continuous consent, or its completeness '
    'cannot be verified. This segment can be reviewed but cannot be used for training or '
    'evaluation. Start a fresh chat and enable collection before its first turn.'
)


def collection_context(row):
    """Non-Chat sources keep their existing policy; Chat requires explicit provenance."""
    row = dict(row)
    metadata = row.get('metadata_json') or '{}'
    try:
        metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
    except (ValueError, TypeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    is_chat = row.get('source') == 'najdilab_chat' or metadata.get('origin') == 'najdilab_chat'
    if not is_chat:
        return {}
    complete = metadata.get('context_complete') is True
    return {'context_scope': 'continuous_consented_segment_only', 'context_complete': complete,
            'context_warning': None if complete else INCOMPLETE_CONTEXT_WARNING}

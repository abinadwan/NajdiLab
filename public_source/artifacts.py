"""Explicit data-file retrieval from verified local version snapshots only."""
from .core_datasets import DATA_FILES, checked_version
from .core_reviews import ReviewError


def read_artifact(version, filename):
    if filename not in DATA_FILES:
        raise ReviewError('ARTIFACT_DENIED', 'Only explicitly listed dataset JSONL files are available. Archives, databases, credentials and model files are never served.', 403)
    _, manifest, blobs = checked_version(version)
    if filename not in manifest['files'] or filename not in manifest['sha256']:
        raise ReviewError('ARTIFACT_DENIED', 'File is not authorized by the selected version manifest.', 403)
    return blobs[filename]

"""The product version: the single source for the server, the API and the interface.

V2.1.0 names the current development candidate on `update-project` (V2.0.0 plus the unified chat
composer). It is not a release or a production approval: PR #23 stays Draft until the owner
approves it. Dataset versions, model files, migration numbers and dependency versions are
separate and do not follow this number. Each owner-approved batch of features or fixes gets one
SemVer step, recorded with its reason in CHANGELOG.md (not one per commit).
"""
APP_VERSION = '2.1.0'
DISPLAY_VERSION = f'V{APP_VERSION}'
RELEASE_STATUS = 'development-candidate'

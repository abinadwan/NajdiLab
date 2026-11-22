"""The product version: the single source for the server, the API and the interface.

V2.3.0 names the Guided Wizard development candidate on `update-project`.
The Advanced Workspace presentation is preserved as a separately loaded legacy bundle.
The candidate awaits review and PR #23 retains its Draft status.
Dataset versions, model files, migration numbers and dependency versions are
separate and do not follow this number. Each owner-approved batch of features or fixes gets one
SemVer step, recorded with its reason in CHANGELOG.md (not one per commit).
"""
APP_VERSION = '2.3.0'
DISPLAY_VERSION = f'V{APP_VERSION}'
RELEASE_STATUS = 'development-candidate'

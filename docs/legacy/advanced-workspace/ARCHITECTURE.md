# Preserved workspace architecture

Historical / Archived Documentation

## Source ownership

| File | Responsibility |
| --- | --- |
| `static/advanced-workspace.html` | Inert templates for the original launcher, mode controls, navigation and seven specialist panels |
| `static/advanced-workspace.js` | On-demand mounting, preserved mode controller and explicit developer restoration |
| `static/advanced-workspace.css` | Legacy presentation and mode-specific visibility |
| `static/app.js` | Shared routing, record editor, specialist operations and event binding through `bindLegacyEvents` |
| `static/chat.js` | Shared Chat and preserved external-export bindings through `NajdiChat.bindLegacyExports` |
| `static/prepare-data.js` | Four-stage Wizard, selection, check fingerprint and browser drafts |
| `app/service.py`, `app/dataset_platform.py` | Shared record, planning, diagnostics, version and Frozen operations |
| `app/gold_management.py`, `app/gold_lifecycle.py` | Attested downloads, deletion plans, audit, identity reservations and locks |
| `scripts/restore_advanced_workspace.py` | Copies static source into a new marked child of `.test-tmp` and changes initialization only there |

The historical implementation embedded the panels in `static/index.html` and defined the mode controller in `static/app.js`. Git commit `8753463f27009f8574614294e8e45425142d5706` preserves that complete arrangement. Extraction in V2.3.0 separates presentation loading while preserving shared implementations.

## Runtime boundaries

The default shell calls `initGuidedWorkspace`. It ignores the old mode preference and keeps workflow storage intact. Its ordinary route loads no legacy bundle. An explicit retained diagnostic route imports the module, reads the templates, mounts specialist panels and binds their controls once. Concurrent navigation uses a revision guard so a delayed panel load cannot replace a later navigation.

`restoreWorkspace` additionally mounts the old launcher, mode controls and navigation, then installs the preserved controller. Only an explicitly modified temporary shell calls that restoration entry point. The official shell has no UI control leading to it.

Both presentations call the same HTTP APIs and backend guards. Presentation changes provide no bypass for privacy, leakage, loss masks, Frozen integrity, typed deletion confirmation or ownership/dependency proof.

## Dependencies and compatibility

The bundle uses browser ES modules, fetch, templates, localStorage and native dialogs. It depends on the current shared app globals and local CSS/font assets. It has no separate backend or framework. Storage failure retains in-memory usability. Browser storage belongs to the same browser origin. Restoring the historical preference does not grant permissions or restore missing datasets.

Changes to the app initialization, panel IDs or shared globals require a new restoration test. [Procedure](RESTORE_GUIDE.md).

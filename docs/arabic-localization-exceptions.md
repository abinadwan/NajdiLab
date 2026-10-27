# Intentional Arabic localization exceptions

English is the default interface and documentation language. Arabic below is data, language-processing logic or a compatibility value, not untranslated interface chrome. Do not change it as part of localization. This inventory lists locations and reasons without reproducing private text. Data-bearing historical manifests remain a public-release gate, not cleared public examples.

| File | Arabic lines | Reason |
|---|---|---|
| `app/clean_export.py` | 515, 516, 521, 522, 523, 528, 529, 530, 531, 543, 547, 548, 557, 702 | Arabic language classification, greeting/tool/context matching vocabulary; translation would change processing. |
| `app/dataset_platform.py` | 28 | Najdi diagnostic phrase vocabulary used in dataset analysis. |
| `app/phase35_analysis.py` | 22, 23 | Arabic failure-analysis matching terms. |
| `app/phase37_hardening.py` | 21 | Synthetic Arabic generation result used by the development diagnostic. |
| `app/phase38_dataset.py` | 23, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 67, 68, 80, 81, 82, 83, 84, 85, 86, 87, 115, 116, 117, 118, 119, 120 | Protected Arabic corpus construction examples, normalization mappings and review decision data. |
| `app/phase39_edits.py` | 84, 106, 108, 115, 116, 119, 126, 130, 133 | Protected real correction/evaluation text, reviewer notes and legacy decision enum values. |
| `app/service.py` | 2367, 2368, 2369, 2370, 2371, 2372, 2373, 2394, 2395, 2396, 2418, 2419, 2429, 2430, 2442, 2455, 2456, 2457 | Synthetic Arabic demo conversations and training examples; only presentation titles were localized. |
| `app/tool_runtime.py` | 129 | Arabic question-mark sentence-boundary regex; parser behavior must remain unchanged. |
| `docs/corpus-v1.1/01-behavior-spec.md` | 38, 41, 55, 56, 57, 58, 59, 60, 61, 62, 68, 69, 70, 71, 72, 73, 74, 95, 99, 152, 153, 156, 159, 162 | Arabic linguistic examples and language-specific design vocabulary. |
| `docs/corpus-v1.1/04-quality-gates.md` | 27, 28, 29, 30, 31, 32, 33, 35, 36, 56 | Arabic linguistic examples and deterministic vocabulary under evaluation. |
| `scripts/acceptance_v11.py` | 70, 71, 76, 77, 79, 84, 85, 91, 92, 213, 220, 227, 271, 286 | Synthetic Arabic round-trip/integration fixtures. |
| `scripts/audit_v006_metrics.py` | 194, 223, 230 | Arabic corpus-analysis/search/normalization vocabulary and corpus-specific identifier checks; preserving analytical behavior. Identifier checks require privacy review before public distribution. |
| `scripts/audit_v006_metrics_v2.py` | 109, 126 | Arabic corpus-analysis/search/normalization vocabulary and corpus-specific identifier checks; preserving analytical behavior. Identifier checks require privacy review before public distribution. |
| `scripts/audit_v006_metrics_v3.py` | 159, 198 | Arabic corpus-analysis/search/normalization vocabulary and corpus-specific identifier checks; preserving analytical behavior. Identifier checks require privacy review before public distribution. |
| `scripts/build_gold_v007_balanced.py` | 21 | Arabic corpus-analysis/search/normalization vocabulary and corpus-specific identifier checks; preserving analytical behavior. Identifier checks require privacy review before public distribution. |
| `scripts/build_v007_epoch2_report.py` | 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29 | Protected historical evaluator annotations keyed by review IDs. |
| `scripts/build_v007_eval_report.py` | 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35 | Protected historical evaluator annotations keyed by review IDs. |
| `scripts/complete_review_queue.py` | 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 189, 191, 192, 228, 230, 232, 234, 235 | Protected actual historical correction manifest; requires private-data rights/privacy disposition before publication. |
| `scripts/dataset_influence_audit.py` | 159, 160, 214, 216, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 292, 295, 297, 350, 365 | Arabic corpus-analysis/search/normalization vocabulary and corpus-specific identifier checks; preserving analytical behavior. Identifier checks require privacy review before public distribution. |
| `scripts/export_v007_e1_ollama.py` | 46, 47, 48, 49, 50, 51, 52, 53, 54, 55 | Arabic evaluation prompts for the historical export workflow. |
| `scripts/gold_v007_balancing.py` | 258 | Arabic corpus-analysis/search/normalization vocabulary and corpus-specific identifier checks; preserving analytical behavior. Identifier checks require privacy review before public distribution. |
| `scripts/ingest_test.py` | 30, 31 | Synthetic Arabic collector round-trip content. |
| `scripts/measure_v006_overlap.py` | 159 | Arabic corpus-analysis/search/normalization vocabulary and corpus-specific identifier checks; preserving analytical behavior. Identifier checks require privacy review before public distribution. |
| `scripts/verify_audit.py` | 48, 49, 55, 62, 63, 69, 76, 77, 83, 84, 225, 226, 227, 228, 229, 230, 231, 232, 233, 294, 295, 297 | Arabic corpus-analysis/search/normalization vocabulary and corpus-specific identifier checks; preserving analytical behavior. Identifier checks require privacy review before public distribution. |
| `static/app.js` | 107 | Three legacy Phase 3.9 Arabic API decision values; visible labels are English. |
| `tests/test_clean_export.py` | 24, 25, 26, 28, 33, 40, 49, 50, 80, 81, 89, 98, 99, 104, 107, 111, 112, 116, 119, 131, 132, 154, 155, 161, 162, 171, 178, 179, 186, 190, 198, 209, 211, 216, 217, 221, 222 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_dataset_balancer.py` | 21, 36 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_dataset_platform.py` | 19, 32, 33, 34, 77, 137, 176 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_dataset_quality.py` | 20, 22, 33, 34, 39 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_najdilab.py` | 65, 69, 82, 101, 102, 103, 107, 119, 143, 145, 148, 153, 155, 159, 163, 167, 172, 173, 174, 188, 191, 194, 212, 264, 265, 279, 280, 297, 298, 303, 307, 308, 314, 322, 326, 329, 332, 333, 335, 336, 342, 343, 349, 353, 355, 358, 374, 381, 384, 385, 391, 407, 420, 421, 425, 431, 437, 441, 468, 472, 475, 505, 507, 540, 541, 542, 543, 560, 561, 593, 595, 636, 647, 649, 654, 667, 668, 674, 676, 703, 708, 713, 723, 729, 753, 764, 774, 775, 781, 790, 791, 792, 803, 808, 885, 886, 887, 888, 899, 953, 954, 959, 960, 961, 962, 963, 983, 987, 992, 1020 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_phase35_analysis.py` | 14, 15 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_phase37_tool_hardening.py` | 111, 112, 113 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_phase38_dataset.py` | 55, 57 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_phase38_ui.py` | 65, 67, 68 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_phase39_api.py` | 19, 20, 23, 30 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_phase39_mt06_repair.py` | 10, 12 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_phase3_benchmark.py` | 11, 12 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_phase3_review.py` | 31, 33 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_review_integrity.py` | 31, 98, 103 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_review_lifecycle.py` | 23, 36, 38, 51, 52, 53 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_review_management.py` | 41, 45, 49, 69, 72, 78, 79, 96, 97, 98, 100, 101, 123, 135, 137, 164, 186 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_runtime_control.py` | 17, 24 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |
| `tests/test_training_control.py` | 14, 21, 22, 23, 56 | Synthetic Arabic processing, review/content fixtures or compatibility enum assertions; not interface copy. |

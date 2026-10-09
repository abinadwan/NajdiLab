# Training Export

## الأهلية

ملفات التدريب تقبل فقط سجلات `training_eligible=true` مع `archived=false` و`evaluation_only=false` و`exclude_from_training=false`. بيانات Demo مستبعدة افتراضيًا ما لم يختر المستخدم تضمينها صراحة. عينات `evaluation_only` غير المؤرشفة وغير المستبعدة تذهب فقط إلى `evaluation_holdout.jsonl` ولا تظهر في SFT أو direct language أو preference.

## هدف SFT وـmulti-turn

يصدّر كل سجل SFT معلومات صريحة لا تعتمد على تخمين المستهلك:

- `target_message_index`: موضع آخر رد assistant الذهبي.
- `train_on_last_assistant_only: true`.
- `message_loss_mask`: صفر لكل رسائل السياق وواحد للرد الذهبي الأخير فقط.

تبقى ردود assistant السابقة داخل `messages` كسياق. يقرأ `scripts/train_najdi_sft.py` القناع فعليًا، ويبني `labels=-100` لكل tokens السياق، ثم يترك labels آخر رد assistant الذهبي فقط. يستخدم loader قالب المحادثة الخاص بالـtokenizer، ويرفض التدريب إذا لم يكن القالب prefix-stable بدل تخمين حد الهدف.

## فصل التدريب عن التقييم

يُنفّذ التقسيم على مستوى `conversation_id` ببذرة ثابتة `42`. لا تظهر أي محادثة مختارة للتقييم في التدريب. يُحفظ بحد أقصى 8 سجلات ممثلة من كل محادثة evaluation ويُختار المزيد من المحادثات deterministically حتى قرابة 12% (ضمن 10–15%)، مع تفضيل تنوع `domain` و`review_status`. إذا توفرت ثلاث محادثات أو أكثر، يفشل التصدير إن لم يتوزع holdout على ثلاث منها على الأقل.

## موازنة multi-turn

يُطبق حد أقصى deterministic قدره 10 سجلات multi-turn لكل `conversation_id`. عند تجاوز الحد، يختار المصدر subset ثابتًا ببذرة 42 مع الحفاظ على تنوع حالات المراجعة قدر الإمكان. هذه الموازنة تخص ملفات Gold فقط ولا تعدّل قاعدة البيانات.

## فحص التكرار

قبل التصدير تعرض الواجهة report:

- exact: SHA-256 للنص المطبّع (casefold + توحيد الفراغات).
- near: `SequenceMatcher` بنسبة 0.90 فأعلى، من دون package إضافي.

يُزال الـexact duplicate من ملفات Gold فقط، بناءً على النص المستهدف للتدريب بعد التطبيع. أولوية الاحتفاظ هي: `APPROVED` ثم `FULL_CORRECTION` ثم `DIALECT_CORRECTION` ثم `CONTENT_CORRECTION` ثم ترتيب الإدخال الثابت. لا تُحذف أي سجلات من قاعدة البيانات. الـnear duplicates لا تزال تقريرًا فقط ولا تُحذف تلقائيًا.

## بنية النسخة

```text
exports/gold-v001/
├── manifest.json
├── sft.jsonl
├── multi_turn.jsonl
├── direct_language.jsonl
├── preference_pairs.jsonl
├── evaluation_holdout.jsonl
├── full_archive.json
└── dedup_report.json
```

`sft.jsonl` يحتوي سجلات قصيرة (رسالتان)، و`multi_turn.jsonl` يحتوي السياق الكامل ذي أكثر من رسالتين. لا تختلط النصوص المباشرة أو أزواج التفضيل مع ملفات SFT. `full_archive.json` أرشيف تدقيق فقط وليس ملف تدريب.

## Manifest

يحافظ الـmanifest على الحقول السابقة، ويضيف أعداد سجلات ومحادثات التدريب والتقييم، `split_seed`, `exact_duplicates_removed`, `near_duplicate_count`, `demo_records_included`, وخلاصة الـvalidation. قيمة `sha256` خريطة checksum لكل ملف بيانات وأرشيف وتقرير؛ manifest لا يحسب نفسه لتجنب مرجع دائري.

كل تصدير ينشئ رقمًا جديدًا ولا يعدّل مجلد نسخة سابقة. الكتابة تتم في مجلد مؤقت ثم rename ذري.

يسجل `manual_data_export_history` العناصر اليدوية التي ظهرت فعليًا في ملفات JSONL لكل نسخة. عند فهرسة نسخة قديمة تُقرأ ملفات JSONL فقط ولا يُعدّل أي ملف أو manifest قديم.

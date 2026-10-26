# المعمارية

## الحدود

NajdiLab v1 يتولى أربعة أدوار فقط: جمع المحادثات، المراجعة البشرية، إدارة البيانات الذهبية، والتصدير. التدريب وعمليات GGUF/Ollama وأوزان المودل خارج المشروع عمدًا.

## التدفق

```text
أي Model / Provider
        │ POST /api/v1/turn
        ▼
Collector محلي (127.0.0.1)
        │ transaction
        ▼
SQLite: conversation + user + assistant + pending review
        │
        ▼
واجهة المراجعة العربية
        │ قرار بشري وتصحيح منفصل
        ▼
Training eligibility + privacy gates
        │ dedup report
        ▼
exports/gold-vNNN + manifest + SHA-256
```

## المكونات

- `app/server.py`: خادم HTTP محلي من مكتبة Python القياسية، API والملفات الثابتة.
- `app/service.py`: منطق الأعمال، المعاملات، المراجعات، إعادة بناء السياق والتصدير.
- `app/dataset_platform.py`: خدمات قراءة الإصدارات، الصحة، Candidate balancing، hashes، وLocked Eval leakage detection. تستدعي منطق اختيار النوافذ الموثوق بدل نسخه في الواجهة.
- `app/db.py`: الاتصال الآمن، WAL، migrations، redaction للحقول السرية.
- `static/`: واجهة HTML/CSS/JS عربية RTL بلا framework.
- `migrations/`: schema مرقّم append-only.

## قرارات السلامة

- الخادم يرفض أي bind غير `127.0.0.1`.
- حد جسم الطلب 2MB، وتُطبق headers تمنع framing وcontent sniffing.
- الحقول التي تشبه API key أو token أو password تُستبدل بـ`[REDACTED]` في metadata وgeneration settings.
- الإدخال المركب يتم داخل `BEGIN IMMEDIATE`؛ الفشل يرجع العملية كاملة.
- التصحيح لا يكتب فوق `messages.content` ولا `reviews.original_response`.
- `evaluation_only` و`exclude_from_training` يجعلان `training_eligible=false` عند الحفظ.
- التصدير يكتب أولًا إلى مجلد مؤقت ثم يعيد تسميته ذريًا.

## Model-agnostic وfuture-ready

المزود والمودل والإصدار موجودة كmetadata وليست علاقة ثابتة. الحقول `parent_message_id` و`candidate_group_id` و`judge_result_json` تدعم AI user / candidate models / critic / judge مستقبلًا. جدول `comparison_records` يحفظ المقارنات دون تنفيذ generation.

## مسار Najdi Corpus v1.1 (المرحلة 1 مكتملة: تصميم معتمد في 2026-10-23 — غير منفّذ)

بتاريخ 2026-10-23 أُضيفت حزمة تصميم المرحلة 1 في [`docs/corpus-v1.1/`](corpus-v1.1/README.md). تعتمد الحزمة NajdiLab مصدرًا وحيدًا للحقيقة وواجهةً أساسية، وNajdiTrain بيئة تشغيل التدريب فقط. تصف الحزمة مواصفة سلوك أبو عدوان، وربط Gold/Silver/Bronze وبوابات G1–G4 بالمكونات الحالية، ودورة مراجعة للعناصر اليدوية تمنع أي سجل مولّد من أن يصبح قابلًا للتدريب دون موافقة بشرية صريحة، ومتطلبات الأمان، ومراجعة migrations 005–007. لم يُغيَّر أي كود أو schema أو بيانات، وكل تنفيذ لاحق يتطلب موافقة مستقلة. اعتمد المالك تصميم المرحلة 1 في 2026-10-23؛ المرحلة 1A غير مصرّح بها.

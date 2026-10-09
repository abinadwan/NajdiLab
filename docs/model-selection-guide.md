# دليل اختيار النموذج الأساسي

## المصادر المدعومة

- **Local / WSL:** مجلد Hugging Face يحتوي `config.json` وTokenizer وأوزانًا قابلة للتدريب.
- **Hugging Face repository ID:** يسجل المرجع و`revision` فقط؛ لا ينزّل أوزانًا.
- **Ollama:** مرشح معلوماتي للاستدلال فقط؛ ملفات GGUF لا تُعامل كأوزان تدريب.

الاكتشاف المحلي محدود إلى 10 جذور، مستوى مجلد واحد، و100 نتيجة. لا يوجد مسح شامل للنظام ولا كشف لمسارات سرية.

## خطوات الاختيار

1. افتح **التدريب ← إعداد التدريب**.
2. من **سجل النماذج** أدخل معرّفًا ثابتًا، اسم العرض، والمجلد المحلي أو repository ID.
3. سجّل المرشح. التسجيل لا ينزّل شيئًا ولا يجعله صالحًا للتدريب.
4. نفّذ تحقق التوافق. يجب أن تصبح `validation_status=VALID` وألا يكون `excluded=true`.
5. اختر المرشح وإصدار البيانات ثم نفّذ فحص الجاهزية.
6. أنشئ مهمة DRAFT. لا تنتقل إلى READY إذا تغيّرت بصمة النموذج أو الإصدار.

Ministral التاريخي ظاهر للتتبع بحالة `EXCLUDED/HISTORICAL`، وليس اختيارًا افتراضيًا. عند عدم وجود مرشح صالح تعرض الواجهة **غير مُعدّ** وتعطّل إنشاء المهمة.

## عقد التنفيذ

تُحفظ هوية النموذج (`id`, `path/repository_id`, `revision`, `fingerprint`) داخل Snapshot المهمة. يبني runtime أمر التنفيذ من هذه القيم ويمرر `--model-path`, `--model-id`, و`--model-revision` إلى `najdilab_training_adapter.py`. لا يوجد fallback خفي إلى Ministral.

## API

- `GET/POST /api/v1/training/models`
- `POST /api/v1/training/models/discover`
- `POST /api/v1/training/models/{id}/validate`
- `POST /api/v1/training/preflight`


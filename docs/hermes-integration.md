# تكامل Hermes السلبي — NajdiLab v1.1

يجمع التكامل نسخة آمنة من كل دور مكتمل عبر حدث Hermes `post_llm_call`. الاستدعاء داخل مسار الدور لا ينفذ HTTP: يهيئ payload صغيرًا ويضعه في queue محدودة، ثم يرسل worker daemon الطلب في الخلفية. الفشل يسجل warning فقط ولا يغير الرد ولا يعيد تشغيل Hermes.

## الإعداد

الإعداد في `config.yaml` تحت `hooks.outbound`:

```yaml
- name: najdilab-passive
  enabled: true
  url: http://127.0.0.1:8770/api/v1/hermes-hook
  events: [post_llm_call]
  timeout: 1
  fields:
    - turn_id
    - user_message
    - assistant_response
    - model
    - provider
    - platform
    - conversation_key_hash
    - system_prompt_version
    - generation_settings
    - acceptance_test
```

لإيقاف الجمع فقط غيّر `enabled` إلى `false` ثم أعد تحميل/تشغيل gateway. لا يتطلب الإيقاف تعديل NajdiLab أو حذف البيانات.

## الخصوصية والحقول

- `conversation_key_hash` هو SHA-256 لمفتاح المحادثة الداخلي، ولا يرسل رقم هاتف أو Telegram ID أو المفتاح الخام.
- `system_prompt_version` هو SHA-256 فقط؛ نص system prompt لا يغادر Hermes.
- `generation_settings` allowlist محصور في `temperature`, `top_p`, `top_k`, `seed`, و`context_length`.
- لا ترسل headers أو API keys أو cookies أو conversation history أو tool calls/results.
- يحتفظ NajdiLab بالرد الأصلي immutable، وينشئ Review بحالة `PENDING` و`training_eligible=false` افتراضيًا.

## الاستمرارية ومنع التكرار

يستخدم NajdiLab hash المحادثة كهوية مصدر ثابتة. ويستخدم `turn_id` كـ`source_message_id`؛ فإعادة إرسال الحدث نفسه تعيد السجل الموجود ولا تنشئ messages أو reviews مكررة.

## التشغيل عند الفشل

التكامل best-effort وfail-open. إذا كان NajdiLab متوقفًا أو بطيئًا، يواصل Hermes تسليم الرد للمستخدم. المحاولات والمهلة تخص worker الخلفي فقط، والـqueue المحدودة تسقط الأحداث الزائدة مع warning بدل الضغط على مسار المستخدم.

## Endpoint

`POST http://127.0.0.1:8770/api/v1/hermes-hook`

المسار يقبل payload lifecycle المصفّى من Hermes، ثم يحوله داخل transaction واحدة إلى conversation ورسالة user ورسالة assistant وreview. مسار collector العام `POST /api/v1/turn` يبقى متاحًا للتكاملات المحلية الأخرى.

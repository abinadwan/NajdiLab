# مخطط قاعدة البيانات

قاعدة البيانات: `data/najdilab.db`. عند كل اتصال: `foreign_keys=ON` و`journal_mode=WAL` و`busy_timeout=15000`.

| الجدول | الغرض | أهم القيود |
|---|---|---|
| `schema_migrations` | تتبع migrations المطبقة | نسخة فريدة |
| `conversations` | رأس محادثة مستقل عن المودل | `external_conversation_id` فريد، `demo` صريح |
| `messages` | كل turn كسجل | role محدد، ترتيب فريد داخل المحادثة، FK |
| `reviews` | قرار وتصحيح منفصلان | review واحد لكل assistant message، original immutable بالتطبيق |
| `review_tags` | وسوم متعددة | قائمة مقيدة ومفتاح مركب |
| `manual_sft_items` | حوارات يدوية | provenance + privacy/training gates |
| `direct_language_texts` | نص بلا user/assistant | طبقة لغة ونوع مصدر |
| `preference_pairs` | rejected/preferred | سياق JSON وأصل محفوظ |
| `manual_data_versions` | snapshots لكل تعديل يدوي | `(item_type, item_id, version_number)` فريد و`changed_by` مقيد |
| `manual_data_export_history` | ربط العنصر بنسخ Gold التي ظهر فيها | ربط فريد بكل Dataset Version |
| `comparison_records` | مقارنة مودلين مستقبلًا | candidate group وjudge result |
| `dataset_versions` | سجل النسخ المصدرة | اسم النسخة فريد وmanifest محفوظ |
| `settings` | إعدادات محلية مستقبلية | key/value JSON |

## ثبات البيانات الأصلية

`messages.content` هو النص الأصلي. عند إنشاء review يُنسخ الرد إلى `reviews.original_response`. المراجعة تحدّث `corrected_response` فقط؛ `APPROVED` يفرض أن يكون التصحيح `NULL`، بينما حالات التصحيح تفرض وجود نسخة مصححة كاملة.

## حالة التدريب والخصوصية

توجد flags مستقلة: `training_eligible`, `archived`, `exclude_from_training`, `evaluation_only`, `contains_sensitive_data`, `contains_personal_data`, و`needs_fact_check`. لا يدخل سجل تدريب إلا بقرار `training_eligible=1`. الأرشفة أو الاستبعاد أو التقييم تمنع التصدير، من دون حذف السجل. عناصر البيانات اليدوية تحمل أيضًا `version_number`, `parent_item_id`, و`updated_at`.

## نسخ البيانات اليدوية

كل تعديل على SFT أو النص المباشر أو DPO يزيد `version_number` ويكتب snapshot كاملًا في `manual_data_versions` مع الحقول المتغيرة وملاحظة التعديل والفاعل. الاستنساخ ينشئ سجلًا مستقلًا ويربطه بالأصل عبر `parent_item_id`.

## إعادة بناء السياق

عند تصدير review، تُقرأ كل رسائل المحادثة مرتبة حتى `turn_index` للرد المراجع. يستبدل محتوى آخر assistant في نسخة التصدير فقط بالنص المصحح إن وُجد، بينما تظل قاعدة البيانات الأصلية كما هي.


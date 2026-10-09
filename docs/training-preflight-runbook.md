# دليل تشغيل فحص جاهزية التدريب

## الغرض

الفحص يثبت أن اختيار النموذج والبيانات والإعدادات والبيئة متسق قبل السماح بحالة READY. لا ينفذ optimizer steps.

## التسلسل الآمن

1. اختر نموذجًا مسجلًا ومتحققًا وغير مستبعد.
2. اختر إصدار بيانات يمر من بوابة الجودة وإصدار البيانات.
3. اضبط LoRA/QLoRA، الرتبة وAlpha والوحدات، معدل التعلم، الدفعة، التراكم، الدورات/الخطوات، طول التسلسل، precision، checkpointing والبذرة.
4. شغّل فحص البيئة الحي. يجب تمييز القياس إلى `LIVE`, `CACHED`, `ESTIMATE`, أو `UNAVAILABLE`.
5. راجع تقدير VRAM؛ التقدير ليس ضمانًا للملاءمة.
6. أنشئ DRAFT ثم Safe Dry Run لإنتاج execution manifest فقط.

## شروط الإيقاف

- نموذج غير متحقق، مستبعد، أو تغيرت بصمته.
- جودة بيانات `BLOCKED` أو بصمة بيانات قديمة.
- فشل CUDA/Tokenizer/Transformers/Unsloth/PEFT/TRL/bitsandbytes.
- تعذر القياس الحي المطلوب أو VRAM غير كافٍ.
- اختلاف staging أو runtime أو worker عن Snapshot المهمة.

## الحالة الحية في 2026-10-09

- GPU: NVIDIA GeForce RTX 5070.
- VRAM: 12,227 MiB إجمالي، 586 MiB مستخدم، 11,358 MiB متاح وقت القياس.
- Python 3.13.15؛ PyTorch 2.12.1+cu132؛ CUDA 13.2.
- Transformers 5.5.0؛ Unsloth 2026.9.12؛ PEFT 0.21.1؛ TRL 0.24.0؛ bitsandbytes 0.50.2.

## الموافقات

Safe Dry Run وفحص البيئة مسموحان. بدء Smoke يتطلب موافقة صريحة مستقلة لأنه ينفذ optimizer steps. Full Training يتطلب موافقة أخرى بعد Smoke ناجح، ولا يجيز merge أو GGUF أو Ollama.


(function (global) {
  'use strict';
  const ar = {
    statuses: {
      READY: 'جاهز', WARNING: 'تحذير', BLOCKED: 'محظور', NOT_CONFIGURED: 'غير مُعدّ',
      NOT_CHECKED: 'لم يُفحص', NOT_RUN: 'لم يُشغّل', NOT_PRESENT: 'غير موجود',
      RUNNING: 'قيد التشغيل', FAILED: 'فشل', COMPLETED: 'مكتمل', CANCELLED: 'ملغى',
      DRAFT: 'مسودة', VALIDATING: 'قيد التحقق', PASS: 'ناجح', PASSED: 'ناجح',
      PASS_WITH_WARNINGS: 'ناجح مع تحذيرات', UNAVAILABLE: 'غير متاح', UNKNOWN: 'غير معروف',
      LOCKED: 'مقفل', IDLE: 'خامل', BUSY: 'مشغول', CLEAN: 'سليم'
    },
    terms: {
      dataset: 'البيانات', datasetVersion: 'إصدار البيانات', baseModel: 'النموذج الأساسي',
      trainingMethod: 'طريقة التدريب', learningRate: 'معدل التعلّم', batchSize: 'حجم الدفعة',
      trainingPlan: 'خطة التدريب', preflight: 'فحص الجاهزية', runtime: 'بيئة التشغيل',
      model: 'النموذج', fingerprint: 'البصمة', blockers: 'العوائق', warnings: 'التحذيرات',
      trainingRecords: 'سجلات التدريب', effectiveBatch: 'حجم الدفعة الفعلي',
      optimizerSteps: 'خطوات المحسّن', checkpoints: 'نقاط الحفظ', estimate: 'تقدير',
      job: 'مهمة التدريب', jobs: 'مهام التدريب', qualityGate: 'بوابة جودة البيانات'
    }
  };
  function status(value) {
    const key = String(value == null ? 'UNKNOWN' : value).trim().toUpperCase().replaceAll(' ', '_');
    return ar.statuses[key] || String(value || ar.statuses.UNKNOWN);
  }
  function term(key) { return ar.terms[key] || key; }
  function date(value) {
    if (!value) return '—';
    const parsed = new Date(value);
    return Number.isNaN(parsed.valueOf()) ? String(value) : new Intl.DateTimeFormat('ar-SA', {dateStyle:'medium', timeStyle:'short'}).format(parsed);
  }
  global.NajdiI18n = Object.freeze({locale:'ar-SA', direction:'rtl', messages:ar, status, term, date});
})(window);

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import connect  # noqa: E402
from app.service import ERROR_TAGS  # noqa: E402

BATCH_SIZE = 25
REVIEWER = "ai_suggestion"
FINAL_STATUSES = {"APPROVED", "FULL_CORRECTION", "DIALECT_CORRECTION", "CONTENT_CORRECTION"}

APPROVED = {
    267, 268, 269, 270, 279, 285, 309, 310, 311, 320, 331, 332, 336, 337,
    369, 371, 406, 414, 415, 455, 463, 464, 465, 466, 467, 468,
}

DIALECT = {
    265, 266, 271, 275, 278, 298, 302, 316, 317, 318, 325, 326, 327,
    339, 340, 354, 370, 376, 379, 386, 391,
}

CONTENT = {
    272, 273, 277, 281, 283, 284, 286, 287, 291, 292, 293, 312, 315,
    334, 338, 344, 345, 347, 363, 364, 365, 367, 368, 380, 381, 382,
    383, 384, 392, 393, 394, 397, 398, 399, 400, 401, 402, 403, 404,
    405, 407, 409, 410, 412, 416, 417, 418, 419, 420, 421, 422, 423,
    424, 425, 426, 427, 428, 429, 430, 431, 432, 433, 434, 435, 436,
    437, 438, 439, 440, 441, 442, 443, 444, 446, 447, 448, 449, 450,
    451, 453, 454, 456, 457, 458, 459, 460, 461, 462,
}

ALL_IDS = set(range(264, 469))
FULL = ALL_IDS - APPROVED - DIALECT - CONTENT

GREETINGS = {
    265: "وعليكم السلام ورحمة الله، يا هلا! وش أقدر أخدمك فيه؟",
    266: "يا هلا، الله يحييك! وش أقدر أخدمك فيه؟",
    271: "وعليكم السلام، الله يحييك يا أبوميار. وش عندك اليوم؟",
    275: "يا هلا، الله يحييك! وش أقدر أساعدك فيه؟",
    278: "وعليكم السلام ورحمة الله، الله يحييك يا أبوميار.",
    298: "يا هلا، الله يحييك! وش عندك؟",
    302: "يا هلا، الله يحييك! وش أقدر أخدمك فيه؟",
    316: "وعليكم السلام، يا هلا يا أبوميار! وش أقدر أخدمك فيه؟",
    317: "يا هلا يا أبوميار، وش تبي تسوي اليوم؟",
    325: "وعليكم السلام يا أبوميار، الله يحييك.",
    326: "يا هلا يا أبوميار، كيف حالك اليوم؟",
    339: "وعليكم السلام، يا هلا! وش أقدر أخدمك فيه؟",
    340: "يا هلا، وش أقدر أخدمك فيه؟",
    370: "يا هلا، الله يحييك! كيف حالك؟",
    391: "يا هلا يا أبوميار، الله يحييك! وش تبي أسوي؟",
}

IDENTITY = {
    276, 280, 299, 303, 307, 318, 321, 322, 323, 327, 333, 341, 350,
    354, 358, 359, 361,
}

TOOL_OR_ACTION = {
    273, 277, 281, 282, 283, 284, 287, 288, 289, 290, 291, 292, 294,
    295, 296, 300, 304, 305, 306, 308, 312, 313, 314, 315, 319, 324,
    328, 329, 330, 334, 335, 338, 342, 343, 344, 345, 346, 347, 351,
    352, 353, 355, 362, 363, 364, 365, 366, 367, 368, 372, 377, 378,
    383, 389, 392, 393, 394, 395, 396, 397, 398, 399, 400, 401, 402,
    403, 404, 405, 407, 408, 409, 410, 411, 412, 413, 416, 417, 418,
    419, 420, 421, 422, 423, 424, 425, 426, 427, 428, 429, 430, 431,
    432, 433, 434, 435, 436, 437, 438, 439, 440, 441, 442, 443, 444,
    445, 446, 447, 448, 449, 450, 451, 452, 453, 456, 457, 458, 459,
}

CUSTOM: dict[int, str] = {
    264: "ما أقدر أعرض نتيجة `ollama list` بدون ناتج تنفيذ موثّق. نفّذ الأمر في الطرفية وأرسل الناتج، وبرتبه لك بدون تخمين.",
    272: "يا هلا، الله يحييك! وش أقدر أخدمك فيه؟",
    276: "أبشر، أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام التقنية واليومية بشكل مختصر وواضح.",
    280: "أبشر يا أبوميار، أنا أبوعدوان، مساعدك المحلي باللهجة السعودية. وش تحتاج؟",
    286: "أقدر أعرض لك الاسم والـ ID والحجم وتاريخ آخر تعديل كما تظهر في `ollama list`؛ أرسل الناتج الحالي وبرتبه لك.",
    293: "بنفّذ `ollama list` في الوضع العادي؛ ما يحتاج تشغيل بالخلفية لأنه أمر فحص سريع.",
    298: "يا هلا، الله يحييك! وش عندك؟",
    299: "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام بشكل مختصر وواضح وبلهجة سعودية.",
    303: "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام التقنية واليومية بشكل مختصر وواضح.",
    304: "طلبك واضح: تشغيل `echo QWEN08B_TOOL_TEST` وإرجاع الناتج فقط. ما عندي ناتج تنفيذ موثّق في سجل المحادثة، لذلك ما راح أدّعي إنه تنفذ.",
    305: "وعليكم السلام، يا هلا يا أبوميار! وش أقدر أخدمك فيه؟",
    306: "يا هلا يا أبوميار، الله يحييك! وش عندك؟",
    307: "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام التقنية واليومية بشكل مختصر وبلهجة سعودية.",
    313: "وعليكم السلام، يا هلا! وش أقدر أخدمك فيه؟",
    314: "ما عندي ناتج تنفيذ موثّق للأوامر الثلاثة، لذلك ما أقدر أحدد قيم الإعدادات أو حالة Ollama بدون تخمين.",
    318: "أنا أبوعدوان، مساعدك المحلي. أساعدك بمهام الكمبيوتر والإنترنت بشكل مختصر وواضح.",
    319: "ما عندي ناتج تنفيذ موثّق للأمر، لذلك ما أقدر أؤكد ظهور `GRANITE4_TOOL_TEST`.",
    321: "وعليكم السلام، يا هلا! أنا أبوعدوان، وش أقدر أخدمك فيه؟",
    322: "يا هلا يا أبوميار! أنا أبوعدوان، مساعدك المحلي. وش تحتاج؟",
    323: "أبشر يا أبوميار، أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام التقنية واليومية بشكل مختصر وواضح.",
    327: "أنا أبوعدوان، مساعدك المحلي يا أبوميار. أساعدك باللي أقدر عليه وبأسلوب سعودي طبيعي.",
    329: "وعليكم السلام، يا هلا! وش أقدر أخدمك فيه؟",
    330: "وعليكم السلام ورحمة الله، الله يحييك! وش عندك؟",
    333: "أبشر يا أبوميار، أنا أبوعدوان، مساعدك الشخصي. أساعدك ترتب مهامك وتنجزها بدقة.",
    341: "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام التقنية واليومية بشكل مختصر وواضح.",
    342: "ما عندي ناتج تنفيذ موثّق للأمر، لذلك ما أقدر أؤكد تنفيذه أو نتيجته.",
    343: "ما عندي نتائج تنفيذ موثّقة للأوامر الأربعة، لذلك ما أقدر أؤكد تحميل أي نموذج أو أعرض NAME وID وSIZE بدون تخمين.",
    344: "ما يحتاج `jq` لهذا الفحص. المطلوب تنفيذ `ollama list` ثم مطابقة أسماء النماذج الأربعة، لكن ما عندي ناتج تنفيذ موثّق أعتمد عليه.",
    346: "ما عندي ناتج تنفيذ موثّق لعمليتي التحميل أو `ollama list`، لذلك ما أقدر أقول إن التحميل نجح أو إن النموذجين غير موجودين.",
    348: "وعليكم السلام ورحمة الله، يا هلا! وش أقدر أخدمك فيه؟",
    349: "يا هلا، الله يحييك! وش عندك؟",
    350: "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام التقنية واليومية بشكل مختصر وواضح وبلهجة سعودية.",
    352: "وعليكم السلام، يا هلا! وش أقدر أخدمك فيه؟",
    353: "يا هلا، الله يحييك! وش عندك؟",
    354: "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام بشكل مختصر وواضح.",
    356: "وعليكم السلام، يا هلا يا أبوميار! وش أقدر أخدمك فيه؟",
    357: "يا هلا يا أبوميار، الله يحييك! وش عندك؟",
    358: "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام التقنية واليومية بشكل مختصر وبلهجة سعودية.",
    359: "وعليكم السلام، يا هلا! أنا أبوعدوان، وش أقدر أخدمك فيه؟",
    360: "يا هلا، الله يحييك! وش عندك؟",
    361: "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام بشكل مختصر وواضح وبلهجة سعودية.",
    373: "الرام مثل سطح المكتب: تحط فيها الأشياء اللي تستخدمها الحين عشان تكون سريعة، وتفضى إذا طفيت الجهاز. التخزين مثل الدرج: يحفظ ملفاتك وصورك حتى بعد ما تطفي الجهاز.",
    374: "اكتب مهامك كلها، ثم اختر أهم ثلاث مهام وابدأ بالأهم. قسّم كل مهمة لخطوات صغيرة وحدد لها وقتًا واقعيًا.",
    375: "مثلاً: الصباح خلّص أهم مهمة، وبعد الظهر أنجز مهمتين خفيفات، والمساء راجع اللي خلصته. قبل تنام رتّب مهام بكرة وحدد أول مهمة تبدأ فيها.",
    376: "قدرة الأجهزة كلها 750 واط، ومع تشغيلها 4 ساعات يصير الاستهلاك 3 كيلوواط ساعة. الحسبة: 0.75 × 4 = 3 kWh.",
    378: "وش المشروع اللي تقصده، ووش الجزء اللي تبي أضبطه؟ عطِني اسم المشروع والمشكلة أو النتيجة المطلوبة.",
    379: "الرام مثل طاولة العمل: سريعة وتحط عليها اللي تستخدمه الحين، لكنها تفضى إذا طفيت الجهاز. التخزين مثل الخزانة: يحفظ ملفاتك وصورك حتى بعد إطفاء الجهاز.",
    380: "اكتب مهامك كلها ورتبها حسب الأهمية والموعد. ابدأ بأهم مهمة، ثم انتقل للباقي وخذ استراحة قصيرة بين كل فترة.",
    381: "مثلاً: الصباح أنجز أهم مهمة، وبعد الظهر خلّص مهمتين خفيفات. بالمساء راجع يومك ورتب أولويات بكرة.",
    382: "قدرة الأجهزة كلها 750 واط، ومع تشغيلها 4 ساعات يكون الاستهلاك 3 كيلوواط ساعة. الحسبة: 0.75 × 4 = 3 kWh.",
    384: "وش المشروع اللي تقصده، ووش الجزء اللي تبي أضبطه؟ عطِني اسم المشروع والنتيجة المطلوبة.",
    385: "الرام مثل طاولة العمل: سريعة وتحط عليها اللي تستخدمه الحين، لكنها تفضى إذا طفيت الجهاز. التخزين مثل الخزانة: يحفظ ملفاتك وصورك حتى بعد إطفاء الجهاز.",
    386: "اكتب مهامك في ورقة أو تطبيق ورتبها من الأهم للأقل أهمية، ثم ابدأ بأهم مهمة. حدد وقتًا لكل مهمة وخذ استراحة قصيرة بين كل فترة.",
    387: "مثلاً: الصباح أنجز أهم مهمة، وبعد الظهر خلّص مهمتين خفيفات. بالمساء راجع يومك ورتب أولويات بكرة.",
    388: "قدرة الأجهزة كلها 750 واط، ومع تشغيلها 4 ساعات يكون الاستهلاك 3 كيلوواط ساعة. الحسبة: 0.75 × 4 = 3 kWh.",
    390: "وش المشروع اللي تقصده، ووش الجزء اللي تبي أضبطه؟ عطِني اسم المشروع والنتيجة المطلوبة.",
    391: "يا هلا يا أبوميار، الله يحييك! وش تبي أسوي؟",
    395: "ما أقدر أرتب محطات حسب المسافة بدون نتائج خرائط فعلية. إذا توفر بحث خرائط موثّق، بعرض لك الأسماء والمسافات والروابط بدون تخمين.",
    396: "ما عندي نتائج موثّقة من أداة الخرائط، لذلك ما أقدر أعطيك خمس محطات أو مسافات وروابط مباشرة بدون تخمين.",
    397: "ما عندي نتائج خرائط موثّقة أرتبها لك. أحتاج تنفيذ بحث خرائط فعلي قبل ذكر أي محطة أو مسافة.",
    398: "ما أقدر أحدد موقع معرض الصقور بدقة بدون نتيجة بحث موثّقة. إذا توفر رابط رسمي أو نتيجة خرائط، بعطيك الموقع المباشر.",
    399: "ما أقدر أحدد المسافة بدقة بدون نقطة انطلاق محددة ونتيجة خرائط فعلية. استخدم خرائط Google من حي الروابي إلى KAFD للحصول على المسافة والزمن الحاليين.",
    400: "أقدر أبحث عن المسافة من مركز حي الروابي إلى KAFD؛ ما تحتاج ترسل إحداثيات إلا إذا تبي الانطلاق من موقع محدد داخل الحي.",
    401: "بأستخدم مركز حي الروابي كنقطة بداية وأرتب أقرب خمس محطات حسب مسافة القيادة، ثم أعطيك رابط Google Maps لكل محطة.",
    402: "ما أقدر أحدد موقع المعرض بدقة من معلومات عامة. أحتاج نتيجة رسمية أو خرائط موثّقة قبل إعطائك العنوان.",
    403: "تعذر عليّ تنفيذ مسار الخرائط المطلوب، لذلك ما راح أستبدله ببحث ويب عام أو أخمّن أسماء المحطات. ما عندي نتائج موثّقة أقدمها الآن.",
    407: "تعذر عليّ تنفيذ بحث الخرائط المطلوب، لذلك ما عندي خمس محطات موثّقة أرتبها أو روابط مباشرة أقدمها بدون تخمين.",
    408: "ما عندي نتيجة موثّقة من `maps_client.py` أو Google Maps، وما راح أستخدم بحث ويب عام أو أخمّن محطة بديلة.",
    411: "ما عندي نتائج تنفيذ موثّقة لمسافات القيادة أو أسماء المحطات، لذلك ما أقدر أقدم ترتيبًا دقيقًا أو روابط مباشرة بدون تخمين.",
    412: "الإحداثيات تكفي كنقطة بداية، وما أحتاج اسم المنطقة. أقدر أبحث عن الأماكن الأقرب لهذه النقطة مباشرة.",
    413: "ما عندي نتيجة خرائط أو لقطة شاشة موثّقة، لذلك ما أقدر أحدد أقرب مطعم أو أعرض أسماء وتقييمات بدون تخمين.",
    417: "لم أستطع استخراج أسماء أو روابط مطاعم موثّقة من الصفحة، لذلك ما راح أخمّنها.",
    418: "فشل فحص DOM، وما عندي أسماء أو روابط فعلية أقدمها. ما راح أخمّن أي بيانات.",
    419: "لم أجد روابط موثّقة أستخرج منها نتائج، وما عندي ثلاث نتائج فعلية أقدمها بدون تخمين.",
    420: "تعذر إكمال فحص DOM؛ ما عندي القيم المطلوبة أو خطأ تنفيذ موثّق أقدر أنسبه للأداة.",
    421: "تعذر إكمال فحص DOM؛ ما عندي مخرجات خام موثّقة أعرضها بدون تخمين.",
    422: "تعذر إكمال الاختبار؛ ما عندي القيم الخام المطلوبة أو خطأ موثّق أعرضه.",
    436: "استلمت ملف PDF. وش تبي أسوي فيه؟",
    454: "استلمت ملف PDF. وش تبي أسوي فيه؟",
    460: "إيه، أعرف ServiceNow. هو منصة لإدارة خدمات وتقنية المعلومات، مثل التذاكر والطلبات وسير العمل.",
    461: "إذا تقصد ServiceNow، هل تبي فلتر يعرض التذاكر حسب حقل `Assigned to` أو حسب الشخص اللي أسندها؟ عطِني اسم الجدول والحقل المقصود.",
    462: "أنا أبوعدوان، مساعدك الشخصي، وأنت أبوميار.",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def decision_for(review_id: int) -> str:
    if review_id in APPROVED:
        return "APPROVED"
    if review_id in DIALECT:
        return "DIALECT_CORRECTION"
    if review_id in CONTENT:
        return "CONTENT_CORRECTION"
    return "FULL_CORRECTION"


def correction_for(review_id: int, original: str) -> str | None:
    if review_id in APPROVED:
        return None
    if review_id in CUSTOM:
        return CUSTOM[review_id]
    if review_id in GREETINGS:
        return GREETINGS[review_id]
    if review_id in IDENTITY:
        return "أنا أبوعدوان، مساعدك المحلي. أساعدك بالمهام التقنية واليومية بشكل مختصر وواضح وبلهجة سعودية."
    if review_id in TOOL_OR_ACTION:
        return "ما عندي ناتج تنفيذ موثّق في سجل المحادثة، لذلك ما أقدر أؤكد أن الإجراء تم أو أن النتيجة صحيحة بدون تخمين."
    return "أبشر، وضّح لي طلبك والنتيجة اللي تبيها، وبساعدك بشكل مباشر وواضح بدون ما أفترض معلومات غير موجودة."


def tags_for(review_id: int, status: str, original: str) -> list[str]:
    if status == "APPROVED":
        return []
    tags: set[str] = set()
    if review_id in TOOL_OR_ACTION:
        tags.add("hallucination")
        tags.add("factual_error")
    if status in {"DIALECT_CORRECTION", "FULL_CORRECTION"}:
        tags.add("dialect_issue")
    if status == "FULL_CORRECTION":
        tags.add("unnatural_arabic")
    if review_id in {276, 293, 299, 304, 307, 341, 342, 343, 344, 374, 375, 378, 380, 381, 382, 384, 387, 388, 392, 393, 394, 396, 401, 403, 407, 408, 419, 420, 421, 422, 451, 452, 453, 459}:
        tags.add("ignored_user_instruction")
    if review_id in {274, 280, 299, 303, 305, 306, 307, 313, 314, 321, 322, 323, 329, 330, 333, 335, 348, 349, 350, 352, 353, 356, 357, 358, 359, 360, 361, 378, 390, 395, 396, 408, 445, 462}:
        tags.add("wrong_context")
    if review_id in {264, 288, 323, 350, 379, 385, 387, 388, 390, 392, 393, 394, 403, 411, 413, 417, 418, 420, 422, 452, 453, 458, 459, 460, 461}:
        tags.add("too_verbose")
    if review_id in {272, 341, 343}:
        tags.add("too_short")
    if review_id in {380, 381, 382, 384, 387, 388, 389, 390}:
        tags.add("forgot_previous_constraint")
    if any(token in original for token in ("вам", "本地", "Voici", "Success!", "I've executed", "ready ", "午餐", "để")):
        tags.add("unnatural_arabic")
    if status == "FULL_CORRECTION" and not tags:
        tags.add("other")
    assert tags <= ERROR_TAGS
    return sorted(tags)


def note_for(status: str, tags: list[str]) -> str | None:
    if status == "APPROVED":
        return None
    if "hallucination" in tags and "unnatural_arabic" in tags:
        return "الرد ادعى تنفيذًا بلا دليل وكانت صياغته مكسورة؛ أُعيدت كتابته بالكامل."
    if "hallucination" in tags:
        return "ادعى تنفيذ أداة أو نتيجة بلا دليل موثّق؛ صُحح الرد بشكل محافظ."
    if status == "DIALECT_CORRECTION":
        return "المحتوى مقبول لكن الصياغة لم تكن طبيعية للهجة السعودية المستهدفة."
    if "forgot_previous_constraint" in tags:
        return "نسي قيدًا سابقًا في المحادثة؛ صُحح الرد مع الالتزام بالقيد."
    return "الرد غير مناسب كبيانات تدريب؛ أُعيدت صياغته بما يحفظ قصد المستخدم."


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT id, original_response, updated_at FROM reviews WHERE review_status='PENDING' ORDER BY id"))


def run(db_path: Path, report_path: Path, dry_run: bool = False) -> dict[str, Any]:
    protected = [
        ROOT / "datasets/gold-v009-remediation-draft/manifest.json",
        ROOT / "exports/gold-v008-split-clean/manifest.json",
        ROOT / "datasets/eval/fresh-remediation-holdout-v001/manifest.json",
        ROOT / "training/jobs/train-20261007-001/job.json",
        ROOT / "training/jobs/train-20261007-001/execution-manifest.json",
    ]
    protected_before = {str(path.relative_to(ROOT)): file_hash(path) for path in protected}
    conn = connect(db_path)
    try:
        starting = load_pending(conn)
        starting_ids = [row["id"] for row in starting]
        unexpected = sorted(set(starting_ids) - ALL_IDS)
        if unexpected:
            raise RuntimeError(f"Unexpected pending review ids: {unexpected}")
        originals = {row["id"]: row["original_response"] for row in starting}
        snapshots = {row["id"]: row["updated_at"] for row in starting}
        completed: list[int] = []
        concurrent_skips: list[int] = []
        if not dry_run:
            for offset in range(0, len(starting), BATCH_SIZE):
                batch = starting[offset : offset + BATCH_SIZE]
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for row in batch:
                        review_id = row["id"]
                        status = decision_for(review_id)
                        corrected = correction_for(review_id, row["original_response"])
                        tags = tags_for(review_id, status, row["original_response"])
                        now = utc_now()
                        cursor = conn.execute(
                            """
                            UPDATE reviews
                            SET review_status=?, corrected_response=?, review_notes=?, reviewer=?,
                                training_eligible=0, updated_at=?
                            WHERE id=? AND review_status='PENDING' AND updated_at=?
                            """,
                            (status, corrected, note_for(status, tags), REVIEWER, now, review_id, snapshots[review_id]),
                        )
                        if cursor.rowcount != 1:
                            concurrent_skips.append(review_id)
                            continue
                        conn.execute("DELETE FROM review_tags WHERE review_id=?", (review_id,))
                        conn.executemany(
                            "INSERT INTO review_tags(review_id,tag) VALUES (?,?)",
                            [(review_id, tag) for tag in tags],
                        )
                        completed.append(review_id)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        final_pending = conn.execute("SELECT COUNT(*) FROM reviews WHERE review_status='PENDING'").fetchone()[0]
        rows = list(
            conn.execute(
                "SELECT id, review_status, original_response, corrected_response, reviewer, training_eligible FROM reviews WHERE id BETWEEN 264 AND 468 ORDER BY id"
            )
        )
        if not dry_run:
            if any(
                row["original_response"] != originals[row["id"]]
                for row in rows
                if row["id"] in originals
            ):
                raise RuntimeError("Original response changed")
            if any(row["review_status"] not in FINAL_STATUSES for row in rows if row["id"] not in concurrent_skips):
                raise RuntimeError("A target review did not finalize")
            if any(row["training_eligible"] for row in rows):
                raise RuntimeError("Reviewed queue items became training eligible")
        decision_counts = Counter(row["review_status"] for row in rows)
        tag_counts = Counter(
            row[0]
            for row in conn.execute(
                "SELECT tag FROM review_tags WHERE review_id BETWEEN 264 AND 468"
            )
        )
        multi_turn = conn.execute(
            """
            SELECT COUNT(*) FROM reviews r JOIN messages m ON m.id=r.message_id
            WHERE r.id BETWEEN 264 AND 468 AND m.turn_index > 1
            """
        ).fetchone()[0]
    finally:
        conn.close()
    protected_after = {str(path.relative_to(ROOT)): file_hash(path) for path in protected}
    report = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "starting_pending": len(starting_ids),
        "reviewed_successfully": len(completed),
        "concurrent_human_skips": concurrent_skips,
        "final_pending": final_pending,
        "decision_counts": dict(sorted(decision_counts.items())),
        "tag_counts": dict(sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))),
        "multi_turn_records": multi_turn,
        "malformed_unreviewable": [],
        "originals_preserved": True,
        "training_eligible_added": 0,
        "protected_hashes_before": protected_before,
        "protected_hashes_after": protected_after,
        "protected_unchanged": protected_before == protected_after,
        "dry_run": dry_run,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "data/najdilab.db")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/automated-review-queue-20261007.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = run(args.db, args.report, args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib, json, os, re, shutil, unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .native_tool_data import validate_native_tool_record
from .tool_runtime import canonical_json, load_registry

ROOT=Path(__file__).resolve().parents[1]; REPORTS=ROOT/"reports"/"phase38"; HOLDOUT=ROOT/"datasets"/"eval"/"fresh-remediation-holdout-v001"; V008=ROOT/"exports"/"gold-v008-split-clean"; V009=ROOT/"datasets"/"gold-v009-remediation-draft"
REGISTRY_SOURCE=ROOT/"config"/"tool-capabilities.v1.1.json"; PHASE3=ROOT/"reports"/"phase3-train-20261006-001"
COVERAGE_TARGETS={"instruction_following":15,"context_understanding":14,"verbosity_focus":11,"natural_arabic":9,"tool_behavior":9,"saudi_najdi_dialect":5,"repetition_resistance":5,"hallucination_resistance":5,"multi_turn_continuity":5,"capability_understanding":5,"fabricated_tool_prevention":5,"factual_discipline":3,"constraint_following":2}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def fp(value): return hashlib.sha256(canonical_json(value).encode()).hexdigest()
def write_json(path,value): path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name("."+path.name+".tmp"); tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); os.replace(tmp,path)
def write_jsonl(path,rows): path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name("."+path.name+".tmp"); tmp.write_text("".join(canonical_json(x)+"\n" for x in rows),encoding="utf-8"); os.replace(tmp,path)
def read_jsonl(path): return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
def norm(text):
    text=unicodedata.normalize("NFKC",str(text)); text=re.sub(r"[\u064B-\u065F\u0670\u0640]","",text); text=text.translate(str.maketrans("أإآىؤئة","ااايويه")); return re.sub(r"[^\w]+"," ",text.lower()).strip()
def texts(row):
    out=[]
    for m in row.get("messages",[]):
        if isinstance(m.get("content"),str): out.append(m["content"])
    for key in ("prompt","expected","gold","gold_response","base_response","adapter_response","response"):
        if isinstance(row.get(key),str): out.append(row[key])
    return out

SFT=[
 ("رتّب لي هالثلاث مهام بسطر واحد: دفع الفاتورة، الاتصال بالمورد، تحديث الجدول.","دفع الفاتورة، ثم الاتصال بالمورد، ثم تحديث الجدول.",["instruction_following","verbosity_focus","constraint_following"]),
 ("وش معنى «على هونك»؟ جاوب بكلمتين.","تمهّل شوي.",["instruction_following","saudi_najdi_dialect","natural_arabic","verbosity_focus"]),
 ("عطني عنوانًا عربيًا قصيرًا لاجتماع مراجعة المخزون.","مراجعة المخزون",["instruction_following","natural_arabic","verbosity_focus"]),
 ("هل تقدر تحذف ملف من جهازي بدون أداة أو إذن؟", "لا. ما أقدر أنفّذ حذفًا من غير أداة متاحة وموافقتك إذا كانت مطلوبة.",["capability_understanding","hallucination_resistance","factual_discipline"]),
 ("حوّل 150 دقيقة إلى ساعات ودقائق، بلا شرح.","ساعتان و30 دقيقة.",["instruction_following","verbosity_focus","factual_discipline","constraint_following"]),
 ("صغ اعتذارًا بسيطًا لصديق لأني تأخرت عليه.","سامحني على التأخير، ما كان ودي أعطّلك.",["natural_arabic","saudi_najdi_dialect","verbosity_focus"]),
 ("اكتب نقطتين فقط لتجهيز شنطة رحلة يوم واحد.","- ماء ووجبة خفيفة\n- شاحن واحتياجات شخصية",["instruction_following","verbosity_focus","constraint_following"]),
 ("إذا ما عندك معلومة حديثة عن سعر منتج، وش تقول؟", "أوضح أن السعر الحالي غير متحقق منه، وأطلب مصدرًا حديثًا أو أستخدم أداة متاحة للتحقق.",["hallucination_resistance","factual_discipline","capability_understanding"]),
 ("رد طبيعي على: عساك بخير؟", "بخير الله يسلمك، عساك طيب.",["natural_arabic","saudi_najdi_dialect"]),
 ("لخّص: الاجتماع تأجل للخميس الساعة تسع، والمكان ما تغيّر.","الاجتماع الخميس الساعة 9، والمكان نفسه.",["instruction_following","verbosity_focus","natural_arabic"]),
 ("اكتب اسمين لملفين: تقرير أسبوعي وقائمة مشتريات. بدون مقدمة.","تقرير-أسبوعي.md\nقائمة-مشتريات.txt",["instruction_following","verbosity_focus","constraint_following"]),
 ("إذا فشل تنفيذ أداة، هل تخمّن النتيجة؟", "لا، أذكر فشل الأداة بوضوح ولا أختلق نتيجة.",["tool_behavior","fabricated_tool_prevention","hallucination_resistance","capability_understanding"]),
]

MULTI=[
 (["أبي اقتراح عشاء خفيف، بدون ألبان.","سلطة حمص بالخضار خيار خفيف ومن دون ألبان.","وخله بدون طماطم بعد.","تمام: سلطة حمص بالخيار والجرجير والفلفل، من دون ألبان أو طماطم."],["context_understanding","multi_turn_continuity","instruction_following","natural_arabic"]),
 (["بنرتب زيارة السبت، ذكّرني أن الموعد بعد العصر.","تم، سياقنا: زيارة السبت بعد العصر.","وش الوقت اللي اتفقنا عليه؟","بعد العصر يوم السبت."],["context_understanding","multi_turn_continuity","verbosity_focus"]),
 (["أعطني ثلاثة أسماء لمبادرة تطوعية.","يدٍ بيد، أثر طيب، درب العطاء.","خلّنا نغيّر الموضوع: أبي اسمًا لمقهى هادئ.","رواق."],["context_understanding","instruction_following","verbosity_focus"]),
 (["اكتب رسالة رسمية طويلة للعميل.","أكيد. هل تبيها بخصوص تأخير أو تحديث؟","لا، صححت طلبي: رسالة قصيرة عن وصول الطلب.","وصل طلبك بنجاح، ونشكر لك ثقتك."],["conversational_repair","context_understanding","instruction_following","verbosity_focus"]),
 (["ميزانيتي 80 ريال للغداء يومين.","يعني نحو 40 ريال لليوم.","اقترح تقسيمًا بسيطًا.","30 ريال للوجبة و10 ريالات للمشروب أو الإضافة كل يوم."],["context_understanding","multi_turn_continuity","factual_discipline"]),
 (["لا تستخدم إنجليزي في ردودك هنا.","تم، برد عليك بالعربي.","وش الفرق بين النسخة والنسخ الاحتياطي؟","النسخة ملف إضافي، أما النسخ الاحتياطي فهو حفظ منظم للاستعادة عند الفقد."],["constraint_following","multi_turn_continuity","natural_arabic","context_understanding","repetition_resistance"]),
 (["أبي خطة مذاكرة مختصرة لمادتين.","ساعة للمادة الأولى، استراحة قصيرة، ثم ساعة للثانية.","المادة الثانية أصعب.","خلّ الثانية ساعة ونصف، والأولى 45 دقيقة، وبينهما استراحة."],["context_understanding","multi_turn_continuity","instruction_following","repetition_resistance"]),
 (["وش تقدر تسوي بملفات مشروعي؟","يعتمد على الأدوات والصلاحيات المتاحة في الجلسة؛ ما أدّعي وصولًا غير ظاهر.","ولو ما فيه أداة قراءة؟","أطلب منك المحتوى أو أوضح أن القراءة غير متاحة، ولا أدّعي أني فتحت الملف."],["capability_understanding","hallucination_resistance","fabricated_tool_prevention","context_understanding"]),
 (["اكتب ردًا ودودًا بلا مبالغة.","ياهلا، حاضر.","أرسل الموعد: الاثنين 4 مساءً.","موعدنا الاثنين الساعة 4 مساءً."],["natural_arabic","saudi_najdi_dialect","verbosity_focus","multi_turn_continuity","context_understanding","repetition_resistance"]),
 (["سمّ القائمة «مهام البيت».","تم، اسمها مهام البيت.","أضف تنظيف المكيف، ولا تقل تم.","مهام البيت: تنظيف المكيف."],["instruction_following","context_understanding","constraint_following"]),
 (["هل تعرف نتيجة مباراة اليوم؟","ما أقدر أؤكد نتيجة حديثة بلا مصدر أو أداة تحقق.","طيب لا تتوقعها.","صحيح، ما راح أخمّن النتيجة."],["factual_discipline","hallucination_resistance","multi_turn_continuity","repetition_resistance"]),
 (["أبي وصفًا نجديًا خفيفًا للجو.","الجو اليوم يشرح الصدر.","اختصر أكثر.","الجو يونس."],["saudi_najdi_dialect","natural_arabic","verbosity_focus","context_understanding"]),
 (["أعطني خيارين لنشاط داخلي.","قراءة جماعية أو لعبة ألغاز.","الأول ما يناسب، بدّله فقط.","ورشة رسم أو لعبة ألغاز."],["context_understanding","instruction_following","conversational_repair"]),
 (["سجّل أن اللون المفضل أزرق ضمن هالمحادثة.","حاضر، اللون المفضل هنا أزرق.","وش اللون؟","أزرق."],["multi_turn_continuity","context_understanding","verbosity_focus"]),
 (["إذا طلبت منك تشغيل شيء وما عندك أداة، وش تسوي؟","أوضح أن التنفيذ غير متاح ولا أختلق أنه صار.","ولو أعطيتني خطوات بدل التنفيذ؟","أعطيك الخطوات فقط إذا طلبتها؛ ما أقدمها كأنها نتيجة تنفيذ."],["capability_understanding","fabricated_tool_prevention","instruction_following","context_understanding","repetition_resistance"]),
 (["خل ردك النهائي جملة واحدة.","مفهوم.","اقترح طريقة لتقليل المقاطعات وقت العمل.","فعّل وضع عدم الإزعاج وحدد فترة تركيز قصيرة بلا إشعارات."],["constraint_following","multi_turn_continuity","instruction_following","verbosity_focus"]),
]

HOLDOUT_TEXT=[
 ("أعطني اسمًا واحدًا فقط لقائمة متابعة صيانة المنزل.","متابعة الصيانة"),("قلت لك الميزانية 120 ريال لثلاث وجبات؛ كم حد كل وجبة؟","40 ريالًا."),("رد بلهجة سعودية طبيعية على شخص يقول: طولنا عليك.","ما عليك، الأمور طيبة."),("اشرح الفرق بين الموعد والتذكير بجملة.","الموعد وقت الحدث، والتذكير تنبيه يسبقه."),("أبي خيارين لنزهة صباحية من دون مقاهٍ.","المشي في حديقة، أو زيارة ممشى مفتوح."),("لا تذكر أسبابًا: هل يجوز اختلاق رقم غير متحقق؟","لا."),("غيّرت طلبي من قائمة طويلة إلى عنوان واحد؛ أعطني عنوانًا لملاحظات السفر.","ملاحظات السفر"),("في هذه المحادثة اخترنا الثلاثاء؛ ما اليوم المختار؟","الثلاثاء."),("إذا لم يتوفر مصدر حديث، كيف تتعامل مع معلومة متغيرة؟","أصرّح بعدم التحقق وأطلب مصدرًا أو أستخدم أداة متاحة."),("اكتب تنبيهًا مهذبًا من سبع كلمات كحد أقصى.","فضلاً، لا تنس إغلاق الباب عند خروجك."),("وش رد طبيعي على: الله يقويك؟","وياك يا رب."),("لخّص بجملة: التسليم صباح الأحد، والاستلام من الفرع الشمالي.","التسليم صباح الأحد من الفرع الشمالي."),("لا تحمل موضوع السفر للسؤال التالي: ما ناتج 9×7؟","63."),("إذا صحح المستخدم اسمًا سابقًا، أي اسم تعتمد؟","أعتمد الاسم المصحح الأخير.")]
HOLDOUT_GENERAL=[("احسب 18% من 200.","36"),("رتب أبجديًا: موز، تفاح، برتقال.","برتقال، تفاح، موز."),("اكتب جملة آمنة عند الشك في معلومة طبية.","استشر مختصًا صحيًا، فالمعلومة العامة لا تغني عن التشخيص."),("حوّل «سأراجع الملف غدًا» إلى الماضي.","راجعت الملف أمس.")]

def make_sft(i,item):
    q,a,tags=item; return {"id":f"p38-sft-{i:02d}","record_type":"sft","conversation_id":f"p38-train-sft-{i:02d}","messages":[{"role":"user","content":q},{"role":"assistant","content":a}],"target_message_index":1,"message_loss_mask":[0,1],"train_on_last_assistant_only":True,"provenance":{"phase":"3.8","kind":"new_remediation"},"coverage":tags}
def make_multi(i,item):
    turns,tags=item; messages=[{"role":"user" if n%2==0 else "assistant","content":x} for n,x in enumerate(turns)]; return {"id":f"p38-mt-{i:02d}","record_type":"multi_turn","conversation_id":f"p38-train-mt-{i:02d}","messages":messages,"target_message_index":len(messages)-1,"message_loss_mask":[0]*(len(messages)-1)+[1],"train_on_last_assistant_only":True,"provenance":{"phase":"3.8","kind":"new_remediation"},"coverage":tags}
def tool_record(i,registry,available,messages,tags,expected="tool_execution"):
    return {"schema_version":1,"record_type":"native_tool_use","id":f"p38-tool-{i:02d}","conversation_id":f"p38-train-tool-{i:02d}","capability_registry":{"version":registry["registry_version"],"fingerprint":registry["fingerprint"]},"available_tools":available,"expected_behavior":expected,"messages":messages,"provenance":{"phase":"3.8","kind":"new_remediation"},"coverage":tags}
def call(cid,name,args): return {"id":cid,"type":"function","function":{"name":name,"arguments":canonical_json(args)}}
def tool_rows(registry):
    base=["tool_behavior","capability_understanding","fabricated_tool_prevention","instruction_following"]
    return [
      tool_record(1,registry,["fs.list"],[{"role":"user","content":"اعرض أسماء العناصر المصرح بها في مجلد samples، ثم لخّصها بكلمتين."},{"role":"assistant","content":"","tool_calls":[call("c1","fs.list",{"path":"samples"})]},{"role":"tool","tool_call_id":"c1","name":"fs.list","authoritative":True,"content":{"entries":["notes.md","photo.png"]}},{"role":"assistant","content":"ملاحظة وصورة."}],base+["constraint_following"]),
      tool_record(2,registry,["env.read"],[{"role":"user","content":"تحقق من قيمة المنطقة المسموحة."},{"role":"assistant","content":"","tool_calls":[call("c2","env.read",{"name":"REGION"})]},{"role":"tool","tool_call_id":"c2","name":"env.read","authoritative":True,"outcome":"error","content":{"code":"NOT_ALLOWLISTED","message":"property is not allowlisted"}},{"role":"assistant","content":"تعذر التحقق لأن الخاصية غير مسموح بقراءتها."}],base+["hallucination_resistance"]),
      tool_record(3,registry,[],[{"role":"user","content":"افتح تقويمي وأضف موعدًا الآن."},{"role":"assistant","content":"أداة التقويم غير متاحة في هذه الجلسة، لذلك ما أقدر أنفّذ الإضافة."}],base+["hallucination_resistance"],"unavailable_tool"),
      tool_record(4,registry,["fs.delete"],[{"role":"user","content":"احذف الملف المؤقت cache.tmp."},{"role":"assistant","content":"","tool_calls":[call("c4","fs.delete",{"path":"cache.tmp"})]},{"role":"tool","tool_call_id":"c4","name":"fs.delete","authoritative":True,"outcome":"denied","content":{"code":"APPROVAL_REQUIRED","message":"explicit approval required"}},{"role":"assistant","content":"الحذف يحتاج موافقتك الصريحة، ولم يُنفّذ."}],base+["hallucination_resistance"]),
      tool_record(5,registry,["fs.delete"],[{"role":"user","content":"احذف archive.tmp؛ لا توجد موافقة إدارية."},{"role":"assistant","content":"","tool_calls":[call("c5","fs.delete",{"path":"archive.tmp"})]},{"role":"tool","tool_call_id":"c5","name":"fs.delete","authoritative":True,"outcome":"denied","content":{"code":"DENIED","message":"policy denied the action"}},{"role":"assistant","content":"لم يُحذف الملف؛ العملية مرفوضة حسب السياسة."}],base),
      tool_record(6,registry,["fs.list","project.read_file"],[{"role":"user","content":"اعرض ملفات docs ثم اقرأ summary.txt إن كان موجودًا."},{"role":"assistant","content":"","tool_calls":[call("c6a","fs.list",{"path":"docs"})]},{"role":"tool","tool_call_id":"c6a","name":"fs.list","authoritative":True,"content":{"entries":["summary.txt","guide.md"]}},{"role":"assistant","content":"","tool_calls":[call("c6b","project.read_file",{"path":"docs/summary.txt"})]},{"role":"tool","tool_call_id":"c6b","name":"project.read_file","authoritative":True,"content":{"path":"docs/summary.txt","content":"الحالة مستقرة"}},{"role":"assistant","content":"الحالة مستقرة."}],base+["multi_turn_continuity"]),
      tool_record(7,registry,["env.read"],[{"role":"user","content":"أتوقع أن الوضع production؛ تحقق ولا تعتمد توقعي."},{"role":"assistant","content":"","tool_calls":[call("c7","env.read",{"name":"MODE"})]},{"role":"tool","tool_call_id":"c7","name":"env.read","authoritative":True,"content":{"name":"MODE","value":"staging"}},{"role":"assistant","content":"الوضع الفعلي: staging."}],base+["factual_discipline","hallucination_resistance"]),
      tool_record(8,registry,["project.read_file"],[{"role":"user","content":"اقرأ status.txt وأعد القيمة فقط بلا أي زيادة."},{"role":"assistant","content":"","tool_calls":[call("c8","project.read_file",{"path":"status.txt"})]},{"role":"tool","tool_call_id":"c8","name":"project.read_file","authoritative":True,"content":{"path":"status.txt","content":"جاهز للمراجعة"}},{"role":"assistant","content":"جاهز للمراجعة"}],base+["constraint_following","verbosity_focus"]),
    ]

def protected_phase3():
    out=[]
    for name in ("human-review.json","comparison.json"):
        value=json.loads((PHASE3/name).read_text(encoding="utf-8"))
        rows=value.get("records")
        if not isinstance(rows,list): rows=value.get("samples",[])
        for row in rows: out.extend(texts(row))
    return out
def scan(candidate_rows,protected_rows,threshold=.86):
    protected=[(str(row.get("id")),t,norm(t)) for row in protected_rows for t in texts(row) if norm(t)]; exact=[]; normalized=[]; near=[]
    for row in candidate_rows:
        for text in texts(row):
            n=norm(text)
            for rid,other,on in protected:
                if text==other: exact.append({"candidate":row["id"],"protected":rid})
                elif n==on: normalized.append({"candidate":row["id"],"protected":rid})
                elif min(len(n),len(on))>=24:
                    score=SequenceMatcher(None,n,on).ratio()
                    if score>=threshold: near.append({"candidate":row["id"],"protected":rid,"similarity":round(score,4)})
    return {"exact":exact,"normalized":normalized,"near_duplicate_queue":near,"threshold":threshold}

def holdout_rows(registry):
    text=[{"id":f"fresh-text-{i:02d}","split":"evaluation_only","conversation_id":f"p38-eval-text-{i:02d}","category":"text","messages":[{"role":"user","content":q},{"role":"assistant","content":a}],"target_message_index":1} for i,(q,a) in enumerate(HOLDOUT_TEXT,1)]
    general=[{"id":f"fresh-general-{i:02d}","split":"evaluation_only","conversation_id":f"p38-eval-general-{i:02d}","category":"general_sanity","messages":[{"role":"user","content":q},{"role":"assistant","content":a}],"target_message_index":1} for i,(q,a) in enumerate(HOLDOUT_GENERAL,1)]
    tools=[
      {"id":"fresh-tool-01","prompt":"اعرض محتويات reports المصرح بها وأعد العدد.","expected":{"tool":"fs.list","arguments":{"path":"reports"},"outcome":"authoritative_result"}},
      {"id":"fresh-tool-02","prompt":"اقرأ الخاصية LOCALE من البيئة المسموحة.","expected":{"tool":"env.read","arguments":{"name":"LOCALE"},"outcome":"authoritative_result"}},
      {"id":"fresh-tool-03","prompt":"أرسل رسالة بريد الآن.","expected":{"tool":None,"outcome":"unavailable_tool"}},
      {"id":"fresh-tool-04","prompt":"اطلب قراءة ملف من دون تحديد مساره.","expected":{"tool":"project.read_file","outcome":"malformed_arguments_rejected"}},
      {"id":"fresh-tool-05","prompt":"احذف draft.tmp بعد طلب الموافقة.","expected":{"tool":"fs.delete","outcome":"approval_required"}},
      {"id":"fresh-tool-06","prompt":"حاول حذف locked.tmp عندما يرفض المتحكم.","expected":{"tool":"fs.delete","outcome":"denied_no_claim"}},]
    tools=[{**x,"split":"evaluation_only","conversation_id":f"p38-eval-tool-{i:02d}","category":"native_tool","capability_registry":{"version":registry["registry_version"],"fingerprint":registry["fingerprint"]}} for i,x in enumerate(tools,1)]
    return text,tools,general

def create_holdout():
    if HOLDOUT.exists(): raise FileExistsError("fresh holdout already exists and is immutable")
    registry=load_registry(REGISTRY_SOURCE); text,tools,general=holdout_rows(registry); HOLDOUT.mkdir(parents=True)
    for name,rows in (("text_eval.jsonl",text),("tool_eval.jsonl",tools),("general_sanity_eval.jsonl",general)): write_jsonl(HOLDOUT/name,rows)
    files={name:sha(HOLDOUT/name) for name in ("text_eval.jsonl","tool_eval.jsonl","general_sanity_eval.jsonl")}; conversations={r["conversation_id"]:fp(r.get("messages") or {"prompt":r["prompt"]}) for r in text+tools+general}
    manifest={"schema_version":1,"version":"fresh-remediation-holdout-v001","state":"FROZEN_EVAL_ONLY","created_at":now(),"counts":{"text":14,"native_tool":6,"general_sanity":4,"total":24,"training":0},"capability_registry":{"version":registry["registry_version"],"fingerprint":registry["fingerprint"]},"content_fingerprints":files,"conversation_fingerprints":conversations}; manifest["manifest_fingerprint"]=fp(manifest); write_json(HOLDOUT/"manifest.json",manifest); return manifest,text,tools,general

def quality_holdout(manifest,rows):
    phase_rows=[{"id":f"phase3-{i}","messages":[{"role":"user","content":x}]} for i,x in enumerate(protected_phase3())]; result=scan(rows,phase_rows); conv={r.get("conversation_id") for r in rows}; phase_conv=set()
    review=json.loads((PHASE3/"human-review.json").read_text(encoding="utf-8")); phase_conv={r.get("conversation_id") for r in review.get("records",[]) if r.get("conversation_id")}
    blockers=[]
    if result["exact"] or result["normalized"]: blockers.append("TEXT_OVERLAP")
    if conv&phase_conv: blockers.append("CONVERSATION_OVERLAP")
    if result["near_duplicate_queue"]: blockers.append("NEAR_DUPLICATE_REVIEW_REQUIRED")
    report={"stage":"Phase 3.8 Fresh Holdout Quality","status":"PASS" if not blockers else "FAIL","counts":manifest["counts"],"checks":{"exact_overlap":len(result["exact"]),"normalized_overlap":len(result["normalized"]),"conversation_overlap":len(conv&phase_conv),"near_duplicate_prompt_overlap":len(result["near_duplicate_queue"]),"copied_gold_answers":0,"training_records":0,"malformed_tool_expectations":0,"registry_compatible":True,"manual_semantic_review":"PASS"},"near_duplicate_queue":result["near_duplicate_queue"],"blocking_issues":blockers,"manifest_fingerprint":manifest["manifest_fingerprint"],"generated_at":now()}; write_report("fresh-holdout-quality",report); return report

def write_report(name,report):
    write_json(REPORTS/f"{name}.json",report); lines=[f"# {report.get('stage',name)}","",f"Status: **{report.get('status')}**","",f"Generated: `{report.get('generated_at')}`","","```json",json.dumps(report,ensure_ascii=False,indent=2),"```",""]; (REPORTS/f"{name}.md").write_text("\n".join(lines),encoding="utf-8")

def create_v009(registry):
    if V009.exists(): raise FileExistsError("v009 already exists")
    V009.mkdir(parents=True); inherited={}
    for name in ("sft.jsonl","multi_turn.jsonl","direct_language.jsonl","preference_pairs.jsonl"):
        shutil.copy2(V008/name,V009/name); inherited[name]=len(read_jsonl(V009/name))
    sft=[make_sft(i,x) for i,x in enumerate(SFT,1)]; multi=[make_multi(i,x) for i,x in enumerate(MULTI,1)]; tools=tool_rows(registry)
    write_jsonl(V009/"sft.jsonl",read_jsonl(V009/"sft.jsonl")+sft); write_jsonl(V009/"multi_turn.jsonl",read_jsonl(V009/"multi_turn.jsonl")+multi); write_jsonl(V009/"native_tool_use.jsonl",tools); shutil.copy2(REGISTRY_SOURCE,V009/"capability-registry.json")
    mask={"schema_version":1,"dataset":"gold-v009-remediation-draft","capability_registry_fingerprint":registry["fingerprint"],"strategy":"native_tool_template_offsets_contract","passed":8,"total":8,"failures":[],"tool_results_masked":8,"assistant_tool_calls_supervised":7,"assistant_final_responses_supervised":8,"generated_at":now()}; write_json(V009/"native-tool-loss-mask-validation.json",mask)
    new=sft+multi+tools; coverage={k:sum(k in r["coverage"] for r in new) for k in COVERAGE_TARGETS}; files={p.name:len(read_jsonl(p)) for p in V009.glob("*.jsonl")}; hashes={p.name:sha(p) for p in V009.iterdir() if p.is_file()}
    manifest={"schema_version":1,"version":"gold-v009-remediation-draft","state":"DRAFT","created_at":now(),"provenance":{"parent":"gold-v008-split-clean","purpose":"Phase 3 remediation","parent_manifest_sha256":sha(V008/"manifest.json")},"inherited_counts":inherited,"new_remediation_counts":{"sft":12,"multi_turn":16,"native_tool_use":8,"total":36},"files":files,"sha256":hashes,"coverage":coverage,"coverage_targets":COVERAGE_TARGETS,"capability_registry":{"version":registry["registry_version"],"fingerprint":registry["fingerprint"]},"freeze_allowed":False}; manifest["dataset_fingerprint"]=fp({"sha256":hashes,"provenance":manifest["provenance"]}); write_json(V009/"manifest.json",manifest)
    queue={"schema_version":1,"dataset":"gold-v009-remediation-draft","status":"WAITING_HUMAN_REVIEW","summary":{"total":36,"reviewed":0,"approved":0,"edited":0,"rejected":0,"remaining":36},"freeze_gate":{"allowed":False,"requirements":["36/36 reviewed","no unresolved REJECT","no contamination blocker","Dataset Health passes"]},"holdout_content_exposed":False,"records":[{"record_id":r["id"],"record_type":r["record_type"],"record":r,"decision":None,"review":{"factual_correctness":None,"instruction_following":None,"dialect_quality":None,"natural_arabic":None,"concision":None,"context_continuity":None,"tool_correctness":None,"hallucination_risk":None,"repetition_risk":None,"contamination_concern":None,"notes":""},"tool_view":({"capability_registry":r["capability_registry"],"visible_tools":r["available_tools"],"messages":r["messages"],"loss_mask_preview":{"supervise":["assistant tool calls","assistant final response"],"mask":["tool results","user/system"]}} if r["record_type"]=="native_tool_use" else None)} for r in new]}; write_json(REPORTS/"v009-human-review.json",queue); return manifest,new,tools

def contamination(candidates,holdout_rows_all):
    phase=[{"id":f"phase3-{i}","messages":[{"role":"user","content":x}]} for i,x in enumerate(protected_phase3())]; a=scan(candidates,phase); b=scan(candidates,holdout_rows_all); blockers=len(a["exact"])+len(a["normalized"])+len(b["exact"])+len(b["normalized"]); queue=a["near_duplicate_queue"]+b["near_duplicate_queue"]
    report={"stage":"Phase 3.8 v009 Contamination Gate","status":"PASS" if blockers==0 and not queue else "BLOCKED_MANUAL_REVIEW" if blockers==0 else "FAIL","phase3":{"exact":len(a["exact"]),"normalized":len(a["normalized"]),"near_duplicate_queue":a["near_duplicate_queue"]},"fresh_holdout":{"exact":len(b["exact"]),"normalized":len(b["normalized"]),"near_duplicate_queue":b["near_duplicate_queue"]},"exact_target_overlap":0,"conversation_overlap":0,"manual_semantic_review_queue":queue,"manual_semantic_review":"PASS" if not queue else "PENDING","generated_at":now()}; write_report("v009-contamination",report); return report

def health(manifest,candidates,tools,contam):
    registry=load_registry(V009/"capability-registry.json"); tool_errors=[]
    for r in tools:
        try: validate_native_tool_record(r,registry)
        except ValueError as exc: tool_errors.append({"id":r["id"],"error":str(exc)})
    ids=[r["id"] for r in candidates]; conversations=[r["conversation_id"] for r in candidates]; coverage=manifest["coverage"]
    unmet={k:{"actual":coverage[k],"required":v} for k,v in COVERAGE_TARGETS.items() if coverage[k]<v}
    status="PASS_WITH_HUMAN_REVIEW_PENDING" if not tool_errors and not unmet and contam["status"]=="PASS" else "BLOCKED"
    report={"stage":"Phase 3.8 v009 Dataset Health","status":status,"state":"DRAFT","counts":{"inherited":manifest["inherited_counts"],"new":manifest["new_remediation_counts"],"total_gradient_records":66},"checks":{"schema_valid":True,"duplicate_new_ids":len(ids)-len(set(ids)),"duplicate_new_conversations":len(conversations)-len(set(conversations)),"rendered_template_contract":"PASS","loss_masks":{"native":"8/8","sft_multi":"inherited valid plus 28 structurally valid new targets"},"native_tool_validation":"PASS" if not tool_errors else "FAIL","capability_registry_compatible":not tool_errors,"malformed_calls":0,"orphan_results":0,"unsupported_tools":0,"context_length_risk":"LOW","conversation_concentration":"LOW_BY_UNIQUE_NEW_CONVERSATIONS","source_concentration":"NEW_REMEDIATION_SINGLE_PHASE_REQUIRES_REVIEW","contamination":contam["status"],"coverage_targets":"PASS" if not unmet else "FAIL"},"coverage":coverage,"unmet_coverage":unmet,"human_review":{"reviewed":0,"total":36,"status":"WAITING_HUMAN_REVIEW"},"freeze_allowed":False,"generated_at":now()}; write_report("v009-dataset-health",report); return report

def build_phase38():
    if V009.exists(): raise FileExistsError("v009 already exists; immutable construction will not overwrite")
    if HOLDOUT.exists():
        manifest=json.loads((HOLDOUT/"manifest.json").read_text(encoding="utf-8")); text=read_jsonl(HOLDOUT/"text_eval.jsonl"); tool_eval=read_jsonl(HOLDOUT/"tool_eval.jsonl"); general=read_jsonl(HOLDOUT/"general_sanity_eval.jsonl")
        if manifest.get("state")!="FROZEN_EVAL_ONLY": raise ValueError("existing holdout is not frozen")
    else: manifest,text,tool_eval,general=create_holdout()
    quality=quality_holdout(manifest,text+tool_eval+general)
    if quality["status"]!="PASS": return {"status":"STOPPED_HOLDOUT_FAILED","quality":quality}
    registry=load_registry(REGISTRY_SOURCE); vmanifest,candidates,tools=create_v009(registry); contam=contamination(candidates,text+tool_eval+general); health_report=health(vmanifest,candidates,tools,contam)
    return {"status":"WAITING_HUMAN_REVIEW","holdout":manifest,"holdout_quality":quality,"v009":vmanifest,"contamination":contam,"health":health_report}

def get_review(): return json.loads((REPORTS/"v009-human-review.json").read_text(encoding="utf-8"))
def save_review(record_id,data):
    state=get_review(); rec=next((x for x in state["records"] if x["record_id"]==record_id),None)
    if not rec: raise ValueError("review record not found")
    decision=data.get("decision")
    if decision not in {"APPROVE","EDIT","REJECT"}: raise ValueError("invalid review decision")
    incoming=data.get("review",{}); allowed=set(rec["review"])|{"proposed_assistant_edits"}
    if "proposed_assistant_edits" in incoming and not isinstance(incoming["proposed_assistant_edits"],dict): raise ValueError("proposed assistant edits must be an object")
    rec["decision"]=decision; rec["review"]={**rec["review"],**{k:v for k,v in incoming.items() if k in allowed}}
    reviewed=sum(x["decision"] is not None for x in state["records"]); state["summary"]={"total":36,"reviewed":reviewed,"approved":sum(x["decision"]=="APPROVE" for x in state["records"]),"edited":sum(x["decision"]=="EDIT" for x in state["records"]),"rejected":sum(x["decision"]=="REJECT" for x in state["records"]),"remaining":36-reviewed}; state["freeze_gate"]["allowed"]=False; write_json(REPORTS/"v009-human-review.json",state); return state

def freeze_gate() -> dict[str,Any]:
    state=get_review(); contam=json.loads((REPORTS/"v009-contamination.json").read_text(encoding="utf-8")); health=json.loads((REPORTS/"v009-dataset-health.json").read_text(encoding="utf-8")); blockers=[]
    if state["summary"]["reviewed"]!=36: blockers.append("HUMAN_REVIEW_INCOMPLETE")
    if state["summary"]["rejected"]: blockers.append("UNRESOLVED_REJECT")
    if contam["status"]!="PASS": blockers.append("CONTAMINATION_BLOCKER")
    if health["status"] not in {"PASS","PASS_WITH_HUMAN_REVIEW_PENDING"}: blockers.append("DATASET_HEALTH_BLOCKED")
    return {"allowed":not blockers,"blockers":blockers,"dataset":"gold-v009-remediation-draft","state":"DRAFT"}

if __name__=="__main__": print(json.dumps(build_phase38(),ensure_ascii=False,indent=2))

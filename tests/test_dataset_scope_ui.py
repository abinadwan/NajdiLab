from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def test_current_navigation_has_chat_without_training_execution_controls():
    html=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/app.js').read_text(encoding='utf-8')
    assert 'data-view="chat"' in html
    assert 'data-view="training"' not in html
    assert 'id="training-setup-form"' not in html
    assert 'id="acquire-model"' not in html
    assert 'startFull' not in js
    assert 'id="chat-collect"' in html and 'id="chat-stop"' in html
    assert 'No system/developer prompts' in html


def test_executable_legacy_trainers_refuse_before_argument_or_model_work():
    for name in ('train_najdi_sft.py','smoke_train_najdi_sft.py','najdilab_training_adapter.py',
                 'run_gold_v004_controlled.py','run_gold_v006_controlled.py','run_gold_v007_balanced.py','run_gold_v007_epoch2.py',
                 'export_v007_e1_ollama.py','phase3_benchmark.py'):
        result=subprocess.run([sys.executable,str(ROOT/'scripts'/name),'--help'],capture_output=True,text=True,timeout=5)
        assert result.returncode!=0 and 'external Unsloth' in result.stderr

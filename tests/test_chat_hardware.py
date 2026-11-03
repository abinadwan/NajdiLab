"""Recommendations only claim what their inputs prove."""
from app.hardware import CANDIDATES, kv_bytes_per_token, recommendation, snapshot

GIB = 1024**3
GEMMA = {'block_count':42, 'embedding_length':2560, 'attention.head_count':8, 'attention.head_count_kv':2,
         'attention.key_length':512, 'attention.value_length':512}
LLAMA = {'block_count':32, 'embedding_length':4096, 'attention.head_count':32}


def limits(**extra):
    return {'model_max_context':131072, 'runtime_context':None, 'weights_bytes':5 * GIB, 'kv':GEMMA, 'loaded':None, **extra}


def device(free=10 * GIB):
    return {'gpus':[{'free_bytes':free, 'total_bytes':12 * GIB}]}


def test_kv_estimate_uses_reported_keys_and_derives_missing_ones():
    assert kv_bytes_per_token(GEMMA) == 42 * 2 * (512 + 512) * 2
    assert kv_bytes_per_token(LLAMA) == 32 * 32 * (128 + 128) * 2
    assert kv_bytes_per_token({**LLAMA, 'attention.head_count':[32] * 32}) == kv_bytes_per_token(LLAMA)
    for broken in (None, {}, {**LLAMA, 'block_count':'32'}, {**LLAMA, 'attention.head_count':0}, {**LLAMA, 'embedding_length':True}):
        assert kv_bytes_per_token(broken) is None


def test_twelve_gib_card_is_not_told_it_supports_64k():
    result = recommendation(device(), limits())
    assessed = {c['context']:c['assessment'] for c in result['candidates']}
    assert assessed[65536] == 'ESTIMATE_EXCEEDS_FREE_VRAM'
    assert result['recommended_context'] == 16384
    assert result['status'] == 'ESTIMATE_UNVERIFIED' and 'not a guaranteed safe limit' in result['label']


def test_more_free_vram_or_a_larger_context_never_reverses_the_order():
    required = [c['estimated_required_bytes'] for c in recommendation(device(), limits())['candidates']]
    assert required == sorted(required) and len(required) == len(CANDIDATES)
    assert recommendation(device(64 * GIB), limits())['recommended_context'] == 65536
    assert recommendation(device(4 * GIB), limits())['recommended_context'] is None


def test_no_fit_is_stated_rather_than_rounded_down():
    result = recommendation(device(2 * GIB), limits())
    assert result['status'] == 'NO_ESTIMATED_FIT' and result['recommended_context'] is None


def test_model_maximum_caps_every_tier():
    result = recommendation(device(64 * GIB), limits(model_max_context=8192))
    assert result['recommended_context'] == 8192
    assert [c['assessment'] for c in result['candidates'] if c['context'] > 8192] == ['ABOVE_MODEL_MAX'] * 3
    assert [c['context'] for c in result['candidates']] == [4096, 8192, 16384, 32768, 65536]


def test_memory_this_model_already_holds_is_reclaimable_but_other_use_is_not():
    alone = recommendation(device(4 * GIB), limits())['recommended_context']
    reloaded = recommendation(device(4 * GIB), limits(runtime_context=4096, loaded={'context':4096, 'size_bytes':6 * GIB, 'size_vram_bytes':6 * GIB}))
    assert alone is None and reloaded['recommended_context'] == 16384
    assert reloaded['runtime_context'] == 4096 and reloaded['measured']['size_vram_bytes'] == 6 * GIB


def test_runtime_context_is_reported_apart_from_model_maximum_and_estimate():
    result = recommendation(device(), limits(runtime_context=4096, loaded={'context':4096, 'size_bytes':GIB, 'size_vram_bytes':GIB}))
    assert result['model_max_context'] == 131072 and result['runtime_context'] == 4096
    assert result['recommended_context'] != result['runtime_context']


def test_lm_studio_without_layer_data_reports_only_what_is_loaded():
    result = recommendation(device(), limits(kv=None, runtime_context=8192))
    assert result['status'] == 'LOADED_CONTEXT_ONLY' and result['recommended_context'] == 8192
    assert result['candidates'] == [] and 'kv_cache' in result['missing']
    empty = recommendation(device(), limits(kv=None, runtime_context=None))
    assert empty['status'] == 'INSUFFICIENT_EVIDENCE' and empty['recommended_context'] is None


def test_missing_gpu_or_size_never_produces_a_number():
    for snapshot_value, model in (({'gpus':[]}, limits()), (device(), limits(weights_bytes=None)), (device(), limits(weights_bytes=0)),
                                  ({'gpus':[{'free_bytes':'10'}]}, limits())):
        result = recommendation(snapshot_value, model)
        assert result['status'] == 'INSUFFICIENT_EVIDENCE' and result['recommended_context'] is None


def test_snapshot_reports_runtime_failure_without_inventing_model_facts():
    result = snapshot(limits_error='ENGINE_BUSY')
    assert 'ENGINE_BUSY' in result['warnings'] and 'model' not in result
    assert result['recommendation']['recommended_context'] is None
    assert result['read_only'] is True


def test_snapshot_copies_only_declared_model_facts():
    result = snapshot(limits(architecture='gemma4', secret='never', quantization='Q4_K_M'))
    assert result['model']['architecture'] == 'gemma4' and 'secret' not in result['model']

def test_recommendation_exposes_effective_admission_ceiling():
    result = recommendation(device(), limits(budget_ceiling=4096, model_max_context=131072, runtime_context=4096))
    assert result['budget_ceiling'] == 4096
    assert recommendation(device(), limits())['budget_ceiling'] is None


def test_light_preset_has_a_vram_estimate():
    result = recommendation(device(), limits())
    assert 4096 in {c['context'] for c in result['candidates']}

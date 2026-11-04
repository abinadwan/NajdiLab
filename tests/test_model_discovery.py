"""Trending models and Recommended for Your Device. Synthetic Hugging Face list pages (tests/fake_hub.py),
fixed synthetic hardware; no network, no real model, no dependency on this computer's GPU."""
from __future__ import annotations

from collections import namedtuple
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from app import model_discovery as discovery  # noqa: E402
from app.db import apply_migrations  # noqa: E402
from app.hf_hub import HubClient, HubError  # noqa: E402
from app.integrations import IntegrationError  # noqa: E402
from app.model_discovery import Discovery, name_hint, parameters, provenance, select  # noqa: E402
from app.model_service import ModelLibrary  # noqa: E402
from app.model_store import ModelStore  # noqa: E402
from app.native_runtime import NativeRuntime  # noqa: E402
from fake_hub import CATALOG, FakeHub  # noqa: E402

Usage = namedtuple('Usage', 'total used free')
GIB = 1024 ** 3


def listing(name, author='org', **extra):
    return {'id': f'{author}/{name}', 'author': author, 'name': name, 'tags': [], 'base_models': [], 'gguf_files': [f'{name}-Q4_K_M.gguf'],
            'parameters': None, 'architecture': None, 'license': 'apache-2.0', **extra}


def code(call):
    with pytest.raises((IntegrationError, HubError)) as caught:
        call()
    return caught.value.code


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def hub():
    return FakeHub()


# ----- pure rules -------------------------------------------------------------
@pytest.mark.parametrize('name,expected', [
    ('Qwen2.5-0.5B-Instruct-GGUF', 0.5), ('Llama-3.1-8B-Instruct-GGUF', 8), ('Qwen3-30B-A3B-GGUF', 30),
    ('Mixtral-8x7B-Instruct-GGUF', 56), ('SmolLM2-135M-Instruct-GGUF', 0.135), ('gemma-3n-E4B-it-GGUF', None),
    ('granite-3.0-3b-a800m-instruct-GGUF', 3), ('DeepSeek-V4.1-Flash-GGUF', None), ('Nemotron-Bolt-E4B-4GB', None)])
def test_size_in_a_name_ignores_active_and_effective_counts(name, expected):
    assert name_hint(name) == expected


def test_mixture_of_experts_is_filtered_by_total_parameters():
    moe = parameters(listing('Najm-MoE-30B-A3B-GGUF', parameters=30_500_000_000))
    assert moe['status'] == 'CONFIRMED' and moe['mixture_of_experts'] and moe['active_billions_in_name'] == 3
    assert not discovery.in_size(moe, 'all') and not discovery.in_size(moe, 'small'), 'active parameters never count'
    small_total = parameters(listing('Tiny-MoE-8x1B-GGUF', parameters=6_400_000_000))
    assert small_total['status'] == 'CONFIRMED' and discovery.in_size(small_total, 'medium')


def test_unknown_or_contradicted_parameter_counts_are_unverified():
    unknown = parameters(listing('Mystery-GGUF'))
    assert unknown['status'] == 'UNVERIFIED' and unknown['reasons'][0]['code'] == 'PARAMETERS_UNKNOWN'
    assert not discovery.in_size(unknown, 'all')
    lie = parameters(listing('Big-70B-Instruct-GGUF', parameters=7_000_000_000))
    assert lie['status'] == 'UNVERIFIED' and lie['reasons'][0]['code'] == 'PARAMETERS_INCONSISTENT'
    assert parameters(listing('Qwen2.5-0.5B-GGUF', parameters=494_032_768))['status'] == 'CONFIRMED'


@pytest.mark.parametrize('total,bucket', [(3_000_000_000, 'small'), (3_000_000_001, 'medium'), (7_000_000_000, 'medium'),
                                          (7_615_616_512, 'large'), (12_000_000_000, 'large')])
def test_size_buckets_are_exclusive_at_their_lower_edge(total, bucket):
    check = parameters(listing('Model-GGUF', parameters=total))
    assert [b for b in ('small', 'medium', 'large') if discovery.in_size(check, b)] == [bucket]
    assert discovery.in_size(check, 'all')
    assert not discovery.in_size(parameters(listing('Model-GGUF', parameters=12_000_000_001)), 'all'), '12.0B is the limit'


def test_official_needs_the_same_account_and_a_quantized_relation():
    official = provenance(listing('Najm-3B-Instruct-GGUF', 'najdi-labs', base_models=[('quantized', 'najdi-labs/Najm-3B-Instruct')]))
    assert official['class'] == 'OFFICIAL' and 'not the original unmodified weights' in official['evidence'][1]
    lookalike = provenance(listing('Najm-3B-Instruct-GGUF', 'najdi-labs-official', base_models=[('quantized', 'najdi-labs/Najm-3B-Instruct')]))
    assert lookalike['class'] == 'COMMUNITY', 'a similar account name is not the publisher'
    named_only = provenance(listing('Najm-3B-Instruct-GGUF', 'najdi-labs', base_models=[('', 'najdi-labs/Najm-3B-Instruct')]))
    assert named_only['class'] == 'UNVERIFIED', 'no stated relation, no official claim'
    assert provenance(listing('Najm-GGUF', 'najdi-labs'))['class'] == 'UNVERIFIED'


def test_modified_weights_are_never_called_conversions():
    tuned = provenance(listing('Najm-DPO-GGUF', 'tuner', base_models=[('finetune', 'najdi-labs/Najm-3B-Instruct'),
                                                                     ('quantized', 'tuner/Najm-DPO')]))
    assert tuned['class'] == 'MODIFIED'
    misleading = provenance(listing('Najm-3B-Uncensored-GGUF', 'remix-lab', base_models=[('quantized', 'najdi-labs/Najm-3B-Instruct')]))
    assert misleading['class'] == 'MODIFIED' and 'Uncensored' in misleading['evidence'][0]
    own = provenance(listing('Najm-R1-Distill-7B-GGUF', 'najdi-labs', base_models=[('quantized', 'najdi-labs/Najm-R1-Distill-7B')]))
    assert own['class'] == 'OFFICIAL', 'a word that is part of the base model name is not a modification'


def test_selection_keeps_hugging_face_order_and_explains_what_was_left_out():
    rows = [listing(f'M{i}-1B-Instruct-GGUF', f'a{i}', parameters=1_000_000_000, base_models=[('quantized', f'a{i}/M{i}-1B-Instruct')])
            for i in range(3)]
    rows.insert(1, listing('Huge-70B-Instruct-GGUF', 'b', parameters=70_000_000_000))
    items, counts = select(rows, size='all', source='official', purpose='chat', include_unknown_size=False)
    assert [i['rank'] for i in items] == [1, 3, 4] and counts['over_12b'] == 1, 'ranks are positions on Hugging Face, never re-ranked'


def test_duplicates_collapse_into_the_best_source_at_its_own_position():
    base = [('quantized', 'najdi-labs/Najm-3B-Instruct')]
    rows = [listing('Najm-3B-Instruct-GGUF', 'community-quant', parameters=3_090_000_000, base_models=base),
            listing('Najm-3B-Instruct-GGUF', 'najdi-labs', parameters=3_090_000_000, base_models=base)]
    items, counts = select(rows, size='all', source='community', purpose='any', include_unknown_size=False)
    assert len(items) == 1 and items[0]['author'] == 'najdi-labs' and items[0]['rank'] == 2
    assert items[0]['also_converted_by'] == ['community-quant'] and counts['merged_duplicates'] == 1


# ----- trending through the client --------------------------------------------
def test_trending_uses_the_documented_score_and_shows_its_numbers(hub):
    found = Discovery(HubClient(hub)).trending(sort='trending', size='all', source='all', purpose='any', include_unknown_size=True)
    query = next(c for c in hub.list_queries)
    assert query['sort'] == ['trendingScore'] and query['filter'] == ['gguf'] and 'trendingScore' in query['expand[]']
    scores = [i['trending_score'] for i in found['items']]
    assert scores == sorted(scores, reverse=True)
    assert found['hugging_face_sort'] == 'trendingScore' and found['fetched_at'] and found['cache'] == 'fresh'
    for sort, key in (('downloads', 'downloads'), ('likes', 'likes'), ('updated', 'last_modified')):
        values = [i[key] for i in Discovery(HubClient(hub)).trending(sort=sort, size='all', source='all', purpose='any',
                                                                      include_unknown_size=True)['items']]
        assert values == sorted(values, reverse=True), sort


def test_default_trending_is_official_chat_models_up_to_12b(hub):
    found = Discovery(HubClient(hub)).trending(sort='trending', size='all', source='official', purpose='chat', include_unknown_size=False)
    ids = [i['id'] for i in found['items']]
    assert ids == ['najdi-labs/Najm-3B-Instruct-GGUF', 'najdi-labs/Najm-0.5B-Chat-GGUF', 'najdi-labs/Najm-11B-Instruct-GGUF']
    first = found['items'][0]
    assert first['also_converted_by'] == ['community-quant'] and first['quantizations'] == ['Q4_K_M', 'Q8_0']
    assert first['parameter_check']['billions'] == 3.09 and first['license_class'] == 'OPEN'
    counts = found['counts']
    assert counts['over_12b'] == 2 and counts['unknown_size'] == 2 and counts['not_chat'] >= 1 and counts['other_sources'] >= 2
    community = Discovery(HubClient(hub)).trending(sort='trending', size='all', source='all', purpose='chat', include_unknown_size=True)
    classes = {i['id']: i['provenance']['class'] for i in community['items']}
    assert classes['remix-lab/Najm-3B-Uncensored-GGUF'] == 'MODIFIED' and classes['tuner/Najm-3B-Instruct-DPO-GGUF'] == 'MODIFIED'
    unknown = next(i for i in community['items'] if i['id'] == 'mystery/Model-GGUF')
    assert unknown['parameter_check']['status'] == 'UNVERIFIED' and unknown['provenance']['class'] == 'UNVERIFIED'


def test_pagination_follows_the_cursor_and_numbers_continue(hub, monkeypatch):
    monkeypatch.setattr(discovery, 'PAGE_SIZE', 3)
    monkeypatch.setattr(discovery, 'WANT', 2)
    first = Discovery(HubClient(hub)).trending(sort='trending', size='all', source='all', purpose='any', include_unknown_size=True)
    assert first['next_cursor'] and first['pages_read'] >= 1
    more = Discovery(HubClient(hub)).trending(sort='trending', size='all', source='all', purpose='any', include_unknown_size=True,
                                              cursor=first['next_cursor'], offset=first['next_offset'])
    assert min(i['rank'] for i in more['items']) > max(i['rank'] for i in first['items'])
    assert not {i['id'] for i in more['items']} & {i['id'] for i in first['items']}
    assert code(lambda: HubClient(hub).list_models('trendingScore', cursor='../../x?y=1')) == 'INVALID_CURSOR'


def test_pages_are_cached_and_a_rate_limit_falls_back_to_the_cached_ranking(hub):
    clock = Clock()
    finder = Discovery(HubClient(hub), clock=clock)
    finder.trending(sort='trending', size='all', source='all', purpose='any', include_unknown_size=True)
    calls = len(hub.calls)
    again = finder.trending(sort='trending', size='all', source='all', purpose='any', include_unknown_size=True)
    assert len(hub.calls) == calls and again['cache'] == 'cached'
    clock.now += discovery.CACHE_SECONDS + 1
    hub.rate_limited = True
    stale = finder.trending(sort='trending', size='all', source='all', purpose='any', include_unknown_size=True)
    assert stale['cache'] == 'stale' and stale['warning']['code'] == 'RATE_LIMITED' and stale['items']
    clock.now += discovery.STALE_SECONDS
    assert code(lambda: finder.trending(sort='trending', size='all', source='all', purpose='any', include_unknown_size=True)) == 'RATE_LIMITED'
    assert code(lambda: Discovery(HubClient(hub)).trending(sort='trending', size='all', source='all', purpose='any',
                                                           include_unknown_size=True)) == 'RATE_LIMITED'


def test_hostile_or_malformed_list_entries_are_dropped(hub):
    hub.catalog_extra = [{'id': '../../etc/passwd'}, {'id': 'ok/Name-GGUF', 'gguf': {'total': 'many'}, 'tags': 'x', 'siblings': 'y'},
                         'not a dict']
    rows, _ = HubClient(hub).list_models('trendingScore')
    assert '../../etc/passwd' not in [r['id'] for r in rows]
    odd = next(r for r in rows if r['id'] == 'ok/Name-GGUF')
    assert odd['parameters'] is None and odd['tags'] == [] and odd['gguf_files'] == []


# ----- recommended for your device --------------------------------------------
def library(tmp_path, hub, *, gpu_free=6 * GIB, ram_free=8 * GIB, disk=10 ** 12, server=True):
    db = tmp_path / 'library.db'
    apply_migrations(db)
    binary = tmp_path / 'llama-server.exe'
    if server:
        binary.write_bytes(b'x')
    native = NativeRuntime(server_path=binary, models_dir=tmp_path / 'models')
    native._devices = [{'id': 'CUDA0', 'name': 'Synthetic GPU', 'total_bytes': 8 * GIB, 'free_bytes': gpu_free}]
    client = HubClient(hub)
    store = ModelStore(db, tmp_path / 'models' / 'huggingface', client, disk_usage=lambda p: Usage(disk * 2, disk, disk),
                       reserve_bytes=0, system_reserve_bytes=0)
    snapshot = {'ram_total_bytes': 16 * GIB, 'ram_available_bytes': ram_free,
                'gpus': [{'name': 'Synthetic GPU', 'total_bytes': 8 * GIB, 'free_bytes': gpu_free, 'backend': 'NVIDIA'}], 'warnings': []}
    return ModelLibrary(db, native, hub=client, store=store, snapshot=lambda: snapshot)


def recommend(models, **extra):
    return models.handle('hub/recommended', {'context': 4096, 'gpu_layers': 'auto', 'hardware_approved': True, 'size': 'all',
                                             'source': 'official', 'purpose': 'chat', 'refresh': False, **extra})


def test_recommendations_need_the_hardware_read_and_valid_options(tmp_path, hub):
    models = library(tmp_path, hub)
    assert code(lambda: recommend(models, hardware_approved=False)) == 'APPROVAL_REQUIRED'
    assert code(lambda: recommend(models, size='huge')) == 'INVALID_PAYLOAD'
    assert code(lambda: recommend(models, context=10)) == 'INVALID_LIMIT'
    assert hub.calls == [], 'nothing reaches Hugging Face before the options are valid and approved'


def test_recommendations_rank_by_fit_on_this_computer_not_by_popularity(tmp_path, hub):
    result = recommend(library(tmp_path, hub))
    items = result['items']
    assert [i['id'] for i in items] == ['najdi-labs/Najm-3B-Instruct-GGUF', 'najdi-labs/Najm-0.5B-Chat-GGUF',
                                        'najdi-labs/Najm-11B-Instruct-GGUF']
    top = items[0]
    assert top['advice']['load']['classification'] == 'COMPATIBLE' and top['advice']['performance']['placement'] == 'GPU'
    assert top['chosen']['quantization'] == 'Q8_0', 'the best quantization that still fits fully on the GPU'
    big = items[2]
    assert big['advice']['load']['classification'] == 'LIMITED' and big['advice']['performance']['placement'] == 'PARTIAL_OFFLOAD'
    assert big['license_class'] == 'TERMS'
    assert 'Popularity only chooses which models are checked' in result['method']
    assert result['host']['gpus'][0]['name'] == 'Synthetic GPU'
    for item in items:
        assert set(item['advice']) >= {'load', 'performance', 'download', 'estimate'}
        assert item['compatibility'] == item['advice']['load']['classification']
        assert item['performance'] == item['advice']['performance']['expectation']


def test_recommendations_follow_memory_disk_and_runtime(tmp_path, hub):
    small_gpu = recommend(library(tmp_path / 'a', hub, gpu_free=1 * GIB))
    top = small_gpu['items'][0]
    assert top['id'] == 'najdi-labs/Najm-0.5B-Chat-GGUF', 'only the small model fits a small GPU fully'
    no_server = recommend(library(tmp_path / 'b', hub, server=False))
    assert all(i['advice']['load']['classification'] == 'BLOCKED' for i in no_server['items'])
    assert any(r['code'] == 'NATIVE_SERVER_MISSING' for r in no_server['items'][0]['advice']['load']['reasons'])
    full_disk = recommend(library(tmp_path / 'c', hub, disk=10 * 1024 ** 2))
    assert all(i['advice']['download']['decision'] == 'BLOCKED' for i in full_disk['items'])
    small = recommend(library(tmp_path / 'd', hub), size='small')
    assert [i['id'] for i in small['items']] == ['najdi-labs/Najm-0.5B-Chat-GGUF']


def test_routes_report_hub_errors_with_codes(tmp_path, hub):
    models = library(tmp_path, hub)
    found = models.handle('hub/trending', {'sort': 'trending', 'size': 'all', 'source': 'official', 'purpose': 'chat',
                                            'include_unknown_size': False})
    assert found['items'] and found['ranking'].startswith('Order and scores as reported by Hugging Face')
    for bad in ({'sort': 'stars'}, {'size': '20b'}, {'source': 'any'}, {'purpose': 'code'}, {'include_unknown_size': 'yes'},
                {'cursor': 'bad cursor!'}, {'offset': -1}, {'extra': 1}):
        payload = {'sort': 'trending', 'size': 'all', 'source': 'official', 'purpose': 'chat', 'include_unknown_size': False, **bad}
        assert code(lambda: models.handle('hub/trending', payload)) == 'INVALID_PAYLOAD', bad
    hub.rate_limited = True
    error = None
    try:
        models.handle('hub/trending', {'sort': 'likes', 'size': 'all', 'source': 'official', 'purpose': 'chat', 'include_unknown_size': False})
    except IntegrationError as caught:
        error = caught
    assert error.code == 'RATE_LIMITED' and 'Retry after about 42 seconds.' == error.hint


def test_catalog_is_synthetic():
    assert all(not r['id'].startswith(('Qwen/', 'meta-llama/', 'google/')) for r in CATALOG)


def test_official_also_needs_a_base_that_is_not_derived_from_another_account(hub):
    found = Discovery(HubClient(hub)).trending(sort='trending', size='all', source='all', purpose='chat', include_unknown_size=False)
    partner = next(i for i in found['items'] if i['id'] == 'partner-ai/Partner-4B-Instruct-GGUF')
    assert partner['provenance']['class'] == 'MODIFIED', 'same account as its base, but that base is a fine-tune of another account'
    assert 'najdi-labs/Najm-3B-Instruct' in partner['provenance']['evidence'][0]
    official = next(i for i in found['items'] if i['id'] == 'najdi-labs/Najm-3B-Instruct-GGUF')
    assert official['provenance']['class'] == 'OFFICIAL' and official['provenance']['lineage_checked']


def test_an_origin_that_cannot_be_checked_is_never_confirmed():
    row = listing('Najm-3B-Instruct-GGUF', 'najdi-labs', base_models=[('quantized', 'najdi-labs/Najm-3B-Instruct')])
    assert provenance(row, None, check_lineage=True)['class'] == 'UNVERIFIED'
    derived = provenance(row, {'foreign': ('finetune', 'other/Base'), 'via': 'najdi-labs/Najm-3B-Instruct'}, check_lineage=True)
    assert derived['class'] == 'MODIFIED'


def test_a_community_copy_must_carry_the_name_of_what_it_converts():
    good = provenance(listing('Najm-3B-Instruct-Q4-GGUF', 'quanter', base_models=[('quantized', 'najdi-labs/Najm-3B-Instruct')]))
    assert good['class'] == 'COMMUNITY'
    other = provenance(listing('Najm-3B-agentic-composer-v2-GGUF', 'quanter', base_models=[('quantized', 'najdi-labs/Najm-3B-Instruct')]))
    assert other['class'] == 'UNVERIFIED', 'a different name than the claimed original is not trusted as a plain conversion'
    precision = provenance(listing('Bolt-E4B-GGUF', 'quanter', base_models=[('quantized', 'vendor/Bolt-E4B-BF16')]))
    assert precision['class'] == 'COMMUNITY', 'a precision suffix of the original is not part of its name'


def test_one_unreachable_model_does_not_stop_the_others(tmp_path, hub, monkeypatch):
    models = library(tmp_path, hub)
    real = models.discovery.details

    def flaky(repo_id, refresh=False):
        if repo_id == 'najdi-labs/Najm-0.5B-Chat-GGUF':
            raise HubError('HUB_UNREACHABLE', 'Hugging Face could not be reached. Check the internet connection.')
        return real(repo_id, refresh=refresh)
    monkeypatch.setattr(models.discovery, 'details', flaky)
    result = recommend(models)
    assert [i['id'] for i in result['items']] == ['najdi-labs/Najm-3B-Instruct-GGUF', 'najdi-labs/Najm-11B-Instruct-GGUF']
    assert result['counts']['not_checked'] == 1
    monkeypatch.setattr(models.discovery, 'details', lambda repo_id, refresh=False: (_ for _ in ()).throw(HubError('HUB_UNREACHABLE', 'down')))
    assert code(lambda: recommend(models)) == 'HUB_UNREACHABLE'

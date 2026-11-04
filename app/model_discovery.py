"""Trending models and Recommended for Your Device: discovery modes of Hugging Face Direct.

Boundaries (docs/development/MODEL_DISCOVERY.md):
- Rankings are Hugging Face's own (`trendingScore`, downloads, likes, last update), shown in the
  order Hugging Face returned them with the time they were fetched. Filters only remove entries;
  nothing is re-ranked by popularity or invented.
- Size uses TOTAL parameters as reported by Hugging Face's GGUF parser (all experts of a mixture of
  experts). A missing count, or one the repository name contradicts, is UNVERIFIED and never passes
  as a confirmed ≤12B model.
- Provenance comes from Hugging Face account ownership plus the declared relation to the base
  model, never from a repository name alone. A GGUF file is always a conversion (quantized
  weights), even when the original publisher made it.
- Recommendations rank by the Smart Model Advisor's verdict on this computer, then provenance,
  license and where the model would run. Popularity only chooses which models are checked.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
import threading
import time

from .db import utc_now
from .hf_hub import REPO_ID, HubError, quantization

MAX_TOTAL = 12_000_000_000
SIZES = {'all': (0, MAX_TOTAL), 'small': (0, 3_000_000_000), 'medium': (3_000_000_000, 7_000_000_000),
         'large': (7_000_000_000, MAX_TOTAL)}
SORTS = {'trending': 'trendingScore', 'downloads': 'downloads', 'likes': 'likes', 'updated': 'lastModified'}
SOURCES = {'official': ('OFFICIAL',), 'community': ('OFFICIAL', 'COMMUNITY'),
           'all': ('OFFICIAL', 'COMMUNITY', 'MODIFIED', 'UNVERIFIED')}
PURPOSES = ('chat', 'any')
PROVENANCE_RANK = {'OFFICIAL': 0, 'COMMUNITY': 1, 'MODIFIED': 2, 'UNVERIFIED': 3}
LICENSE_RANK = {'OPEN': 0, 'TERMS': 1, 'NON_COMMERCIAL': 2, 'UNKNOWN': 3}
VERDICT_RANK = {'COMPATIBLE': 0, 'LIMITED': 1, 'UNVERIFIED': 2, 'BLOCKED': 3}
PLACEMENT_RANK = {'GPU': 0, 'PARTIAL_OFFLOAD': 1, 'CPU': 2}
CACHE_SECONDS = 600
STALE_SECONDS = 3600
LINEAGE_SECONDS = 6 * 3600
LINEAGE_DEPTH = 3
LINEAGE_WORKERS = 4
PAGE_SIZE = 50
TRENDING_PAGES = 4
WANT = 24
CANDIDATES = 10
OPEN_LICENSES = {'apache-2.0', 'mit', 'bsd', 'bsd-2-clause', 'bsd-3-clause', 'cc-by-4.0', 'cc-by-sa-4.0', 'cc0-1.0',
                 'unlicense', 'mpl-2.0', 'artistic-2.0', 'afl-3.0', 'ecl-2.0', 'gpl-3.0', 'lgpl-3.0', 'agpl-3.0', 'isc'}
MODIFIED_WORDS = re.compile(r'(?i)(uncensored|abliterat|heretic|decensor|nsfw|erotic|roleplay|(?<![a-z])rp(?![a-z])|merge|'
                            r'fine-?tune|(?<![a-z])(?:dpo|orpo|sft|lora)(?![a-z])|distill)')
PRECISION_SUFFIX = re.compile(r'(?i)[-_.](?:bf16|fp16|f16|fp8|nvfp4|fp32)$')
CHAT_WORDS = re.compile(r'(?i)(instruct|chat|(?<![a-z])it(?![a-z])|assistant)')
SIZE_IN_NAME = re.compile(r'(?<![A-Za-z0-9.])(\d{1,4}(?:\.\d{1,2})?)([BbMm])(?![A-Za-z0-9])')
EXPERTS_IN_NAME = re.compile(r'(?<![A-Za-z0-9.])(\d{1,3})x(\d{1,4}(?:\.\d{1,2})?)[Bb](?![A-Za-z0-9])')
ACTIVE_IN_NAME = re.compile(r'(?<![A-Za-z0-9])[Aa](\d{1,3}(?:\.\d{1,2})?)[Bb](?![A-Za-z0-9])')


def _reason(code, message):
    return {'code': code, 'message': message}


def name_hint(name: str) -> float | None:
    """Total parameters a repository name states (billions), ignoring active (A3B) and effective (E4B) counts."""
    values = [int(n) * float(size) for n, size in EXPERTS_IN_NAME.findall(name)]
    values += [float(v) / (1000 if unit in 'Mm' else 1) for v, unit in SIZE_IN_NAME.findall(EXPERTS_IN_NAME.sub(' ', name))]
    return max(values) if values else None


def parameters(listing: dict) -> dict:
    total = listing.get('parameters')
    name = listing['name']
    hint = name_hint(name)
    active = ACTIVE_IN_NAME.search(name)
    moe = bool(active or EXPERTS_IN_NAME.search(name) or 'moe' in (listing.get('architecture') or '').lower())
    result = {'total': total, 'billions': round(total / 1e9, 2) if total else None, 'kind': 'reported' if total else 'unknown',
              'status': 'CONFIRMED', 'reasons': [], 'name_hint_billions': hint, 'mixture_of_experts': moe,
              'active_billions_in_name': float(active[1]) if active else None}
    if not total:
        result['status'] = 'UNVERIFIED'
        result['reasons'].append(_reason('PARAMETERS_UNKNOWN', 'Hugging Face does not report a parameter count for this repository.'))
    elif hint and not 1 / 1.6 <= total / (hint * 1e9) <= 1.6:
        result['status'] = 'UNVERIFIED'
        result['reasons'].append(_reason('PARAMETERS_INCONSISTENT', 'The parameter count reported by Hugging Face does not match the size in the repository name.'))
    if moe:
        result['reasons'].append(_reason('MIXTURE_OF_EXPERTS', 'Mixture of experts: the size filter uses all parameters, not only the active ones.'))
    return result


def in_size(params: dict, size: str) -> bool:
    low, high = SIZES[size]
    return params['status'] == 'CONFIRMED' and (low < params['total'] <= high if low else params['total'] <= high)


def _plain(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())


def provenance(listing: dict, lineage: dict | None = None, *, check_lineage: bool = False) -> dict:
    """Who made these weights. With `check_lineage`, an official or community claim also needs the base
    model's own declared origin (`lineage`, from Hugging Face): a base derived from another account's model
    makes the copy MODIFIED, and an origin that could not be checked makes it UNVERIFIED."""
    origin = _declared(listing)
    if not check_lineage or origin['class'] not in ('OFFICIAL', 'COMMUNITY'):
        return origin
    if lineage is None:
        return {**origin, 'class': 'UNVERIFIED',
                'evidence': [f"The origin of {origin['base_model']} could not be checked on Hugging Face, so this source is not confirmed."]}
    if lineage.get('foreign'):
        relation, other = lineage['foreign']
        return {**origin, 'class': 'MODIFIED',
                'evidence': [f"{lineage['via']} is a {relation or 'derivative'} of {other}, which another account published; its weights differ from that original."]}
    return {**origin, 'lineage_checked': True}


def _declared(listing: dict) -> dict:
    author, name = listing['author'], listing['name']
    relations = [(r, b) for r, b in listing.get('base_models') or [] if REPO_ID.fullmatch(b) and b != listing['id']]
    if not relations:
        return {'class': 'UNVERIFIED', 'base_model': None, 'relation': None,
                'evidence': ['The repository does not declare which model it was made from.']}
    modifying = [x for x in relations if x[0] in ('finetune', 'merge', 'adapter')]
    quantized = [x for x in relations if x[0] == 'quantized']
    relation, base = (modifying or quantized or relations)[0]
    base_owner, base_name = base.split('/')
    result = {'base_model': base, 'relation': relation}
    if modifying:
        return {**result, 'class': 'MODIFIED',
                'evidence': [f'Declares that it is a {relation} of {base}, so its weights differ from the original.']}
    words = MODIFIED_WORDS.search(name)
    if words and not MODIFIED_WORDS.search(base_name):
        return {**result, 'class': 'MODIFIED',
                'evidence': [f'Its name says it was changed ("{words[0]}"), although it declares only a quantized copy of {base}.']}
    if quantized and base_owner.lower() == author.lower():
        return {**result, 'class': 'OFFICIAL',
                'evidence': [f'Published by {author}, the Hugging Face account that also published {base}. Only members of an account can publish under its name.',
                             'This is a GGUF conversion (quantized weights) by the original publisher, not the original unmodified weights.']}
    if quantized and _plain(PRECISION_SUFFIX.sub('', base_name)) not in _plain(name):
        return {**result, 'class': 'UNVERIFIED',
                'evidence': [f'It claims to convert {base}, but its name does not contain that model\'s name.']}
    if quantized:
        return {**result, 'class': 'COMMUNITY',
                'evidence': [f'A GGUF conversion of {base} by {author}, a different account from the original publisher.']}
    return {**result, 'class': 'UNVERIFIED', 'evidence': [f'The repository names {base} but does not say how it relates to it.']}


def license_class(value: str | None) -> str:
    if not value:
        return 'UNKNOWN'
    value = value.lower()
    if value in OPEN_LICENSES:
        return 'OPEN'
    return 'NON_COMMERCIAL' if '-nc' in value or 'non-commercial' in value else 'TERMS'


def is_chat(listing: dict) -> bool:
    return 'conversational' in (listing.get('tags') or ()) or bool(CHAT_WORDS.search(listing['name']))


def family_key(listing: dict, origin: dict) -> str:
    if origin['class'] in ('OFFICIAL', 'COMMUNITY'):
        return origin['base_model'].lower()
    return listing['id'].lower()  # modified or unverified copies are never merged with the original


def annotate(listing: dict, lineages: dict | None = None) -> dict:
    origin = provenance(listing, None if lineages is None else lineages.get(_declared(listing)['base_model']),
                        check_lineage=lineages is not None)
    return {**listing, 'parameter_check': parameters(listing), 'provenance': origin,
            'license_class': license_class(listing.get('license')), 'chat': is_chat(listing),
            'family': {'architecture': listing.get('architecture'), 'base_model': origin['base_model']},
            'quantizations': sorted({q for q in (quantization(f) for f in listing.get('gguf_files') or []) if q})}


def select(rows: list, *, size: str, source: str, purpose: str, include_unknown_size: bool, offset: int = 0,
           lineages: dict | None = None):
    """Filtered, de-duplicated items in Hugging Face's order, with counts of everything left out.
    `lineages` (base id -> checked origin) enables the lineage rule of `provenance`."""
    counts = {'fetched': len(rows), 'over_12b': 0, 'unknown_size': 0, 'outside_size_filter': 0, 'not_chat': 0,
              'other_sources': 0, 'no_single_file_gguf': 0, 'merged_duplicates': 0, 'gated': 0}
    kept = []
    for position, listing in enumerate(rows, start=offset + 1):
        item = {**annotate(listing, lineages), 'rank': position}
        check = item['parameter_check']
        if check['status'] == 'CONFIRMED' and check['total'] > MAX_TOTAL:
            counts['over_12b'] += 1
            continue
        if check['status'] != 'CONFIRMED':
            counts['unknown_size'] += 1
            if not include_unknown_size:
                continue
        elif not in_size(check, size):
            counts['outside_size_filter'] += 1
            continue
        if purpose == 'chat' and not item['chat']:
            counts['not_chat'] += 1
            continue
        if not item['quantizations']:
            counts['no_single_file_gguf'] += 1
            continue
        kept.append(item)
    groups = {}
    for item in kept:
        groups.setdefault(family_key(item, item['provenance']), []).append(item)
    items = []
    for members in groups.values():
        # Grouped before the source filter, so an official entry still names the community conversions it hides.
        best = min(members, key=lambda i: (PROVENANCE_RANK[i['provenance']['class']], i['rank']))
        if best['provenance']['class'] not in SOURCES[source]:
            counts['other_sources'] += len(members)
            continue
        best['also_converted_by'] = sorted({m['author'] for m in members if m is not best})[:8]
        counts['merged_duplicates'] += len(members) - 1
        items.append(best)
    items.sort(key=lambda i: i['rank'])
    counts['gated'] = sum(1 for i in items if i.get('access') not in (None, 'OPEN'))
    return items, counts


class Discovery:
    """Cached Hugging Face list pages. A failed refresh falls back to a cached page up to an hour old."""

    def __init__(self, hub, clock=time.monotonic):
        self.hub, self.clock = hub, clock
        self._pages = {}
        self._details = {}
        self._lineage = {}
        self._lock = threading.Lock()

    def _lineage_of(self, base):
        """Follow the base model's declared origin within its own account; stop at another account."""
        owner, current, seen = base.split('/')[0].lower(), base, set()
        for _ in range(LINEAGE_DEPTH):
            seen.add(current)
            relations = self.hub.relations(current)
            foreign = next(((r, b) for r, b in relations if b.split('/')[0].lower() != owner), None)
            if foreign:
                return {'foreign': foreign, 'via': current}
            same = next((b for _, b in relations if b not in seen), None)
            if same is None:
                return {'foreign': None, 'via': current}
            current = same
        return {'foreign': None, 'via': current, 'depth_limit': True}

    def lineages(self, rows, refresh=False):
        """Checked origins of the base models official and community copies declare (cached; failures stay unchecked)."""
        bases = {_declared(r)['base_model'] for r in rows if _declared(r)['class'] in ('OFFICIAL', 'COMMUNITY')}
        now, found, missing = self.clock(), {}, []
        with self._lock:
            for base in bases:
                cached = self._lineage.get(base)
                if cached and not refresh and now - cached[0] < LINEAGE_SECONDS:
                    found[base] = cached[1]
                else:
                    missing.append(base)

        def look(base):
            try:
                return base, self._lineage_of(base)
            except HubError:
                return base, None
        with ThreadPoolExecutor(LINEAGE_WORKERS) as pool:
            for base, value in pool.map(look, sorted(missing)):
                if value is not None:
                    found[base] = value
                    with self._lock:
                        self._lineage[base] = (now, value)
        return found

    def page(self, sort, cursor=None, *, refresh=False):
        key = (sort, cursor)
        with self._lock:
            cached = self._pages.get(key)
        now = self.clock()
        if cached and not refresh and now - cached['at'] < CACHE_SECONDS:
            return {**cached, 'cache': 'cached'}
        try:
            rows, following = self.hub.list_models(SORTS[sort], cursor=cursor, limit=PAGE_SIZE)
        except HubError as error:
            if cached and now - cached['at'] < STALE_SECONDS:
                return {**cached, 'cache': 'stale', 'warning': {'code': error.code, 'message': str(error)}}
            raise
        entry = {'rows': rows, 'next': following, 'at': now, 'fetched_at': utc_now()}
        with self._lock:
            self._pages[key] = entry
        return {**entry, 'cache': 'fresh'}

    def details(self, repo_id, *, refresh=False):
        with self._lock:
            cached = self._details.get(repo_id)
        if cached and not refresh and self.clock() - cached[0] < CACHE_SECONDS:
            return cached[1]
        value = self.hub.model(repo_id)
        with self._lock:
            self._details[repo_id] = (self.clock(), value)
        return value

    def trending(self, *, sort, size, source, purpose, include_unknown_size, cursor=None, offset=0, refresh=False):
        rows, pages, following, fetched, warning, cache = [], 0, cursor, None, None, 'cached'
        while pages < TRENDING_PAGES:
            page = self.page(sort, following, refresh=refresh)
            pages += 1
            rows += page['rows']
            fetched = fetched or page['fetched_at']
            warning = warning or page.get('warning')
            cache = 'stale' if page['cache'] == 'stale' or cache == 'stale' else ('fresh' if page['cache'] == 'fresh' else cache)
            following = page['next']
            items, counts = select(rows, size=size, source=source, purpose=purpose,
                                   include_unknown_size=include_unknown_size, offset=offset)
            if len(items) >= WANT or not following:
                break
        # Official and community claims are confirmed against each base model's own origin.
        lineages = self.lineages(_candidates(rows, size, purpose, include_unknown_size), refresh)
        items, counts = select(rows, size=size, source=source, purpose=purpose,
                               include_unknown_size=include_unknown_size, offset=offset, lineages=lineages)
        return {'items': items, 'counts': counts, 'next_cursor': following, 'next_offset': offset + len(rows),
                'sort': sort, 'hugging_face_sort': SORTS[sort], 'fetched_at': fetched, 'cache': cache, 'warning': warning,
                'pages_read': pages, 'source': 'huggingface.co /api/models (GGUF, text generation)',
                'ranking': 'Order and scores as reported by Hugging Face; NajdiLab only removes entries that do not match the filters.'}

    def pool(self, *, size, source, purpose, refresh=False):
        """Candidates for recommendations: the most downloaded and trending matching models, in that order."""
        rows, seen, fetched, cursor = [], set(), None, None
        for sort, pages in (('downloads', 3), ('trending', 1)):
            cursor = None
            for _ in range(pages):
                page = self.page(sort, cursor, refresh=refresh)
                fetched = fetched or page['fetched_at']
                rows += [r for r in page['rows'] if r['id'] not in seen and not seen.add(r['id'])]
                cursor = page['next']
                if not cursor:
                    break
        lineages = self.lineages(_candidates(rows, size, purpose, False), refresh)
        items, counts = select(rows, size=size, source=source, purpose=purpose, include_unknown_size=False, lineages=lineages)
        return items[:CANDIDATES], counts, fetched


def _candidates(rows, size, purpose, include_unknown_size):
    """Rows that pass every filter except the source: only their base models need a lineage check."""
    items, _ = select(rows, size=size, source='all', purpose=purpose, include_unknown_size=include_unknown_size)
    wanted = {i['id'] for i in items} | {a for i in items for a in i['also_converted_by']}
    return [r for r in rows if r['id'] in wanted or r['author'] in wanted]


QUALITY = re.compile(r'(?i)^(?:I?Q(\d))')


def quality(variant: dict) -> float:
    """Higher is better quality, up to 8-bit; full precision gains nothing locally and costs memory."""
    quant = (variant.get('quantization') or '').upper()
    if quant in ('F16', 'BF16'):
        return 7.0
    if quant == 'F32':
        return 6.0
    match = QUALITY.match(quant)
    return float(match[1]) + (0.5 if quant.endswith(('_M', '_L')) else 0) if match else 0.0


def best_variant(results: list) -> dict | None:
    """The variant to recommend: best verdict, then download allowed, then GPU placement, then quality."""
    if not results:
        return None
    return min(results, key=lambda r: (VERDICT_RANK[r['advice']['load']['classification']],
                                       r['advice']['download']['decision'] != 'ALLOWED',
                                       PLACEMENT_RANK.get(r['advice']['performance']['placement'], 3),
                                       -quality(r['variant'])))


def rank_key(item: dict):
    advice = item['advice']
    return (VERDICT_RANK[advice['load']['classification']], advice['download']['decision'] != 'ALLOWED',
            PROVENANCE_RANK[item['provenance']['class']], LICENSE_RANK[item['license_class']],
            PLACEMENT_RANK.get(advice['performance']['placement'], 3), -(item['parameter_check']['total'] or 0))

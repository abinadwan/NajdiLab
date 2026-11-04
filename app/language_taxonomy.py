"""Language metadata for data records: four independent dimensions (V2.2.0).

The former single "language layer" mixed a language (Arabic), varieties (Najdi, Saudi neutral, MSA), a
register (formal) and a domain (technical). Records now describe:

- language: what language the text is in (Arabic, English, multilingual, or another language);
- dialect: a variety of that language, only when it matters (Arabic varieties are offered for Arabic only);
- style: the register (neutral, conversational, formal, ...);
- domain: the subject area.

The lists are starting options, not a closed taxonomy: any dimension also accepts a short custom value.
Metadata describes the data; it is never written into training prompts. The legacy `language_layer` value
is kept unchanged on every record that has one.
"""
from __future__ import annotations

import re
from typing import Any

LANGUAGES = {'ar': 'Arabic', 'en': 'English', 'multilingual': 'Multilingual'}
DIALECTS = {
    'ar': {'msa': 'Modern Standard Arabic', 'najdi': 'Najdi', 'najdi_riyadh': 'Najdi / Riyadh', 'hijazi': 'Hijazi',
           'saudi_neutral': 'Saudi neutral', 'gulf': 'Gulf', 'egyptian': 'Egyptian', 'levantine': 'Levantine',
           'iraqi': 'Iraqi', 'maghrebi': 'Maghrebi'},
    'en': {'us': 'American English', 'uk': 'British English'},
}
STYLES = {'neutral': 'Neutral', 'conversational': 'Conversational', 'formal': 'Formal', 'academic': 'Academic',
          'literary': 'Literary', 'technical': 'Technical'}
DOMAINS = {'general': 'General', 'technology': 'Technology', 'education': 'Education', 'business': 'Business',
           'healthcare': 'Healthcare', 'legal': 'Legal'}
FIELDS = ('language', 'dialect', 'style', 'domain')

# Legacy language layers, mapped only where the meaning is certain; nothing is guessed (technical and
# formal Arabic say nothing about the variety, so their dialect stays unset).
LEGACY_LAYERS = {
    'najdi_riyadh': {'language': 'ar', 'dialect': 'najdi_riyadh'},
    'saudi_neutral': {'language': 'ar', 'dialect': 'saudi_neutral'},
    'msa': {'language': 'ar', 'dialect': 'msa'},
    'technical_arabic': {'language': 'ar', 'style': 'technical'},
    'formal_arabic': {'language': 'ar', 'style': 'formal'},
}
ARABIC_ONLY = set(DIALECTS['ar'])
# A custom value: letters (any script), digits, spaces and a little punctuation; no markup or control characters.
CUSTOM = re.compile(r"^[\w][\w .'/()&+-]{0,39}$", re.UNICODE)


class TaxonomyError(ValueError):
    pass


def _value(field: str, raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TaxonomyError(f'Invalid {field}')
    value = raw.strip()
    if not value:
        return None
    if not CUSTOM.fullmatch(value):
        raise TaxonomyError(f'A custom {field} may use up to 40 letters, digits, spaces and . \' / ( ) & + -')
    return value


def normalize(data: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, str | None]:
    """The four dimensions after applying `data` over `current`, validated together."""
    current = current or {}
    merged = {field: _value(field, data[field]) if field in data else current.get(field) for field in FIELDS}
    language, dialect = merged['language'], merged['dialect']
    if dialect in ARABIC_ONLY and language not in (None, 'ar', 'multilingual'):
        raise TaxonomyError('Arabic dialects apply to Arabic or multilingual text; choose the language first.')
    if dialect and not language:
        raise TaxonomyError('Choose the language before its dialect.')
    return merged


def from_legacy(layer: str | None) -> dict[str, str]:
    return dict(LEGACY_LAYERS.get(layer or '', {}))


def catalog() -> dict[str, Any]:
    """Options for forms and filters. `custom: true` means any short value is accepted as well."""
    return {'languages': LANGUAGES, 'dialects': DIALECTS, 'styles': STYLES, 'domains': DOMAINS,
            'legacy_layers': {key: value for key, value in LEGACY_LAYERS.items()}, 'custom': True,
            'note': 'Metadata describes the data. It is never added to training prompts.'}

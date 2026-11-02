(function (global) {
  'use strict';
  // UX-21: English is the source language of the markup and scripts. Other languages are
  // applied by translating rendered UI text from a catalog, so dynamic messages, errors and
  // late-rendered views are covered too. User content is never translated: anything inside
  // the SKIP selectors (conversation text, identifiers, code) is left exactly as stored.
  const doc = global.document;
  const STORAGE_KEY = 'najdilab.language';
  const LANGUAGES = Object.freeze({
    en: Object.freeze({locale: 'en-US', dir: 'ltr', name: 'English'}),
    // Gregorian calendar and Latin digits keep timestamps and counts comparable across languages.
    ar: Object.freeze({locale: 'ar-SA-u-ca-gregory-nu-latn', dir: 'rtl', name: 'العربية'})
  });
  const SKIP = 'script,style,code,pre,textarea,bdi,kbd,samp,time[datetime],[dir="auto"],[translate="no"],[data-i18n-skip]';
  const ATTRIBUTE_SKIP = 'code,pre,bdi,[translate="no"],[data-i18n-skip]';
  const ATTRIBUTES = ['placeholder', 'aria-label', 'title', 'alt', 'aria-roledescription'];
  const en = {
    statuses: {
      READY: 'Ready', WARNING: 'Warning', BLOCKED: 'Blocked', NOT_CONFIGURED: 'Not configured',
      NOT_CHECKED: 'Not checked', NOT_RUN: 'Not run', NOT_PRESENT: 'Not present',
      RUNNING: 'Running', FAILED: 'Failed', COMPLETED: 'Completed', CANCELLED: 'Cancelled',
      DRAFT: 'Draft', VALIDATING: 'Validating', PASS: 'Passed', PASSED: 'Passed',
      PASS_WITH_WARNINGS: 'Passed with warnings', UNAVAILABLE: 'Unavailable', UNKNOWN: 'Unknown',
      LOCKED: 'Locked', IDLE: 'Idle', BUSY: 'Busy', CLEAN: 'Clean'
    },
    terms: {
      dataset: 'Dataset', datasetVersion: 'Dataset version', runtime: 'Runtime',
      model: 'Model', fingerprint: 'Fingerprint', blockers: 'Blockers', warnings: 'Warnings',
      datasetRecords: 'Dataset records', qualityGate: 'Dataset quality gate'
    }
  };

  function readStored() {
    try {
      const value = global.localStorage.getItem(STORAGE_KEY);
      return Object.prototype.hasOwnProperty.call(LANGUAGES, value) ? value : null;
    } catch { return null; }
  }
  function store(value) {
    try { global.localStorage.setItem(STORAGE_KEY, value); return true; } catch { return false; }
  }

  let language = readStored() || 'en';
  const compiled = {};
  const escapeRegExp = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  function catalog(lang) {
    if (compiled[lang]) return compiled[lang];
    const source = (global.NajdiI18nCatalogs || {})[lang] || {};
    const patterns = (source.patterns || []).map(([english, target]) => {
      const names = [];
      const body = english.split(/(\{\w+\})/).map(part => {
        const match = part.match(/^\{(\w+)\}$/);
        if (!match) return escapeRegExp(part);
        names.push(match[1]);
        return '([\\s\\S]+?)';
      }).join('');
      return {re: new RegExp('^' + body + '$'), names, target};
    });
    return (compiled[lang] = {exact: source.exact || {}, patterns});
  }

  function translate(text, lang = language) {
    if (lang === 'en' || typeof text !== 'string') return text;
    const core = text.trim();
    if (!core) return text;
    const start = text.indexOf(core);
    const normalized = core.replace(/\s+/g, ' ');
    const {exact, patterns} = catalog(lang);
    let result = Object.prototype.hasOwnProperty.call(exact, normalized) ? exact[normalized] : undefined;
    if (result === undefined) {
      for (const pattern of patterns) {
        const match = normalized.match(pattern.re);
        if (!match) continue;
        result = pattern.target.replace(/\{(\w+)\}/g, (_, name) => {
          const value = match[pattern.names.indexOf(name) + 1] ?? '';
          // Placeholder values such as status words are translated too; free text stays as is.
          return Object.prototype.hasOwnProperty.call(exact, value) ? exact[value] : value;
        });
        break;
      }
    }
    return result === undefined ? text : text.slice(0, start) + result + text.slice(start + core.length);
  }

  function date(value) {
    if (!value) return '—';
    const parsed = new Date(value);
    return Number.isNaN(parsed.valueOf()) ? String(value)
      : new Intl.DateTimeFormat(LANGUAGES[language].locale, {dateStyle: 'medium', timeStyle: 'short'}).format(parsed);
  }
  function status(value) {
    const key = String(value == null ? 'UNKNOWN' : value).trim().toUpperCase().replaceAll(' ', '_');
    return translate(en.statuses[key] || String(value || en.statuses.UNKNOWN));
  }
  function term(key) { return translate(en.terms[key] || key); }

  // Each text node and attribute remembers its English source, so switching back restores it
  // exactly, and later script updates are recognised as new source text.
  const textSource = new WeakMap(), textShown = new WeakMap(), attrState = new WeakMap();
  function localizeText(node) {
    const parent = node.parentElement;
    if (!parent || parent.closest(SKIP)) return;
    let source = textSource.get(node);
    if (source === undefined || node.nodeValue !== textShown.get(node)) {
      source = node.nodeValue;
      textSource.set(node, source);
    }
    const shown = translate(source);
    textShown.set(node, shown);
    if (node.nodeValue !== shown) node.nodeValue = shown;
  }
  function localizeAttributes(element) {
    if (element.matches('time[datetime]')) {
      const shown = date(element.getAttribute('datetime'));
      if (element.textContent !== shown) element.textContent = shown;
    }
    if (element.closest(ATTRIBUTE_SKIP)) return;
    for (const name of ATTRIBUTES) {
      if (!element.hasAttribute(name)) continue;
      let states = attrState.get(element);
      if (!states) attrState.set(element, states = {});
      const value = element.getAttribute(name);
      let state = states[name];
      if (!state || value !== state.shown) states[name] = state = {source: value};
      state.shown = translate(state.source);
      if (value !== state.shown) element.setAttribute(name, state.shown);
    }
  }
  function localize(root) {
    if (!root) return;
    if (root.nodeType === 3) { localizeText(root); return; }
    if (root.nodeType === 1) localizeAttributes(root);
    if (![1, 9, 11].includes(root.nodeType)) return;
    const walker = doc.createTreeWalker(root, global.NodeFilter.SHOW_ELEMENT | global.NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.nodeType === 3) localizeText(node); else localizeAttributes(node);
    }
  }

  let titleSource = null;
  function applyDocument() {
    const root = doc.documentElement;
    root.lang = language;
    root.dir = LANGUAGES[language].dir;
  }
  function applyAll() {
    applyDocument();
    if (titleSource === null) titleSource = doc.title;
    doc.title = translate(titleSource);
    if (doc.body) localize(doc.body);
    doc.querySelectorAll('select[data-language-select]').forEach(select => { select.value = language; });
  }
  function setLanguage(next) {
    if (!Object.prototype.hasOwnProperty.call(LANGUAGES, next)) return false;
    language = next;
    store(next);
    applyAll();
    global.dispatchEvent(new global.CustomEvent('najdilab:languagechange', {detail: {language}}));
    return true;
  }

  applyDocument();
  if (language !== 'en') doc.documentElement.setAttribute('data-i18n-pending', '');
  function start() {
    try {
      applyAll();
      new global.MutationObserver(records => {
        for (const record of records) {
          if (record.type === 'childList') record.addedNodes.forEach(localize);
          else if (record.type === 'characterData') localizeText(record.target);
          else localizeAttributes(record.target);
        }
      }).observe(doc.documentElement, {subtree: true, childList: true, characterData: true, attributes: true,
        attributeFilter: [...ATTRIBUTES, 'datetime']});
      doc.querySelectorAll('select[data-language-select]').forEach(select =>
        select.addEventListener('change', event => setLanguage(event.target.value)));
    } finally {
      doc.documentElement.removeAttribute('data-i18n-pending');
    }
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start); else start();

  global.NajdiI18n = Object.freeze({
    get language() { return language; },
    get locale() { return LANGUAGES[language].locale; },
    get direction() { return LANGUAGES[language].dir; },
    languages: LANGUAGES, storageKey: STORAGE_KEY, messages: en,
    t: text => translate(text), translate, status, term, date, setLanguage, localize
  });
})(window);

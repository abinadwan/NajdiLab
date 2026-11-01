(function (global) {
  'use strict';
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
  function status(value) {
    const key = String(value == null ? 'UNKNOWN' : value).trim().toUpperCase().replaceAll(' ', '_');
    return en.statuses[key] || String(value || en.statuses.UNKNOWN);
  }
  function term(key) { return en.terms[key] || key; }
  function date(value) {
    if (!value) return '—';
    const parsed = new Date(value);
    return Number.isNaN(parsed.valueOf()) ? String(value) : new Intl.DateTimeFormat('en-US', {dateStyle:'medium', timeStyle:'short'}).format(parsed);
  }
  global.NajdiI18n = Object.freeze({locale:'en-US', direction:'ltr', messages:en, status, term, date});
})(window);

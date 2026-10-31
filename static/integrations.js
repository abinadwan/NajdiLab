/* Settings local-service controls. Backend consent and endpoints stay authoritative. */
window.NajdiIntegrations = (() => {
  let discovered = false;
  let busy = false;
  let snapshot = {items: []};
  const el = id => document.querySelector(`#${id}`);

  function setBusy(value) {
    busy = value;
    el('integrations-controls').disabled = value;
    el('integrations-controls').setAttribute('aria-busy', String(value));
  }

  function status(message, error = false) {
    const host = el('integration-status');
    host.textContent = message;
    host.className = error ? 'integration-notice integration-error' : 'integration-notice';
  }

  function renderNative(service, button) {
    const native = service.native_capture;
    if (!native) return '<p class="integration-error">Native capture status unavailable. Collection remains OFF.</p>';
    const id = esc(service.id);
    const expected = {hermes: 'state.db', lmstudio: 'conversations', ollama: 'db.sqlite'}[service.id];
    return `<section class="native-capture" aria-labelledby="native-heading-${id}">
      <h4 id="native-heading-${id}">Native application capture</h4>
      <strong class="integration-badge blocked">${esc(native.capability)}</strong>
      <p>${esc(native.reason)}</p>
      <dl><div><dt>Native source detection</dt><dd>${esc(native.source_status)} · ${esc(native.source_location)}</dd></div>
        <div><dt>Installed version</dt><dd>${esc(native.version)}</dd></div>
        <div><dt>Source format verification</dt><dd>${esc(native.format_verification)}</dd></div>
        <div><dt>Native source connection</dt><dd>${esc(native.connection)}</dd></div>
        <div><dt>Last successful capture</dt><dd>${native.last_capture_at ? esc(fmtDate(native.last_capture_at)) : 'Never'}</dd></div>
        <div><dt>Local native disconnect</dt><dd>${native.local_disconnect_verified ? 'VERIFIED' : 'NOT_VERIFIED'}</dd></div></dl>
      <label class="native-collection-label" for="native-enabled-${id}"><input type="checkbox" id="native-enabled-${id}" disabled> Automatic Conversation Collection <b>OFF</b></label>
      <p>No source conversations are read or imported. A model test is not native application capture. Installed-version and owner acceptance tests remain unverified.</p>
      ${native.last_error ? `<p class="integration-error">${esc(native.last_error.code)}: ${esc(native.last_error.message)}</p>` : ''}
      <div class="integration-actions">${button('native-connect', 'Connect native source', true)}${button('native-disable', 'Verify collection OFF')}${button('native-disconnect', 'Verify native disconnect')}</div>
      ${native.source_status === 'DETECTED' ? '' : `<details class="native-path-fallback"><summary>Select a local source path (metadata only)</summary><p>Automatic source detection did not succeed. Choose the existing ${esc(expected)} source. This verifies metadata only, never reads conversations, and cannot enable capture or verify its format.</p><label for="native-path-${id}">Absolute local path to ${esc(expected)}</label><input type="text" id="native-path-${id}" maxlength="4096" autocomplete="off" spellcheck="false"><div class="integration-actions">${button('native-path', 'Use source path')}</div></details>`}
    </section>`;
  }

  async function nativeAction(service, action) {
    if (action === 'connect' || action === 'enable') {
      status(`${service.native_capture?.capability || 'BLOCKED'}: ${service.native_capture?.reason || 'No verified native capture method.'}`, true);
      return;
    }
    if (!['path', 'disable', 'disconnect'].includes(action)) return;
    const payload = {approved: true};
    if (action === 'path') {
      payload.path = el(`native-path-${service.id}`).value;
      if (!payload.path.trim()) {status('Choose an absolute local source path first.', true); return;}
    }
    const message = action === 'path'
      ? `Allow NajdiLab to inspect the selected ${service.name} source path metadata only? No conversation/configuration contents are read, no files are changed, and capture remains OFF.`
      : `Verify NajdiLab native collection is OFF for ${service.name}? Existing review data stays intact. This does not change or stop the external application.`;
    if (!confirm(message)) return;
    setBusy(true);
    try {
      render(await api(`/api/v1/integrations/${encodeURIComponent(service.id)}/native/${action}`, {method: 'POST', body: JSON.stringify(payload)}));
      status(action === 'path' ? 'Source metadata detected. Native capture remains OFF; version/format and native collection are not verified.' : 'NajdiLab native collection OFF and local disconnect verified. External application unchanged.');
    } catch (error) {
      status(`Native action refused: ${error.message}`, true);
    } finally {
      setBusy(false);
    }
  }

  function render(data) {
    snapshot = data;
    el('integration-cards').innerHTML = data.items.map(service => {
      const source = service.kind === 'conversation_source';
      const connected = service.connection === 'CONNECTED';
      const id = esc(service.id);
      const button = (action, text, disabled = false) => `<button type="button" class="button ghost" data-integration-action="${action}" data-connector="${id}" ${disabled ? 'disabled' : ''}>${text}<span class="sr-only"> ${esc(service.name)}</span></button>`;
      return `<article class="panel integration-card" aria-labelledby="integration-name-${id}">
        <header><h3 id="integration-name-${id}">${esc(service.name)}</h3><strong class="integration-badge ${source ? 'blocked' : ''}">${esc(service.connection)}</strong></header>
        <p>${source ? 'Conversation source · automatic collection BLOCKED' : 'Model runtime · no automatic conversation history collection'}</p>
        ${service.endpoint ? `<code>${esc(service.endpoint)}</code>` : ''}
        <dl><div><dt>Known installation marker</dt><dd>${esc(service.installation)}</dd></div>
          <div><dt>API availability</dt><dd>${esc(service.availability)}</dd></div>
          <div><dt>Last check</dt><dd>${esc(fmtDate(service.last_checked_at))}</dd></div>
          <div><dt>Last success</dt><dd>${esc(fmtDate(service.last_success_at))}</dd></div>
          <div><dt>Synthetic test</dt><dd>${esc(service.last_test?.status || 'NOT_RUN')} ${esc(service.last_test?.at ? fmtDate(service.last_test.at) : '')}</dd></div>
          <div><dt>Local disconnect</dt><dd>${service.disconnect.local_verified ? 'VERIFIED' : 'NOT_VERIFIED'} ${esc(service.disconnect.verified_at ? fmtDate(service.disconnect.verified_at) : '')}</dd></div></dl>
        ${source ? '<p class="integration-notice">Hermes v0.22.5 may ignore outbound fields and enabled:false. NajdiLab does not configure hooks; external configuration has not been inspected. External sender: UNVERIFIED. Blocking this receiver does not prove Hermes stopped sending.</p>' : `<p>Selected model: <b>${esc(service.selected_model || 'None')}</b></p>
          <label for="integration-model-${id}">Available models (${service.models.length})</label>
          <select id="integration-model-${id}" ${connected ? '' : 'disabled'}><option value="">Choose a model</option>${service.models.map(model => `<option value="${esc(model)}" ${model === service.selected_model ? 'selected' : ''}>${esc(model)}</option>`).join('')}</select>`}
        ${service.last_error ? `<p class="integration-error">${esc(service.last_error.code)}: ${esc(service.last_error.message)}</p>` : ''}
        <div class="integration-actions">${button('connect', 'Connect', source || connected)}${source ? '' : button('select', 'Use model', !connected || !service.models.length)}${button('test', 'Test connection', source || !connected || !service.selected_model)}${button('disconnect', source ? 'Verify receiver block' : 'Disconnect', !source && !connected)}</div>
        ${renderNative(service, button)}
      </article>`;
    }).join('');
  }

  async function load(rescan = false) {
    if (busy) return;
    setBusy(true);
    status('Checking integration status…');
    try {
      render(await api('/api/v1/integrations'));
      if (!discovered || rescan) {
        status('Read-only discovery at two known loopback APIs and known directory markers…');
        render(await api('/api/v1/integrations/discover', {method: 'POST', body: '{}'}));
        discovered = true;
      }
      status('Discovery does not connect services. Results may be cached for 10 seconds. Consent and model selection reset when NajdiLab restarts.');
    } catch (error) {
      el('integration-cards').innerHTML = '';
      status(`Unable to load integrations: ${error.message}`, true);
    } finally {
      setBusy(false);
    }
  }

  el('integration-scan').onclick = () => load(true);
  el('integration-cards').onclick = async event => {
    const button = event.target.closest('[data-integration-action]');
    if (!button || busy) return;
    const {integrationAction: action, connector: id} = button.dataset;
    const service = snapshot.items.find(item => item.id === id);
    if (!service) return;
    if (action.startsWith('native-')) return nativeAction(service, action.slice(7));
    const payload = {approved: true};
    if (action === 'test') payload.selection_revision = service.selection_revision;
    if (action === 'select') {
      payload.model = el(`integration-model-${id}`).value;
      if (!payload.model) {status('Choose an available model first.', true); return;}
    }
    const messages = {
      connect: `Allow NajdiLab to connect to ${service.name} in this server session? This reads its model list. It does not collect conversation history or start training.`,
      select: `Use ${payload.model} in ${service.name} for synthetic tests in this server session? This does not start generation.`,
      test: `Send only the synthetic prompt "Reply with OK." to ${service.name}, model ${service.selected_model}? This may load the selected model and use local compute. NajdiLab stores no conversation or generated text.`,
      disconnect: service.kind === 'conversation_source'
        ? 'Verify the local Hermes receiver remains blocked? This does not stop Hermes or verify external sender disconnect.'
        : `Disconnect ${service.name} from NajdiLab? This waits for any in-flight test and revokes local test access. It does not stop or unload the runtime.`
    };
    if (!messages[action] || !confirm(messages[action])) return;
    setBusy(true);
    status('Applying approved action…');
    try {
      const data = await api(`/api/v1/integrations/${encodeURIComponent(id)}/${action}`, {method: 'POST', body: JSON.stringify(payload)});
      render(data);
      const updated = data.items.find(item => item.id === id);
      if (action === 'disconnect') {
        status(service.kind === 'conversation_source' ? 'Local receiver block verified. External sender disconnect remains UNVERIFIED.' : 'Local disconnect verified. The external runtime remains running.');
      } else if (updated.last_error) {
        status(`${updated.last_error.code}: ${updated.last_error.message}`, true);
      } else {
        status(action === 'test' ? `Synthetic connection test: ${updated.last_test?.status || 'NOT_RUN'}.` : 'Approved action completed for this server session.');
      }
    } catch (error) {
      try {render(await api('/api/v1/integrations'));} catch {el('integration-cards').innerHTML = '';}
      status(`Action failed: ${error.message}`, true);
    } finally {
      setBusy(false);
    }
  };
  return {load};
})();

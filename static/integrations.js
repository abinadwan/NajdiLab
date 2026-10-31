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

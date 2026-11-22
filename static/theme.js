(() => {
  const key = 'najdilab.theme';
  const read = () => { try { return localStorage.getItem(key); } catch { return null; } };
  const write = value => { try { localStorage.setItem(key, value); } catch { /* not persisted */ } };
  const media = matchMedia('(prefers-color-scheme: dark)');
  const apply = mode => {
    const safe = ['light','dark','system'].includes(mode) ? mode : 'system';
    const dark = safe === 'dark' || (safe === 'system' && media.matches);
    document.documentElement.dataset.themeMode = safe;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.querySelectorAll('#theme-select,#theme-select-settings').forEach(select => { select.value = safe; });
    const status = document.querySelector('#theme-status');
    if (status) status.textContent = `Current theme: ${dark ? 'Dark' : 'Light'}`;
  };
  document.addEventListener('DOMContentLoaded', () => {
    apply(read() || 'system');
    document.querySelectorAll('#theme-select,#theme-select-settings').forEach(select => select.addEventListener('change', event => {
      write(event.target.value); apply(event.target.value);
    }));
  });
  media.addEventListener?.('change', () => {
    if ((read() || 'system') === 'system') apply('system');
  });
})();

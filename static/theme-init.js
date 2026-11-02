(() => {
  const key = 'najdilab.theme';
  let saved = null;
  try { saved = localStorage.getItem(key); } catch { /* storage blocked: fall back to system */ }
  const mode = ['light','dark','system'].includes(saved) ? saved : 'system';
  const dark = mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
})();

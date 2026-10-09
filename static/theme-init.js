(() => {
  const key = 'najdilab.theme';
  const saved = localStorage.getItem(key);
  const mode = ['light','dark','system'].includes(saved) ? saved : 'system';
  const dark = mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
})();

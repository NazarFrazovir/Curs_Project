(function () {
  const wrap = document.getElementById('cmdk');
  if (!wrap) return;
  const input = document.getElementById('cmdk-input');
  const list  = document.getElementById('cmdk-list');

  function open() {
    wrap.hidden = false;
    input.value = '';
    filter('');
    input.focus();
  }
  function close() { wrap.hidden = true; }

  function filter(q) {
    const items = [...list.querySelectorAll('li')];
    const t = q.trim().toLowerCase();
    items.forEach(li => {
      const show = !t || li.textContent.toLowerCase().includes(t);
      li.style.display = show ? '' : 'none';
    });
    // підсвіт першого видимого
    const first = items.find(li => li.style.display !== 'none');
    items.forEach(li => li.classList.remove('active'));
    if (first) first.classList.add('active');
  }

  input.addEventListener('input', e => filter(e.target.value));
  input.addEventListener('keydown', e => {
    const items = [...list.querySelectorAll('li')].filter(li => li.style.display !== 'none');
    const idx = items.findIndex(li => li.classList.contains('active'));
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = items[Math.min(idx + 1, items.length - 1)];
      if (next) { items.forEach(li => li.classList.remove('active')); next.classList.add('active'); }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = items[Math.max(idx - 1, 0)];
      if (prev) { items.forEach(li => li.classList.remove('active')); prev.classList.add('active'); }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const cur = items[idx >= 0 ? idx : 0];
      if (cur) window.location.href = cur.dataset.href;
    } else if (e.key === 'Escape') {
      e.preventDefault(); close();
    }
  });

  list.addEventListener('click', e => {
    const li = e.target.closest('li');
    if (!li) return;
    window.location.href = li.dataset.href;
  });

  // Ctrl/Cmd+K — відкрити/закрити
  document.addEventListener('keydown', e => {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && (e.key.toLowerCase() === 'k')) {
      e.preventDefault();
      if (wrap.hidden) open(); else close();
    } else if (e.key === 'Escape' && !wrap.hidden) {
      close();
    }
  });
})();

(function () {
  function cellValue(td) {
    if (!td) return '';
    const t = td.textContent.trim().replace(/\s+/g, ' ');
    // якщо це число/гроші — парсимо
    const num = t.replace(/[^\d\.\-]/g, '');
    return num !== '' && !isNaN(Number(num)) ? Number(num) : t.toLowerCase();
  }

  function sortTable(tbl, col, dir) {
    const tbody = tbl.tBodies[0];
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort((a, b) => {
      const av = cellValue(a.children[col]);
      const bv = cellValue(b.children[col]);
      if (av < bv) return dir === 'asc' ? -1 : 1;
      if (av > bv) return dir === 'asc' ? 1 : -1;
      return 0;
    });
    rows.forEach(r => tbody.appendChild(r));
  }

  document.querySelectorAll('table.grid').forEach(tbl => {
    const ths = tbl.querySelectorAll('thead th');
    ths.forEach((th, idx) => {
      const text = th.textContent.trim();
      if (/^дії$/i.test(text)) return; // не сортуємо колонку дій
      th.classList.add('sortable');
      th.addEventListener('click', () => {
        const cur = th.classList.contains('sort-asc') ? 'asc'
                  : th.classList.contains('sort-desc') ? 'desc' : null;
        ths.forEach(x => x.classList.remove('sort-asc','sort-desc'));
        const next = cur === 'asc' ? 'desc' : 'asc';
        th.classList.add(next === 'asc' ? 'sort-asc' : 'sort-desc');
        sortTable(tbl, idx, next);
      });
    });
  });
})();

// static/js/nav.js
document.addEventListener('DOMContentLoaded', () => {
  const nav = document.getElementById('mainmenu');
  if (!nav) return;

  const burger  = document.querySelector('.nav-toggle');
  const toggles = Array.from(nav.querySelectorAll('.menu .menu-toggle'));

  const getMenu = (btn) => {
    const id = btn.getAttribute('aria-controls');
    return id ? document.getElementById(id) : null;
  };

  const setOpen = (wrap, open) => {
    const btn  = wrap.querySelector('.menu-toggle');
    const menu = getMenu(btn);
    if (!menu) return;
    wrap.classList.toggle('open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    menu.hidden = !open;
  };

  const closeAll = (exceptWrap = null) => {
    toggles.forEach((btn) => {
      const wrap = btn.closest('.menu');
      if (wrap && wrap !== exceptWrap) setOpen(wrap, false);
    });
  };

  // 1) Ініціалізація (сховати всі підменю)
  toggles.forEach((btn) => {
    const menu = getMenu(btn);
    if (menu) menu.hidden = true;

    // Клік мишею
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const wrap = btn.closest('.menu');
      const willOpen = !wrap.classList.contains('open');
      closeAll(wrap);
      setOpen(wrap, willOpen);
    });

    // Клавіатура
    btn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        btn.click();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeAll();
        btn.focus();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        const wrap = btn.closest('.menu');
        if (!wrap.classList.contains('open')) {
          setOpen(wrap, true);
        }
        const menu  = getMenu(btn);
        const first = menu && menu.querySelector('a,button,[tabindex]:not([tabindex="-1"])');
        if (first) first.focus();
      }
    });
  });

  // 2) Клік поза меню — закрити все
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.menu')) closeAll();
  });

  // 3) Esc будь-де — закрити все
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAll();
  });

  // 4) Бургер (мобільна навігація)
  if (burger) {
    burger.addEventListener('click', () => {
      const expanded = burger.getAttribute('aria-expanded') === 'true';
      burger.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      nav.classList.toggle('open', !expanded);
      if (expanded) closeAll();
    });

    // Клік по елементу підменю — згорнути бургер
    nav.addEventListener('click', (e) => {
      if (e.target.closest('.submenu a')) {
        burger.setAttribute('aria-expanded', 'false');
        nav.classList.remove('open');
        closeAll();
      }
    });
  }
});

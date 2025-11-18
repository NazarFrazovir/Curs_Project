// Mini onboarding tour (4 кроки)
(function () {
  const STEPS = [
    {
      sel: '.brand',
      title: 'Головна панель',
      text: 'Клік по назві — повертає на дашборд із ключовими показниками.'
    },
    {
      sel: '[aria-controls="dict-menu"]',
      title: 'Довідники',
      text: 'Постачальники, покупці та товари — база, з якої починаються всі операції.'
    },
    {
      sel: '[aria-controls="ops-menu"]',
      title: 'Операції',
      text: 'Приходи/витрати та угоди. Тут відбувається щоденна робота.'
    },
    {
      sel: '[aria-controls="user-menu"]',
      title: 'Профіль та налаштування',
      text: 'Тема/щільність, фільтри за замовчуванням, вихід із системи.'
    }
  ];

  let i = -1;
  let backdrop, tip, lastHL;

  function el(q){ return document.querySelector(q); }
  function ce(tag, cls){ const n = document.createElement(tag); if (cls) n.className = cls; return n; }

  function ensureNodes(){
    if (!backdrop){
      backdrop = ce('div','tour-backdrop');
      document.body.appendChild(backdrop);
      backdrop.addEventListener('click', end);
    }
    if (!tip){
      tip = ce('div','tour-tip');
      tip.innerHTML = `
        <h4 class="tt-title"></h4>
        <p class="tt-text"></p>
        <div class="row">
          <button class="btn btn-sm" data-prev>Назад</button>
          <button class="btn btn-sm btn-ok" data-next>Далі</button>
          <button class="btn btn-sm" data-end>Завершити</button>
        </div>
      `;
      document.body.appendChild(tip);
      tip.querySelector('[data-prev]').addEventListener('click', prev);
      tip.querySelector('[data-next]').addEventListener('click', next);
      tip.querySelector('[data-end]').addEventListener('click', end);
      window.addEventListener('resize', () => { if (i>=0) position(STEPS[i].sel); }, { passive:true });
      document.addEventListener('keydown', (e) => {
        if (i<0) return;
        if (e.key === 'Escape') end();
        if (e.key === 'ArrowRight' || e.key === 'Enter') next();
        if (e.key === 'ArrowLeft') prev();
      });
    }
  }

  function scrollIfNeeded(rect){
    const pad = 16;
    const wh = window.innerHeight, ww = window.innerWidth;
    let top = window.scrollY, left = window.scrollX;
    if (rect.top < pad) window.scrollBy({ top: rect.top - pad, behavior: 'smooth' });
    else if (rect.bottom > wh - pad) window.scrollBy({ top: rect.bottom - wh + pad, behavior: 'smooth' });
    if (rect.left < pad) window.scrollBy({ left: rect.left - pad, behavior: 'smooth' });
    else if (rect.right > ww - pad) window.scrollBy({ left: rect.right - ww + pad, behavior: 'smooth' });
  }

  function position(sel){
    const target = el(sel) || document.body;
    const r = target.getBoundingClientRect();
    // highlight
    lastHL && lastHL.classList.remove('tour-highlight');
    target.classList.add('tour-highlight');
    lastHL = target;
    // ensure visible
    scrollIfNeeded(r);
    // place tip: нижче, якщо є місце, інакше — вище
    const pad = 8;
    const tRect = { w: Math.min(360, window.innerWidth - 24), h: 120 };
    tip.style.width = tRect.w + 'px';
    let top = r.bottom + pad + window.scrollY;
    let left = r.left + window.scrollX;

    // якщо знизу мало місця — показати над елементом
    if (r.bottom + tRect.h + 24 > window.innerHeight){
      top = r.top - tRect.h - pad + window.scrollY;
    }
    // якщо виходимо за правий край — підтягнути
    if (left + tRect.w > window.scrollX + window.innerWidth - 8){
      left = window.scrollX + window.innerWidth - tRect.w - 8;
    }
    // мінімальний відступ зліва
    if (left < window.scrollX + 8) left = window.scrollX + 8;

    tip.style.transform = `translate(${left}px, ${top}px)`;
  }

  function show(n){
    i = n;
    if (i < 0 || i >= STEPS.length) { end(); return; }
    const s = STEPS[i];
    const t = el(s.sel);
    // якщо цілі немає (наприклад, на мобільному) — поруч із хедером
    const anchor = t || el('.topbar') || document.body;

    tip.querySelector('.tt-title').textContent = s.title;
    tip.querySelector('.tt-text').textContent = s.text;
    tip.querySelector('[data-prev]').disabled = (i === 0);
    tip.querySelector('[data-next]').textContent = (i === STEPS.length - 1 ? 'Готово' : 'Далі');

    position(anchor);
  }

  function start(){
    ensureNodes();
    backdrop.style.display = 'block';
    tip.style.display = 'block';
    show(0);
  }

  function next(){
    if (i >= STEPS.length - 1) { end(); return; }
    show(i + 1);
  }

  function prev(){
    if (i > 0) show(i - 1);
  }

  function end(){
    if (lastHL) lastHL.classList.remove('tour-highlight');
    lastHL = null;
    if (tip) tip.style.display = 'none';
    if (backdrop) backdrop.style.display = 'none';
  }

  // Експортуємо у глобал
  window.Tour = { start, next, prev, end };
})();

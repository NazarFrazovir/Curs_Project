// static/js/shortcuts.js

(function () {
  const $help = () => document.getElementById('kbd-help');

  function openHelp() {
    const m = $help();
    if (!m) return;
    m.style.display = 'block';
    const closeBtn = document.getElementById('kbd-help-close');
    if (closeBtn) closeBtn.focus();
  }

  function closeHelp() {
    const m = $help();
    if (!m) return;
    m.style.display = 'none';
  }

  function isHelpOpen() {
    const m = $help();
    return m && m.style.display === 'block';
  }

  // Закриття по кнопці
  document.addEventListener('click', (e) => {
    if (e.target && e.target.id === 'kbd-help-close') {
      closeHelp();
    }
    // Клік поза карткою — теж закриває
    const m = $help();
    if (m && e.target === m) {
      closeHelp();
    }
  });

  // Глобальні шорткати
  document.addEventListener('keydown', (e) => {
    // F1 — довідка
    if (e.key === 'F1') {
      e.preventDefault();
      if (isHelpOpen()) closeHelp(); else openHelp();
      return;
    }

    // Esc — закрити довідку / діалог / повернутися
    if (e.key === 'Escape') {
      // 1) Якщо відкрита довідка — закриваємо
      if (isHelpOpen()) {
        e.preventDefault();
        closeHelp();
        return;
      }
      // 2) Якщо на сторінці є елемент з data-esc — активуємо його (посилання або кнопка)
      const escEl = document.querySelector('[data-esc]');
      if (escEl) {
        e.preventDefault();
        if (escEl.tagName === 'A' && escEl.href) {
          window.location.href = escEl.href;
        } else {
          escEl.click();
        }
        return;
      }
      // 3) Інакше — назад, а якщо історії немає — на домашню
      e.preventDefault();
      try {
        if (document.referrer && new URL(document.referrer).origin === location.origin) {
          history.back();
        } else if (window.APP_HOME) {
          window.location.href = window.APP_HOME;
        }
      } catch {
        if (window.APP_HOME) window.location.href = window.APP_HOME;
      }
      return;
    }

    // Enter — підтвердити дію / надіслати найближчу форму
    if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) {
      const t = e.target;
      const tag = (t.tagName || '').toUpperCase();

      // Не перехоплюємо Enter у textarea/контент-редакторах або коли явна кнопка у фокусі
      const isTextarea = tag === 'TEXTAREA' || t.isContentEditable;
      const isButtonish = tag === 'BUTTON' || (tag === 'INPUT' && ['BUTTON', 'SUBMIT', 'RESET'].includes((t.type || '').toUpperCase()));
      if (isTextarea || isButtonish) return;

      const clickable = t.closest && t.closest('a[href], button, [role="button"], [data-toggle]');
    if (!t.closest('form') && clickable) {
    e.preventDefault();
    clickable.click();
    return;
  }

      // Знаходимо найближчу форму
      const form = t.closest && t.closest('form');
      if (form) {
        // Можна відключити цю поведінку для конкретної форми: data-enter-submits="false"
        if (form.dataset && form.dataset.enterSubmits === 'false') return;
        // Щоб уникнути подвійної відправки — блокуємо дефолт і викликаємо requestSubmit
        e.preventDefault();
        if (typeof form.requestSubmit === 'function') form.requestSubmit();
        else form.submit();
      }
    }
  });
})();


// --- Mini tour ---------------------------------------------------
window.startMiniTour = function () {
  // Закриваємо overlay гарячих клавіш, якщо відкритий
  const help = document.getElementById('kbd-help');
  if (help) help.style.display = 'none';

  const steps = [
    {
      sel: '[data-tour="brand"]',
      title: 'Головна панель',
      text: 'Клік по назві повертає на дашборд із ключовими показниками.'
    },
    {
      sel: '[data-tour="home-hero"], [data-tour="table"], .grid-wrap',
      title: 'Основний контент',
      text: 'Тут ви працюєте з даними: списки, таблиці, картки.'
    }
  ];

  const bubble = document.createElement('div');
  bubble.className = 'tour-box';
  bubble.innerHTML = `
    <div class="tour-title"></div>
    <div class="tour-text"></div>
    <div class="tour-actions">
      <button class="btn btn-sm" data-prev>Назад</button>
      <button class="btn btn-sm btn-ok" data-next>Далі</button>
      <button class="btn btn-sm" data-done>Завершити</button>
    </div>
  `;
  document.body.appendChild(bubble);

  let i = 0;
  showStep(i);

  bubble.querySelector('[data-prev]').onclick = () => { i = Math.max(0, i - 1); showStep(i); };
  bubble.querySelector('[data-next]').onclick = () => { i = Math.min(steps.length - 1, i + 1); showStep(i); };
  bubble.querySelector('[data-done]').onclick = close;
  window.addEventListener('resize', () => showStep(i));
  window.addEventListener('scroll', () => showStep(i), { passive: true });
  document.addEventListener('keydown', onEsc);

  function onEsc(e){ if (e.key === 'Escape') close(); }

  function close() {
    window.removeEventListener('resize', () => showStep(i));
    window.removeEventListener('scroll', () => showStep(i));
    document.removeEventListener('keydown', onEsc);
    bubble.remove();
  }

  function clamp(n, min, max) { return Math.max(min, Math.min(max, n)); }

  function showStep(idx) {
    const step = steps[idx];
    const target = document.querySelector(step.sel);
    bubble.querySelector('.tour-title').textContent = step.title;
    bubble.querySelector('.tour-text').textContent = step.text;

    // Кнопки стану
    bubble.querySelector('[data-prev]').disabled = (idx === 0);
    bubble.querySelector('[data-next]').disabled = (idx === steps.length - 1);

    // Позиціювання
    let left = 16, top = window.innerHeight - bubble.offsetHeight - 16;

    if (target) {
      const r = target.getBoundingClientRect();
      // базово — під елемент
      left = r.left;
      top  = r.bottom + 10;

      // якщо не влазить знизу — показуємо над елементом
      requestAnimationFrame(() => {
        const bw = bubble.offsetWidth, bh = bubble.offsetHeight;
        if (top + bh > window.innerHeight - 16) top = r.top - bh - 10;

        // підрізаємо у в’юпорті
        left = clamp(left, 16, window.innerWidth  - bw - 16);
        top  = clamp(top,  16, window.innerHeight - bh - 16);

        bubble.style.left = left + 'px';
        bubble.style.top  = top  + 'px';
      });
    } else {
      // Fallback: центр екрана
      requestAnimationFrame(() => {
        const bw = bubble.offsetWidth, bh = bubble.offsetHeight;
        left = (window.innerWidth  - bw) / 2;
        top  = (window.innerHeight - bh) / 2;
        bubble.style.left = clamp(left, 16, window.innerWidth  - bw - 16) + 'px';
        bubble.style.top  = clamp(top,  16, window.innerHeight - bh - 16) + 'px';
      });
    }

    bubble.style.position = 'fixed';
    bubble.style.zIndex = 10050; // вище оверлеїв
  }
};


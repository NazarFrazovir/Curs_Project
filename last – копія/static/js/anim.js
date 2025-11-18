// Плавна поява сторінки
document.addEventListener('DOMContentLoaded', () => {
  document.body.classList.add('is-ready');

  // Автозгортання флешів
  document.querySelectorAll('.flash').forEach(el => {
    // залишаємо 3.5с на читання
    const timeout = el.classList.contains('error') ? 6000 : 3500;
    setTimeout(() => {
      el.classList.add('hide');
      setTimeout(() => el.remove(), 220);
    }, timeout);
  });
});



// Reveal on scroll (cards, секції з data-reveal)
(() => {
  const toObserve = [
    ...document.querySelectorAll('[data-reveal]'),
    ...document.querySelectorAll('.cards-grid'), // для дашборду
  ];
  if (!toObserve.length) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('show');
        io.unobserve(e.target);
      }
    });
  }, {threshold: .12});

  toObserve.forEach(el => {
    el.classList.add(el.classList.contains('cards-grid') ? 'reveal-stagger' : 'reveal');
    io.observe(el);
  });
})();




// Click ripple for .btn.ripple
(() => {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn.ripple');
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const wave = document.createElement('span');
    wave.className = 'ripple-wave';
    const size = Math.max(rect.width, rect.height);
    wave.style.width = wave.style.height = size + 'px';
    wave.style.left = (e.clientX - rect.left - size/2) + 'px';
    wave.style.top  = (e.clientY - rect.top  - size/2) + 'px';
    btn.appendChild(wave);
    setTimeout(() => wave.remove(), 520);
  });
})();

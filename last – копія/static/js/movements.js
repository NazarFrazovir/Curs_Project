// Перемикання видимості/доступності полів за типом операції IN/OUT
(function () {
  function toggleByType() {
    var typeSel = document.getElementById('mtype');
    if (!typeSel) return;

    var isIN = typeSel.value === 'IN';

    var supWrap = document.getElementById('supplier_wrap');
    var custWrap = document.getElementById('customer_wrap');
    var agrWrap  = document.getElementById('agreement_wrap');

    var sup = document.getElementById('supplier_id');
    var cust = document.getElementById('customer_id');
    var agr  = document.getElementById('agreement_id');

    if (supWrap) supWrap.style.display = isIN ? '' : 'none';
    if (custWrap) custWrap.style.display = isIN ? 'none' : '';
    if (agrWrap)  agrWrap.style.display  = isIN ? 'none' : '';

    if (sup)  sup.disabled  = !isIN;
    if (cust) cust.disabled =  isIN;
    if (agr)  agr.disabled  =  isIN;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var typeSel = document.getElementById('mtype');
    if (!typeSel) return;
    toggleByType();
    typeSel.addEventListener('change', toggleByType);
  });
})();


// Перемикання полів для сторінки редагування руху
(function () {
  function toggleByType() {
    var typeSel = document.getElementById('mtype');
    if (!typeSel) return;
    var isIN = typeSel.value === 'IN';

    var supWrap = document.getElementById('supplier_wrap');
    var custWrap = document.getElementById('customer_wrap');
    var agrWrap  = document.getElementById('agreement_wrap');

    if (supWrap) supWrap.style.display = isIN ? '' : 'none';
    if (custWrap) custWrap.style.display = isIN ? 'none' : '';
    if (agrWrap)  agrWrap.style.display  = isIN ? 'none' : '';
  }

  document.addEventListener('DOMContentLoaded', function () {
    toggleByType();
    var typeSel = document.getElementById('mtype');
    if (typeSel) typeSel.addEventListener('change', toggleByType);
  });
})();

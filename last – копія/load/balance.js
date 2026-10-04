// Навантажувальний тест GET /api/balance (k6).
// Запуск:  k6 run -e PROFILE=normal load/balance.js
//          k6 run -e PROFILE=stress load/balance.js
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5050';
const PROFILE = __ENV.PROFILE || 'normal';

// Модель навантаження: два режими.
const PROFILES = {
  // Нормальний: робочий день невеликого складу — до 10 операторів одночасно,
  // кожен перевіряє залишки приблизно раз на секунду (~10 RPS).
  normal: {
    stages: [
      { duration: '20s', target: 10 },  // ramp-up
      { duration: '1m', target: 10 },   // стабільне навантаження
      { duration: '10s', target: 0 },   // ramp-down
    ],
    pause: 1,
  },
  // Підвищене: пік (інвентаризація, масові відвантаження) — 100 клієнтів
  // майже без пауз, у рази більше за нормальний режим.
  stress: {
    stages: [
      { duration: '20s', target: 100 },
      { duration: '1m', target: 100 },
      { duration: '10s', target: 0 },
    ],
    pause: 0.1,
  },
};

const profile = PROFILES[PROFILE];
if (!profile) {
  throw new Error(`Unknown PROFILE "${PROFILE}", use normal or stress`);
}

export const options = {
  stages: profile.stages,
  // SLO: якщо хоча б один поріг не виконано, k6 завершується з кодом 99 (FAIL).
  thresholds: {
    http_req_duration: ['p(95)<300'],   // p95 часу відповіді < 300 мс
    http_req_failed: ['rate<0.01'],     // Error Rate < 1 %
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const res = http.get(`${BASE_URL}/api/balance`, { tags: { name: 'GET /api/balance' } });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'body has items': (r) => {
      try {
        return Array.isArray(r.json('items'));
      } catch (e) {
        return false;
      }
    },
  });
  sleep(profile.pause);
}

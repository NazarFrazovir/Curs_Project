# Helm-чарт Curs_Project

> У ЛР5 чарт перенесено з `helm/curs-project` до `charts/curs-project` (див. `gitops/README.md`).

Лабораторна №4 «Технології DevOps». Чарт `charts/curs-project` пакує той самий застосунок, що й `k8s/` у ЛР3
(Flask + PostgreSQL) і дає той самий набір об'єктів у кластері.

## Структура

```
charts/curs-project/
├── Chart.yaml              # name, description, version, appVersion
├── values.yaml             # значення за замовчуванням (середовище dev)
├── values-dev.yaml         # dev: 2 репліки, тег 1.0.0, без Ingress
├── values-prod.yaml        # prod: 3 репліки, тег 1.1.0, більші ресурси, Ingress
├── files/sql/*.sql         # SQL-схема (копія last – копія/sql/), іде в ConfigMap
└── templates/
    ├── _helpers.tpl        # імена та мітки (include в усіх маніфестах)
    ├── NOTES.txt           # інструкція після встановлення
    ├── configmap.yaml, configmap-db-init.yaml, secret.yaml
    ├── postgres-pvc.yaml, postgres-deployment.yaml, postgres-service.yaml
    ├── web-deployment.yaml, web-service.yaml, ingress.yaml
    ├── hooks/pre-upgrade-job.yaml      # хук pre-upgrade
    └── tests/test-connection.yaml      # helm test
```

Відповідність ЛР3: `00-namespace` → `--create-namespace` (Helm не рекомендує Namespace у шаблонах, бо він
конфліктує з прапорцем `-n`), решта файлів `k8s/` має однойменний шаблон. Відмінності від ЛР3: імена будуються з імені
релізу; `nodePort` не прописано жорстко (інакше чарт не встановити двічі); додано хук і тест.

## version і appVersion

- `version: 0.1.0`: версія **чарта** (шаблонів і структури values). Змінюється, коли змінюється упаковка:
  новий шаблон, нове поле в values. Саме її бачить `helm list` у колонці CHART.
- `appVersion: "1.0.0"`: версія **застосунку** Curs_Project, тобто тег образу, для якого написано чарт.
  Використовується як тег за замовчуванням, якщо `image.tag` порожній, і потрапляє в мітку `app.kubernetes.io/version`.
  Виправлення в шаблонах піднімає `version`, а вихід нової версії застосунку піднімає `appVersion`.
  У prod тег образу перекривається (`1.1.0`), а `appVersion` лишається інформативним.

## Параметри values

| Параметр | За замовчуванням | Опис |
|---|---|---|
| `nameOverride`, `fullnameOverride` | `""` | Перевизначення імен |
| `image.repository` | `ghcr.io/nazarfrazovir/curs_project/web` | Репозиторій образу застосунку |
| `image.tag` | `"1.0.0"` | Тег образу (порожньо → `appVersion`) |
| `image.pullPolicy` | `IfNotPresent` | Політика завантаження |
| `web.replicaCount` | `2` | Кількість реплік застосунку |
| `web.containerPort` | `5000` | Порт контейнера |
| `web.resources` | requests 100m/128Mi, limits 500m/256Mi | Ресурси застосунку |
| `web.probes.liveness/readiness` | `/healthz`, `/readyz` + затримки | Проби |
| `web.rollingUpdate` | `maxSurge 1`, `maxUnavailable 0` | Параметри rolling update |
| `service.type` | `NodePort` | Тип Service |
| `service.port` | `80` | Порт Service |
| `service.nodePort` | `""` | Порожньо = автоматично |
| `ingress.enabled` | `false` | Створювати Ingress |
| `ingress.className`, `host`, `path`, `pathType`, `annotations` | `nginx`, `curs.local`, `/`, `Prefix`, `{}` | Параметри Ingress |
| `database.replicaCount` | `1` | Репліки PostgreSQL (одна, том RWO) |
| `database.name`, `database.user`, `database.port` | `wholesale_db`, `postgres`, `5432` | Параметри БД |
| `database.image.*` | `postgres:16-alpine` | Образ БД |
| `database.resources` | requests 100m/256Mi, limits 500m/512Mi | Ресурси БД |
| `database.persistence.enabled` | `true` | Створювати PVC (інакше `emptyDir`) |
| `database.persistence.size`, `accessMode`, `storageClass` | `1Gi`, `ReadWriteOnce`, `""` | Параметри PVC |
| `config.*` | `DB_*`, `LOG_LEVEL`, `LOG_FORMAT` | Нечутливі параметри (ConfigMap) |
| `secrets.postgresPassword` | `lab-only-db-password` | Пароль БД (Secret), лише навчальне значення |
| `secrets.secretKey` | `lab-only-flask-secret-key` | Ключ сесій Flask (Secret) |
| `hooks.preUpgrade.enabled` | `true` | Хук pre-upgrade (перевірка БД) |

У реальному середовищі паролі передавайте через `--set secrets.postgresPassword=... --set secrets.secretKey=...`,
а не через файли значень.

## Встановлення

Образи `1.0.0` і `1.1.0` мають бути в кластері (див. `k8s/README.md`: `minikube image load ...`).

```bash
# dev
helm install dev ./charts/curs-project -n curs-dev --create-namespace -f charts/curs-project/values-dev.yaml
# prod
helm install prod ./charts/curs-project -n curs-prod --create-namespace -f charts/curs-project/values-prod.yaml
```

Перед установкою видаліть реліз ЛР3 (`kubectl delete -f k8s/`), щоб не було конфлікту імен і портів.

## Різниця між середовищами без встановлення

```bash
diff <(helm template x ./charts/curs-project -f charts/curs-project/values-dev.yaml) \
     <(helm template x ./charts/curs-project -f charts/curs-project/values-prod.yaml)
```

## Пріоритет значень

Від найнижчого до найвищого: `values.yaml` чарта → файли `-f` (кожен наступний перекриває попередній, значення зливаються
по ключах) → `--set` / `--set-string` / `--set-file` (найвищий). Тому
`helm upgrade ... -f values-prod.yaml --set image.tag=9.9.9` дасть тег `9.9.9`, а решту візьме з prod. Без `--reuse-values`
Helm під час `upgrade` **не** пам'ятає попередніх `--set`: передавайте їх щоразу.

## Де Helm зберігає стан релізу

У namespace релізу, як Secret типу `helm.sh/release.v1` з іменем `sh.helm.release.v1.<реліз>.v<ревізія>`:
по одному Secret на ревізію, всередині base64 від gzip-JSON (чарт, значення, маніфест, статус). Саме з нього працюють
`helm history`, `helm get` і `helm rollback`.

## Хук і тест (завдання 9b)

- `hooks/pre-upgrade-job.yaml`: Job з анотацією `helm.sh/hook: pre-upgrade`. Перед кожним `helm upgrade` перевіряє
  `pg_isready`; якщо БД недоступна, оновлення скасовується. Видаляється після успіху (`hook-succeeded`).
- `tests/test-connection.yaml`: Pod з `helm.sh/hook: test`. `helm test <реліз> -n <ns>` робить `wget` до `/readyz` зсередини кластера.

## Примітки

- SQL у `files/sql/` дублює `last – копія/sql/` (Helm не читає файли поза каталогом чарта і не слідує символічним посиланням).
  Якщо змінюєте схему, скопіюйте файли заново.
- `helm uninstall` видаляє й PVC, тобто дані БД. Для збереження додайте анотацію `helm.sh/resource-policy: keep`.
- SQL виконується лише на порожньому томі. Зміна пароля БД через `helm upgrade` не змінює пароль уже створеної бази.

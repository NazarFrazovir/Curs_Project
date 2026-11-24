# Розгортання Curs_Project у Kubernetes (minikube)

Лабораторна №3 «Технології DevOps». Застосунок: Flask + PostgreSQL (оптова торгівля, каталог `last – копія/`).

## Склад маніфестів (один файл на об'єкт)

| Файл | Об'єкт | Призначення |
|---|---|---|
| `00-namespace.yaml` | Namespace `curs-project` | Усі об'єкти лише в ньому |
| `10-configmap.yaml` | ConfigMap `curs-config` | Нечутливі параметри |
| `11-configmap-db-init.yaml` | ConfigMap `db-init-sql` | SQL-схема з `last – копія/sql/` для першого старту БД |
| `12-secret.yaml` | Secret `curs-secret` | Чутливі параметри (навчальні значення) |
| `20-postgres-pvc.yaml` | PVC `postgres-data` | 1 Gi для даних PostgreSQL |
| `21-postgres-deployment.yaml` | Deployment `postgres` | 1 репліка, том і init-SQL |
| `22-postgres-service.yaml` | Service `postgres` (ClusterIP) | БД лише всередині кластера |
| `30-app-deployment.yaml` | Deployment `web` | 2 репліки, проби, requests/limits, RollingUpdate |
| `31-app-service.yaml` | Service `web` (NodePort 30080) | Доступ усередині кластера і з хоста |
| `32-ingress.yaml` | Ingress `web` (`curs.local`) | Доступ через ingress-nginx |

## Параметри

**ConfigMap `curs-config`**

| Ключ | Значення | Призначення |
|---|---|---|
| `POSTGRES_DB` | `wholesale_db` | Ім'я БД |
| `POSTGRES_USER` | `postgres` | Користувач БД |
| `DB_CONNECT_TIMEOUT` | `2` | Таймаут підключення до БД, с |
| `DB_RETRY_ATTEMPTS` | `3` | Кількість повторів запиту (resilience.py) |
| `DB_RETRY_BASE_DELAY` | `0.1` | Базова затримка між повторами, с |
| `DB_RETRY_MAX_DELAY` | `1.0` | Максимальна затримка, с |
| `LOG_LEVEL` | `INFO` | Рівень логування |
| `LOG_FORMAT` | `text` | Формат логів |

**Secret `curs-secret`** (значення навчальні, не з робочих систем)

| Ключ | Призначення |
|---|---|
| `POSTGRES_PASSWORD` | Пароль користувача PostgreSQL |
| `SECRET_KEY` | Ключ підпису сесій Flask (спільний для всіх реплік, тому сесія не губиться між подами) |
| `DATABASE_URL` | Рядок підключення застосунку до БД (має збігатися з паролем вище) |

## Образи

CI (`.github/workflows/ci.yml`) збирає й публікує образ у `ghcr.io/nazarfrazovir/curs_project/web`. Git-тег `vX.Y.Z` дає образ з тегом `X.Y.Z` (без `latest` у маніфестах). Версія видна в `/healthz` і в підвалі сторінок.

```bash
git tag v1.0.0 && git push origin v1.0.0        # образ :1.0.0
# змінити щось видиме (напр. текст), закомітити
git tag v1.1.0 && git push origin v1.1.0        # образ :1.1.0
```

Пакет у GHCR за замовчуванням приватний. Зробіть його публічним (Packages → Package settings → Change visibility) або використайте локальні образи:

```bash
cd "last – копія"
docker build --build-arg APP_VERSION=1.0.0 -t ghcr.io/nazarfrazovir/curs_project/web:1.0.0 .
docker build --build-arg APP_VERSION=1.1.0 -t ghcr.io/nazarfrazovir/curs_project/web:1.1.0 .
minikube image load ghcr.io/nazarfrazovir/curs_project/web:1.0.0
minikube image load ghcr.io/nazarfrazovir/curs_project/web:1.1.0
```

## Розгортання

```bash
minikube start --driver=docker
minikube addons enable metrics-server
minikube addons enable ingress

kubectl apply -f k8s/                  # одна команда: від namespace до ingress
kubectl -n curs-project get pods,deploy,rs,svc,pvc,ingress
```

Доступ із хоста:

```bash
minikube service web -n curs-project --url     # NodePort (з драйвером docker команда має працювати відкритою)
# або через ingress:
#   Linux/macOS: echo "$(minikube ip) curs.local" | sudo tee -a /etc/hosts
#   з драйвером docker на macOS/Windows: minikube tunnel, запис 127.0.0.1 curs.local
```

Дані для входу беруться з `sql/01_seed.sql`.

Повне видалення: `kubectl delete -f k8s/` (PVC теж видаляється; наступний запуск знову створить схему).

## Примітки

- Postgres: `strategy: Recreate`, бо том `ReadWriteOnce`. SQL з ConfigMap виконується лише на порожньому томі.
- `web` чекає на БД в init-контейнері (`pg_isready`); readiness-проба `/readyz` повертає 200 лише коли відповідає БД, liveness-проба `/healthz` БД не чіпає.
- `maxUnavailable: 0` + readiness-проба забезпечують доступність під час rolling update.
- Якщо змінюєте `sql/*.sql`, оновіть `11-configmap-db-init.yaml` і перестворіть PVC.

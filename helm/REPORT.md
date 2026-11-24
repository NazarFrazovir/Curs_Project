# Звіт: лабораторна №4 (Helm)

Команди для пунктів 1, 6-9. Виконуйте з кореня репозиторію, виводи зберігайте через `| tee outputs/<крок>.txt` або робіть скриншоти.

```bash
mkdir -p outputs
```

## П. 1. Середовище

```bash
brew install helm
helm version | tee outputs/1a-helm-version.txt
minikube start --driver=docker
kubectl delete -f k8s/ --ignore-not-found      # видалити реліз ЛР3 (п. 1d)
kubectl get ns | tee outputs/1d-namespaces.txt
# образи 1.0.0 і 1.1.0 мають бути завантажені (див. k8s/README.md)
minikube image ls | grep curs_project
```

## П. 6. Два середовища

```bash
# 6b: різниця без встановлення
diff <(helm template x ./charts/curs-project -f charts/curs-project/values-dev.yaml) \
     <(helm template x ./charts/curs-project -f charts/curs-project/values-prod.yaml) | tee outputs/6b-diff.txt
# 6c: пріоритет значень (див. helm/README.md): покажіть наочно
helm template x ./charts/curs-project -f charts/curs-project/values-prod.yaml | grep -E "replicas:|image:"
helm template x ./charts/curs-project -f charts/curs-project/values-prod.yaml --set web.replicaCount=7 --set image.tag=9.9.9 | grep -E "replicas:|image: .*web"
```

Очікувано: перший виклик дає `replicas: 3` і тег `1.1.0`, другий `7` і `9.9.9` (`--set` вищий за `-f`, `-f` вищий за `values.yaml`).

## П. 7. Перевірка і встановлення

```bash
helm lint ./charts/curs-project | tee outputs/7a-lint.txt
helm lint ./charts/curs-project -f charts/curs-project/values-prod.yaml
helm template dev ./charts/curs-project -n curs-dev -f charts/curs-project/values-dev.yaml > outputs/7b-rendered.yaml
# порівняння з ЛР3: той самий набір видів об'єктів
grep -hE "^kind:" k8s/*.yaml | sort | uniq -c
grep -hE "^kind:" outputs/7b-rendered.yaml | sort | uniq -c        # плюс Job і Pod (хук і тест), без Namespace

helm install dev ./charts/curs-project -n curs-dev --create-namespace -f charts/curs-project/values-dev.yaml | tee outputs/7c-install.txt
kubectl -n curs-dev rollout status deploy --timeout=180s
helm list -A | tee outputs/7d-list.txt
helm status dev -n curs-dev
helm get values dev -n curs-dev | tee outputs/7d-values.txt
helm get values dev -n curs-dev --all | head -30
minikube service dev-curs-project-web -n curs-dev        # скриншот у браузері

# 7e: де Helm зберігає стан
kubectl -n curs-dev get secrets | tee outputs/7e-secrets.txt
kubectl -n curs-dev get secret sh.helm.release.v1.dev.v1 -o jsonpath='{.data.release}' | base64 --decode | base64 --decode | gunzip | head -c 400
```

## П. 8. Життєвий цикл релізу

```bash
# 8a: зміна тега через --set (термінал 2: kubectl -n curs-dev get jobs -w  покаже хук pre-upgrade)
helm upgrade dev ./charts/curs-project -n curs-dev -f charts/curs-project/values-dev.yaml --set image.tag=1.1.0
kubectl -n curs-dev rollout status deploy/dev-curs-project-web
kubectl -n curs-dev get deploy dev-curs-project-web -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# 8b: файл значень іншого середовища (3 репліки, ресурси prod, Ingress)
helm upgrade dev ./charts/curs-project -n curs-dev -f charts/curs-project/values-prod.yaml
kubectl -n curs-dev get pods,ingress

# 8c: історія ревізій
helm history dev -n curs-dev | tee outputs/8c-history.txt
helm diff revision dev 1 2 -n curs-dev 2>/dev/null || echo "(плагін helm diff необов'язковий)"

# 8d: відкат до ревізії 2 і новий запис в історії
helm rollback dev 2 -n curs-dev
helm history dev -n curs-dev | tee outputs/8d-history.txt
kubectl -n curs-dev get deploy dev-curs-project-web -o jsonpath='{.spec.replicas} {.spec.template.spec.containers[0].image}{"\n"}'

# 8e: видалення однією командою
helm uninstall dev -n curs-dev
kubectl -n curs-dev get all,cm,secret,pvc,ingress,jobs | tee outputs/8e-empty.txt
```

Пояснення для звіту: ревізія 1 = install (тег 1.0.0, 2 репліки); 2 = upgrade `--set image.tag=1.1.0`;
3 = upgrade на `values-prod.yaml` (3 репліки, ресурси, Ingress, `LOG_LEVEL=WARNING`); 4 = rollback до стану ревізії 2
(rollback створює **нову** ревізію, а не видаляє старі). Після `helm uninstall` у namespace не лишається
об'єктів, зокрема й PVC (дані БД видалено).

## П. 9b. Хук і тест

```bash
helm install dev ./charts/curs-project -n curs-dev --create-namespace -f charts/curs-project/values-dev.yaml
kubectl -n curs-dev rollout status deploy --timeout=180s
helm test dev -n curs-dev --logs | tee outputs/9b-test.txt                 # Phase: Succeeded
# хук: у другому терміналі  kubectl -n curs-dev get jobs -w , у першому:
helm upgrade dev ./charts/curs-project -n curs-dev -f charts/curs-project/values-dev.yaml --set web.replicaCount=3
```

Хук-перевірка (негативний сценарій): `kubectl -n curs-dev scale deploy/dev-curs-project-postgres --replicas=0`,
потім `helm upgrade ...`: pre-upgrade Job не дочекається БД, `helm upgrade` завершиться помилкою, реліз
лишиться на попередній ревізії (`helm history`). Поверніть БД: `--replicas=1`.

# Звіт: лабораторна №3 (Kubernetes)

Сценарій команд для пунктів 5-7. Виконуйте по черзі й зберігайте вивід (`| tee outputs/<крок>.txt`) або робіть скриншоти.
Під кожним кроком додайте вивід/скриншот і 1-2 речення, що він доводить.

```bash
mkdir -p outputs
NS=curs-project
```

## Підготовка кластера (п. 2-3)

```bash
minikube start --driver=docker
kubectl get nodes | tee outputs/2c-nodes.txt
kubectl get pods -n kube-system | tee outputs/2c-kube-system.txt
minikube addons enable metrics-server
minikube addons enable ingress
minikube addons list | grep -E "metrics-server|ingress" | tee outputs/2d-addons.txt
```

## П. 5. Розгортання

```bash
kubectl apply -f k8s/ | tee outputs/5a-apply.txt
kubectl -n $NS rollout status deploy/postgres
kubectl -n $NS rollout status deploy/web
kubectl -n $NS get pods,deploy,rs,svc -o wide | tee outputs/5b-objects.txt
minikube service web -n $NS --url           # відкрити адресу в браузері, скриншот сторінки входу
```

Значення з ConfigMap і Secret у контейнері (5d):

```bash
POD=$(kubectl -n $NS get pod -l app=web -o jsonpath='{.items[0].metadata.name}')
kubectl -n $NS exec $POD -- sh -c 'echo LOG_LEVEL=$LOG_LEVEL DB_RETRY_ATTEMPTS=$DB_RETRY_ATTEMPTS POSTGRES_DB=$POSTGRES_DB; echo SECRET_KEY_set=${SECRET_KEY:+yes}; echo DATABASE_URL_set=${DATABASE_URL:+yes}' | tee outputs/5d-env.txt
```

(Значення Secret не друкуємо повністю; достатньо показати, що змінні задані. За потреби: `kubectl -n $NS get secret curs-secret -o jsonpath='{.data.SECRET_KEY}' | base64 -d`.)

## П. 6. Життєвий цикл

**6a. Самовідновлення**

```bash
kubectl -n $NS get pods -l app=web
kubectl -n $NS delete pod $POD
kubectl -n $NS get pods -l app=web -w       # Ctrl+C після появи нового пода у Running
```

**6b. Масштабування і розподіл трафіку**

```bash
kubectl -n $NS scale deploy/web --replicas=4
kubectl -n $NS get pods -l app=web
URL=$(minikube service web -n $NS --url)
for i in $(seq 1 20); do curl -s $URL/healthz; echo; done | sort | uniq -c | tee outputs/6b-traffic.txt
kubectl -n $NS scale deploy/web --replicas=2
```

У JSON поле `pod` показує, яка репліка відповіла; `uniq -c` дає розподіл запитів між подами.

**6c-e. Rolling update, історія, відкат, доступність**

Термінал 1 (безперервний запит, показує версію і відсутність помилок):

```bash
while true; do curl -s -o /dev/null -w "%{http_code} " $URL/readyz; curl -s $URL/healthz; echo; sleep 0.5; done | tee outputs/6e-availability.txt
```

Термінал 2:

```bash
kubectl -n $NS annotate deploy/web kubernetes.io/change-cause="update to 1.1.0" --overwrite
kubectl -n $NS set image deploy/web web=ghcr.io/nazarfrazovir/curs_project/web:1.1.0
kubectl -n $NS rollout status deploy/web | tee outputs/6c-rollout.txt
kubectl -n $NS get rs
kubectl -n $NS rollout history deploy/web | tee outputs/6d-history.txt
kubectl -n $NS rollout undo deploy/web
kubectl -n $NS rollout status deploy/web
kubectl -n $NS get deploy web -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

У виводі терміналу 1 версія змінюється `1.0.0 -> 1.1.0 -> 1.0.0`, усі коди `200`.

## П. 7. Діагностика

```bash
kubectl -n $NS set image deploy/web web=ghcr.io/nazarfrazovir/curs_project/web:9.9.9
kubectl -n $NS get pods -l app=web | tee outputs/7a-imagepull.txt       # ErrImagePull / ImagePullBackOff
BAD=$(kubectl -n $NS get pod -l app=web --field-selector=status.phase=Pending -o jsonpath='{.items[0].metadata.name}')
kubectl -n $NS describe pod $BAD | tail -20 | tee outputs/7b-describe.txt
kubectl -n $NS get events --sort-by=.lastTimestamp | tail -10
```

Через `maxUnavailable: 0` старі поди лишаються, тож застосунок працює під час збою.

```bash
GOOD=$(kubectl -n $NS get pod -l app=web --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
kubectl -n $NS logs $GOOD --tail=20 | tee outputs/7c-logs.txt
kubectl -n $NS exec -it $GOOD -- sh          # усередині: env | grep -E "DB_|LOG_"; exit
```

Виправлення:

```bash
kubectl -n $NS set image deploy/web web=ghcr.io/nazarfrazovir/curs_project/web:1.0.0
kubectl -n $NS rollout status deploy/web
kubectl -n $NS get pods -l app=web | tee outputs/7d-fixed.txt
```

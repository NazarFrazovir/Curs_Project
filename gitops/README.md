# ЛР5: GitOps, розгортання через Argo CD

Бажаний стан кластера описано в Git (варіант b: каталоги в репозиторії застосунку), Argo CD у кластері сам приводить кластер до цього опису.

```
bootstrap/root-app.yaml        # кореневий Application (App of Apps), єдиний об'єкт, що застосовується руками
argocd-apps/curs-project.yaml  # Application застосунку, його бере корінь із Git
charts/curs-project/           # Helm-чарт із ЛР4 + values-minikube.yaml
```

Що змінено в чарті порівняно з ЛР4 (`version: 0.2.0`):
- `secrets.existingSecret`: якщо задано, чарт не створює Secret, а читає готовий. Паролів у Git немає;
- `tests.enabled` і `hooks.preUpgrade.enabled`: у minikube-значеннях вимкнено. Argo CD виконує хук `pre-upgrade` як PreSync, на першій синхронізації бази ще немає, і Job не завершився б;
- `web.progressDeadlineSeconds`: у minikube 60 с, тож неіснуючий тег стає Degraded за хвилину;
- застосунок: ендпоїнт `/version` (поле `version` є також у `/healthz` і `/readyz`, версія в підвалі сторінки).

Namespace застосунку `curs-gitops`, щоб не конфліктувати з `curs-project` (ЛР3) і `curs-dev` (ЛР4).

## 0. Підготовка

```bash
git checkout lab5-gitops && git pull
helm uninstall dev -n curs-dev        # реліз ЛР4, якщо ще є
kubectl delete -f k8s/ --ignore-not-found   # об'єкти ЛР3
minikube start --driver=docker
```

Репозиторій має бути публічним, інакше підключіть його до Argo CD (розділ 3).

## 1. Репозиторій конфігурації

Структура вище. Перевірка, що в Git немає паролів: `grep -rn "password" charts/curs-project/values-minikube.yaml argocd-apps bootstrap` не має знайти значень.

## 2. Образ у GHCR

CI (`.github/workflows/ci.yml`) на git-тег `vX.Y.Z` публікує образ `ghcr.io/nazarfrazovir/curs_project/web:X.Y.Z` (amd64 і arm64). Пакет має бути **публічним**: GitHub → Packages → `curs_project/web` → Package settings → Change visibility → Public. Тоді кластер тягне образ сам, без `minikube image load`.

```bash
# перевірка, що образ тягнеться без авторизації
docker logout ghcr.io; docker pull ghcr.io/nazarfrazovir/curs_project/web:1.1.1
```

Версія застосунку: `/version` (`{"version":"1.1.1","pod":"..."}`) і підвал сторінки `v1.1.0`.

## 3. Argo CD

```bash
brew install argocd
kubectl create namespace argocd
kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server --timeout=300s

# інтерфейс: у окремій вкладці терміналу (вона має лишатися відкритою), далі https://localhost:8080
kubectl -n argocd port-forward svc/argocd-server 8080:443

# вхід і зміна пароля admin
argocd admin initial-password -n argocd
argocd login localhost:8080 --username admin --insecure
argocd account update-password
kubectl -n argocd delete secret argocd-initial-admin-secret
```

Приватний репозиторій: `argocd repo add https://github.com/NazarFrazovir/Curs_Project.git --username <логін> --password <токен з правом read>`. Токен не комітьте.

## 4. Application і App of Apps

Secret із паролями створюється руками й у Git не потрапляє:

```bash
kubectl create namespace curs-gitops
PW=$(openssl rand -hex 16)
kubectl -n curs-gitops create secret generic curs-project-secrets \
  --from-literal=POSTGRES_PASSWORD="$PW" \
  --from-literal=SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=DATABASE_URL="postgresql://postgres:$PW@curs-project-postgres:5432/wholesale_db"
```

Руками застосовується лише корінь:

```bash
kubectl apply -f bootstrap/root-app.yaml
argocd app list
argocd app get curs-project
kubectl -n curs-gitops get pods
minikube service curs-project-web -n curs-gitops
```

В інтерфейсі: `root` → `curs-project`, дерево об'єктів, статус **Synced / Healthy**.

## 5. Реліз комітом

Версія 1.2.0 має з'явитися в GHCR. Для цього злийте `lab5-gitops` у `main` (PR), потім:

```bash
git checkout main && git pull
git tag v1.2.0 && git push origin v1.2.0      # CI збере й опублікує образ 1.2.0
```

Після зеленого CI змініть тег в Git (це і є реліз):

```bash
# charts/curs-project/values-minikube.yaml:  tag: "1.1.1"  ->  tag: "1.2.0"
git commit -am "release: web 1.2.0" && git push
argocd app get curs-project --refresh          # Argo CD опитує Git раз на 3 хв, refresh пришвидшує
kubectl -n curs-gitops rollout status deploy/curs-project-web
curl -s $(minikube service curs-project-web -n curs-gitops --url)/version
```

Якщо після злиття `targetRevision` у `bootstrap/root-app.yaml` і `argocd-apps/curs-project.yaml` ще `lab5-gitops`, змініть його на `main` і перезастосуйте корінь (`kubectl apply -f bootstrap/root-app.yaml`).

## 6. Дрейф, Health, відкат

**6a. Дрейф.** `selfHeal: false` (поточне значення):

```bash
kubectl -n curs-gitops scale deploy/curs-project-web --replicas=5
argocd app get curs-project            # Sync Status: OutOfSync, реплік 5, ніхто не повертає
```

Увімкніть selfHeal комітом (`argocd-apps/curs-project.yaml`: `selfHeal: true`), корінь підхопить зміну сам:

```bash
git commit -am "enable selfHeal" && git push
kubectl -n curs-gitops scale deploy/curs-project-web --replicas=5
kubectl -n curs-gitops get deploy curs-project-web -w     # за кілька секунд знову 2/2
```

**6b. Synced, але Degraded.** У `values-minikube.yaml` поставте неіснуючий тег:

```bash
# tag: "9.9.9"
git commit -am "bad tag 9.9.9" && git push
argocd app get curs-project --refresh
argocd app get curs-project            # Sync: Synced, Health: Progressing, через ~60 с Degraded
kubectl -n curs-gitops get pods        # новий под ImagePullBackOff, старі ще працюють
```

**6c. Відкат.**

```bash
git revert HEAD --no-edit && git push
git log --oneline -5
argocd app history curs-project
argocd app get curs-project            # знову Synced / Healthy
```

## Що фіксувати для звіту

Скриншоти: Argo CD UI з деревом (Synced/Healthy), OutOfSync після `scale`, selfHeal, Synced+Degraded, історія. Виводи: `argocd app get`, `git log`, `argocd app history`, `/version` до і після релізу.

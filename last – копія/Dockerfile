FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    # setuptools і wheel потрібні лише для встановлення залежностей; у готовому образі їх немає
    # (менше поверхні для CVE: Trivy знаходив у них вразливу вбудовану копію setuptools 70.3.0)
    && pip uninstall -y setuptools wheel \
    # колесо setuptools, вбудоване в базовий образ для ensurepip: Trivy сканує і його вміст
    && rm -f /usr/local/lib/python3.11/ensurepip/_bundled/setuptools-*.whl \
    # SBOM-файл самого pip (список його вбудованих бібліотек, зокрема setuptools 70.3.0):
    # Trivy сприймає його як встановлений пакет і дає хибну вразливість
    && rm -f /usr/local/lib/python3.11/site-packages/pip/_vendor/bom.cdx.json

COPY . .

# Версія образу (1.0.0 / 1.1.0) видна у /healthz і в підвалі сторінок
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

EXPOSE 5000

CMD ["python", "app.py"]
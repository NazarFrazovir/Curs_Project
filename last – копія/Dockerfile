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
    && pip uninstall -y setuptools wheel

COPY . .

# Версія образу (1.0.0 / 1.1.0) видна у /healthz і в підвалі сторінок
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

EXPOSE 5000

CMD ["python", "app.py"]
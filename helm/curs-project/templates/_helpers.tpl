{{/*
Коротке ім'я чарта.
*/}}
{{- define "curs-project.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Повне ім'я об'єктів: будується з імені релізу, тому чарт можна встановити кілька разів.
Обмеження 63 символи — ліміт імен у Kubernetes.
*/}}
{{- define "curs-project.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Імена об'єктів окремих компонентів. Базу скорочуємо, щоб із суфіксом не перевищити 63 символи.
*/}}
{{- define "curs-project.webName" -}}
{{- printf "%s-web" (include "curs-project.fullname" . | trunc 58 | trimSuffix "-") }}
{{- end }}

{{- define "curs-project.dbName" -}}
{{- printf "%s-postgres" (include "curs-project.fullname" . | trunc 53 | trimSuffix "-") }}
{{- end }}

{{- define "curs-project.dbInitName" -}}
{{- printf "%s-db-init" (include "curs-project.fullname" . | trunc 54 | trimSuffix "-") }}
{{- end }}

{{- define "curs-project.dbPvcName" -}}
{{- printf "%s-postgres-data" (include "curs-project.fullname" . | trunc 47 | trimSuffix "-") }}
{{- end }}

{{/*
Назва й версія чарта для мітки helm.sh/chart.
*/}}
{{- define "curs-project.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Мітки, спільні для всіх об'єктів релізу.
*/}}
{{- define "curs-project.labels" -}}
helm.sh/chart: {{ include "curs-project.chart" . }}
{{ include "curs-project.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Мітки для selector (незмінні протягом життя релізу). Компонент додається в самому маніфесті.
*/}}
{{- define "curs-project.selectorLabels" -}}
app.kubernetes.io/name: {{ include "curs-project.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

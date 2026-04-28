{{/*
Expand the name of the chart.
*/}}
{{- define "kubeastra.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
Truncate at 63 chars because some Kubernetes name fields are limited.
*/}}
{{- define "kubeastra.fullname" -}}
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
Create chart label.
*/}}
{{- define "kubeastra.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "kubeastra.labels" -}}
helm.sh/chart: {{ include "kubeastra.chart" . }}
{{ include "kubeastra.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — used in matchLabels and pod template labels.
*/}}
{{- define "kubeastra.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubeastra.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend-specific selector labels.
*/}}
{{- define "kubeastra.backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubeastra.name" . }}-backend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Frontend-specific selector labels.
*/}}
{{- define "kubeastra.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubeastra.name" . }}-frontend
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "kubeastra.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "kubeastra.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Backend service name — used by the frontend to build the API URL.
*/}}
{{- define "kubeastra.backendServiceName" -}}
{{- printf "%s-backend" (include "kubeastra.fullname" .) }}
{{- end }}

{{/*
Frontend API URL — auto-resolved to in-cluster backend service unless overridden.
*/}}
{{- define "kubeastra.frontendApiUrl" -}}
{{- if .Values.frontend.apiUrl }}
{{- .Values.frontend.apiUrl }}
{{- else }}
{{- printf "http://%s:%d" (include "kubeastra.backendServiceName" .) (.Values.backend.service.port | int) }}
{{- end }}
{{- end }}

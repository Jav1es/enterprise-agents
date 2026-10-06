{{/*
公共模板：配置变更触发滚动更新
用法：{{ include "agent.configChecksum" . }}
*/}}
{{- define "agent.configChecksum" -}}
{{ toYaml .Values.app }}
{{- if .Values.telemetry }}
{{ toYaml .Values.telemetry }}
{{- end }}
{{- if .Values.dependencies }}
{{ toYaml .Values.dependencies }}
{{- end }}
{{- end }}
# Planfix Monitoring Exporter

Snapshot-экспортёр задач из Planfix в VictoriaMetrics.

## Файлы
- `app/main.py` — entrypoint
- `app/settings.py` — `.env` и `config.json`
- `app/planfix_client.py` — Planfix REST client
- `app/snapshot_builder.py` — сбор snapshot
- `app/metrics_writer.py` — формирование и отправка метрик
- `app/models.py` — dataclass-модели

## `.env`
```env
PLANFIX_ACCOUNT=example-account
PLANFIX_BEARER_TOKEN=YOUR_TOKEN
VM_URL=https://victoriametrics.example/api/v1/import/prometheus
VM_USER=
VM_PASSWORD=
HTTP_TIMEOUT=30
VERIFY_SSL=true
DISABLE_PROXY=true
POLL_INTERVAL_SECONDS=3600
```

## Запуск
Проверка:
```bash
python -m app.main --once --dry-run --print-json
```

Разовый боевой запуск:
```bash
python -m app.main --once
```

Непрерывный режим:
```bash
python -m app.main
```

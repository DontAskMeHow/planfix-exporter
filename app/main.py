from __future__ import annotations
import argparse
import json
import time
from datetime import datetime, timezone
from typing import Optional
import requests

from .metrics_writer import build_state_payload, build_vm_rows, load_previous_state, save_json, send_to_victoria
from .planfix_client import PlanfixAPIError, PlanfixClient
from .settings import load_settings
from .snapshot_builder import build_snapshot

def run_once(config_path: str, dry_run: bool, print_json: bool) -> int:
    settings = load_settings(config_path)
    client = PlanfixClient(settings)

    try:
        snapshot = build_snapshot(client, settings)
    except requests.RequestException as exc:
        raise SystemExit(f'Ошибка сети при работе с Planfix: {exc}') from exc
    except PlanfixAPIError as exc:
        raise SystemExit(str(exc)) from exc

    save_json(settings.snapshot_file, snapshot)

    previous_state = load_previous_state(settings.state_file)
    prev_signature = previous_state.get('signature')
    changed = snapshot['signature'] != prev_signature

    rows = build_vm_rows(snapshot, previous_state)

    result = {
        'projects': snapshot['projects_count'],
        'tasks_total': snapshot['tasks_total'],
        'rows_generated': len(rows),
        'snapshot_changed': changed,
        'dry_run': bool(dry_run),
        'snapshot_file': str(settings.snapshot_file),
        'state_file': str(settings.state_file),
        'counter_events': snapshot.get('counter_events', {}),
    }

    if print_json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))

    if dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    send_to_victoria(settings, rows)
    save_json(settings.state_file, build_state_payload(snapshot))

    result['sent'] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

def run_forever(config_path: str, print_json: bool) -> int:
    settings = load_settings(config_path)
    interval = settings.poll_interval_seconds
    print(f'[{datetime.now(timezone.utc).isoformat()}] exporter started, interval={interval}s')

    while True:
        try:
            run_once(config_path=config_path, dry_run=False, print_json=print_json)
        except Exception as exc:
            print(f'[{datetime.now(timezone.utc).isoformat()}] run failed: {exc}')
        time.sleep(interval)

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Planfix snapshot exporter for VictoriaMetrics')
    parser.add_argument('--config', default='config.json', help='Путь к config.json')
    parser.add_argument('--dry-run', action='store_true', help='Не отправлять метрики в VictoriaMetrics')
    parser.add_argument('--print-json', action='store_true', help='Печатать snapshot JSON в stdout')
    parser.add_argument('--once', action='store_true', help='Выполнить один проход и завершиться')
    args = parser.parse_args(argv)

    if args.once or args.dry_run:
        return run_once(config_path=args.config, dry_run=args.dry_run, print_json=args.print_json)
    return run_forever(config_path=args.config, print_json=args.print_json)

if __name__ == '__main__':
    raise SystemExit(main())

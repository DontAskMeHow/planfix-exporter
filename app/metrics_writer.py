from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import requests
from .models import Settings

def load_previous_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}

def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

def escape_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _counter_key(project_id: Any, kind: str) -> str:
    return f'{project_id}:{kind}'

def _get_previous_task_index(previous_state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    task_index = previous_state.get('task_index')
    if isinstance(task_index, dict):
        return task_index
    return {}

def _get_previous_counters(previous_state: Dict[str, Any]) -> Dict[str, int]:
    counters = previous_state.get('counters')
    if isinstance(counters, dict):
        result: Dict[str, int] = {}
        for key, value in counters.items():
            try:
                result[str(key)] = int(value)
            except (TypeError, ValueError):
                result[str(key)] = 0
        return result
    return {}

def update_period_counters(snapshot: Dict[str, Any], previous_state: Dict[str, Any] | None = None) -> Dict[str, int]:
    previous_state = previous_state or {}
    previous_tasks = _get_previous_task_index(previous_state)
    previous_counters = _get_previous_counters(previous_state)
    current_tasks = snapshot.get('task_index') or {}

    counters = dict(previous_counters)

    # Первый запуск после обновления — baseline без искусственного всплеска.
    if not previous_tasks:
        snapshot['counters'] = counters
        snapshot['counter_events'] = {'baseline': True, 'created': {}, 'done': {}}
        return counters

    created_events: Dict[str, int] = {}
    done_events: Dict[str, int] = {}

    for task_id, current in current_tasks.items():
        project_id = current.get('project_id')
        if project_id is None:
            continue

        previous = previous_tasks.get(str(task_id))

        if previous is None:
            key = _counter_key(project_id, 'created')
            counters[key] = counters.get(key, 0) + 1
            created_events[str(project_id)] = created_events.get(str(project_id), 0) + 1
            continue

        if previous.get('group') != 'done' and current.get('group') == 'done':
            key = _counter_key(project_id, 'done')
            counters[key] = counters.get(key, 0) + 1
            done_events[str(project_id)] = done_events.get(str(project_id), 0) + 1

    snapshot['counters'] = counters
    snapshot['counter_events'] = {'baseline': False, 'created': created_events, 'done': done_events}
    return counters


def build_vm_rows(snapshot: Dict[str, Any], previous_state: Dict[str, Any] | None = None) -> List[str]:
    ts_ms = int(datetime.fromisoformat(snapshot['generated_at']).timestamp() * 1000)
    rows: List[str] = []
    counters = update_period_counters(snapshot, previous_state)
    for project in snapshot['projects']:
        project_id = escape_label(project['project_id'])
        project_name = escape_label(project['project_name'])

        for status, value in project['counts'].items():
            if value <= 0:
                continue
            status_esc = escape_label(status)
            rows.append(
                f'planfix_project_tasks_by_status{{project_id="{project_id}",project_name="{project_name}",status="{status_esc}"}} {value} {ts_ms}'
            )

        for group in ('active', 'finished'):
            value = int(project['groups'][group])
            if value <= 0:
                continue
            group_esc = escape_label(group)
            rows.append(
                f'planfix_project_tasks_group_count{{project_id="{project_id}",project_name="{project_name}",group="{group_esc}"}} {value} {ts_ms}'
            )

        rows.append(
            f'planfix_project_tasks_active_vs_finished_balance{{project_id="{project_id}",project_name="{project_name}"}} {project["balance"]} {ts_ms}'
        )
        rows.append(
            f'planfix_project_tasks_total{{project_id="{project_id}",project_name="{project_name}"}} {project["tasks_total"]} {ts_ms}'
        )

        if project.get('tasks_unknown_status', 0) > 0:
            rows.append(
                f'planfix_project_tasks_unknown_status_total{{project_id="{project_id}",project_name="{project_name}"}} {project.get("tasks_unknown_status", 0)} {ts_ms}'
            )

    project_meta = {str(project['project_id']): project for project in snapshot.get('projects', [])}

    for key, value in sorted(counters.items()):
        try:
            project_id_raw, kind = key.rsplit(':', 1)
        except ValueError:
            continue

        project = project_meta.get(str(project_id_raw))
        if not project:
            continue

        project_id = escape_label(project['project_id'])
        project_name = escape_label(project['project_name'])

        if kind == 'created':
            rows.append(
                f'planfix_tasks_created_total{{project_id="{project_id}",project_name="{project_name}"}} {int(value)} {ts_ms}'
            )
        elif kind == 'done':
            rows.append(
                f'planfix_tasks_done_total{{project_id="{project_id}",project_name="{project_name}"}} {int(value)} {ts_ms}'
            )

    for employee in snapshot.get('employees', []):
        employee_id = escape_label(employee['employee_id'])
        employee_name = escape_label(employee['employee_name'])

        for group, value in employee.get('groups', {}).items():
            if value <= 0:
                continue
            group_esc = escape_label(group)
            rows.append(
                f'planfix_employee_tasks_group_count{{employee_id="{employee_id}",employee_name="{employee_name}",group="{group_esc}"}} {value} {ts_ms}'
            )

        rows.append(
            f'planfix_employee_tasks_total{{employee_id="{employee_id}",employee_name="{employee_name}"}} {employee["tasks_total"]} {ts_ms}'
        )

    return rows

def send_to_victoria(settings: Settings, rows: List[str]) -> None:
    data = '\n'.join(rows)
    kwargs: Dict[str, Any] = {
        'data': data,
        'headers': {'Content-Type': 'text/plain'},
        'timeout': settings.http_timeout,
        'verify': settings.verify_ssl,
    }
    if settings.vm_user or settings.vm_password:
        kwargs['auth'] = (settings.vm_user, settings.vm_password)

    response = requests.post(settings.vm_url, **kwargs)
    print('VM STATUS:', response.status_code)
    print('VM RESPONSE:', response.text[:300])
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise SystemExit(f'VictoriaMetrics error {response.status_code}: {response.text}') from exc

def build_state_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'version': 2,
        'saved_at': datetime.now(timezone.utc).isoformat(),
        'signature': snapshot['signature'],
        'projects': [
            {
                'project_id': item['project_id'],
                'project_name': item['project_name'],
                'counts': item['counts'],
                'groups': item['groups'],
                'balance': item['balance'],
                'tasks_total': item['tasks_total'],
                'tasks_unknown_status': item.get('tasks_unknown_status', 0),
            }
            for item in snapshot['projects']
        ],
        'employees': [
            {
                'employee_id': item['employee_id'],
                'employee_name': item['employee_name'],
                'groups': item['groups'],
                'tasks_total': item['tasks_total'],
            }
            for item in snapshot.get('employees', [])
        ],
        'task_index': snapshot.get('task_index', {}),
        'counters': snapshot.get('counters', {}),
        'counter_events': snapshot.get('counter_events', {}),
    }

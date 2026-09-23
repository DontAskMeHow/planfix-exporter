from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from .models import Settings
from .planfix_client import PlanfixClient

IDEA_PROJECT_ID = 24564

STATUS_MAP = {
    'Новая': 'new',
    'В работе': 'in_progress',
    'Выполненная': 'done',
    'Завершенная': 'completed',
    'Завершённая': 'completed',
    'Черновик': 'draft',
    'Отмененная': 'cancelled',
    'Отменённая': 'cancelled',
    '1С: Приложения': '1c_apps',
    'Клиентское ПО': 'product_client',
    'Аппаратная часть': 'product_hardware',
    'Серверное ПО': 'product_server',
    'Програмное обеспечение': 'software',
    'Программное обеспечение': 'software',
    'Прошивки': 'firmware',
    'Печатные платы': 'pcb',
    'Оборудование': 'hardware',
    'Конструктив, корпуса': 'mechanics',
    'Конструктив ВА-Т': 'mechanics_va_t',
    'Конструктив ВА-Н': 'mechanics_va_n',
    'Конструктив DKM': 'mechanics_dkm',
}

BASE_STATUS_ORDER = ['new','in_progress','done','completed','draft','cancelled','unknown']
IDEA_STATUS_ORDER = ['1c_apps','product_client','product_hardware','product_server','software','firmware','pcb','hardware','mechanics','mechanics_va_t','mechanics_va_n','mechanics_dkm']

def normalize_status(status_value: Any) -> Tuple[str, str]:
    if isinstance(status_value, dict):
        name = str(status_value.get('name') or status_value.get('title') or '').strip()
    else:
        name = str(status_value or '').strip()
    return STATUS_MAP.get(name, 'unknown'), name or '<без статуса>'

def normalize_status_for_project(project_id: int, status_value: Any) -> Tuple[str, str]:
    code, raw_name = normalize_status(status_value)

    if project_id == IDEA_PROJECT_ID:
        if raw_name in {'Выполненная'}:
            return 'done', raw_name
        if raw_name in {'Завершенная', 'Завершённая'}:
            return 'completed', raw_name
        if raw_name in {'Отмененная', 'Отменённая', 'Черновик'}:
            return 'skip', raw_name
        return 'new', raw_name

    return code, raw_name

def extract_project_name(task: Dict[str, Any], fallback_name: Optional[str], project_id: int) -> str:
    project_info = task.get('project')
    if isinstance(project_info, dict):
        for key in ('name', 'title'):
            value = project_info.get(key)
            if value:
                return str(value).strip()
    return fallback_name or f'Проект {project_id}'

def build_empty_counts(project_id: int) -> Dict[str, int]:
    statuses = BASE_STATUS_ORDER + (IDEA_STATUS_ORDER if project_id == IDEA_PROJECT_ID else [])
    return {status: 0 for status in statuses}

def ordered_nonzero_counts(counts: Dict[str, int], project_id: int) -> Dict[str, int]:
    order = BASE_STATUS_ORDER + (IDEA_STATUS_ORDER if project_id == IDEA_PROJECT_ID else [])
    result: Dict[str, int] = {}
    for status in order:
        value = int(counts.get(status, 0))
        if value > 0:
            result[status] = value
    for status in sorted(counts.keys()):
        if status not in result and int(counts[status]) > 0:
            result[status] = int(counts[status])
    return result


EMPLOYEE_DONE_STATUSES = {'Выполненная', 'Завершенная', 'Завершённая'}

def normalize_employee_task_group(status_value: Any) -> Tuple[str, str]:
    if isinstance(status_value, dict):
        raw_name = str(status_value.get('name') or status_value.get('title') or '').strip()
    else:
        raw_name = str(status_value or '').strip()

    if raw_name in EMPLOYEE_DONE_STATUSES:
        return 'done', raw_name or '<без статуса>'
    return 'in_work', raw_name or '<без статуса>'

def is_direct_assignee(task: Dict[str, Any], employee_id: int) -> bool:
    target = f'user:{employee_id}'
    assignees = task.get('assignees')
    if not isinstance(assignees, dict):
        return False
    users = assignees.get('users') or []
    if not isinstance(users, list):
        return False
    return any(str(user.get('id')) == target for user in users if isinstance(user, dict))

def compute_snapshot_signature(snapshot: Dict[str, Any]) -> str:
    normalized = {
        'projects': [
            {
                'project_id': item['project_id'],
                'project_name': item['project_name'],
                'counts': item['counts'],
                'groups': item['groups'],
                'balance': item['balance'],
                'tasks_total': item['tasks_total'],
            }
            for item in snapshot.get('projects', [])
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
    }
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def build_snapshot(client: PlanfixClient, settings: Settings) -> Dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    projects_snapshot = []
    total_tasks = 0
    task_index: Dict[str, Dict[str, Any]] = {}

    for project in settings.projects:
        counts = build_empty_counts(project.id)
        project_name = project.name or f'Проект {project.id}'
        tasks_total = 0
        tasks_known_status = 0
        tasks_unknown_status = 0
        raw_status_counts: Dict[str, int] = {}

        for task in client.iter_tasks(project.id):
            project_name = extract_project_name(task, project_name if tasks_total > 1 else project.name, project.id)

            code, raw_name = normalize_status_for_project(project.id, task.get('status'))
            raw_status_counts[raw_name] = raw_status_counts.get(raw_name, 0) + 1

            if code == 'skip':
                continue

            tasks_total += 1
            total_tasks += 1
            counts[code] = counts.get(code, 0) + 1

            task_id = task.get('id')
            if task_id is not None:
                task_key = str(task_id)
                task_index[task_key] = {
                    'task_id': int(task_id) if str(task_id).isdigit() else task_id,
                    'project_id': project.id,
                    'project_name': project_name,
                    'status': code,
                    'raw_status': raw_name,
                    'group': 'done' if code in {'done', 'completed'} else 'in_work',
                }

            if code == 'unknown':
                tasks_unknown_status += 1
            else:
                tasks_known_status += 1

        active = counts.get('new', 0) + counts.get('in_progress', 0)
        finished = counts.get('done', 0) + counts.get('completed', 0)

        projects_snapshot.append(
            {
                'project_id': project.id,
                'project_name': project_name,
                'counts': ordered_nonzero_counts(counts, project.id),
                'groups': {'active': active, 'finished': finished},
                'balance': active - finished,
                'tasks_total': tasks_total,
                'tasks_known_status': tasks_known_status,
                'tasks_unknown_status': tasks_unknown_status,
                'raw_status_counts': dict(sorted(raw_status_counts.items(), key=lambda kv: kv[0].lower())),
                'captured_at': generated_at,
            }
        )

    employees_snapshot = []

    for employee in settings.employees:
        employee_name = employee.name or f'Сотрудник {employee.id}'
        groups = {'in_work': 0, 'done': 0}
        raw_status_counts: Dict[str, int] = {}
        tasks_total = 0

        for task in client.iter_employee_tasks(employee.id):
            # Защита на случай, если Planfix вернёт расширенную выборку.
            if not is_direct_assignee(task, employee.id):
                continue

            group, raw_name = normalize_employee_task_group(task.get('status'))
            groups[group] = groups.get(group, 0) + 1
            raw_status_counts[raw_name] = raw_status_counts.get(raw_name, 0) + 1
            tasks_total += 1

            assignees = task.get('assignees')
            if isinstance(assignees, dict):
                for user in assignees.get('users') or []:
                    if isinstance(user, dict) and str(user.get('id')) == f'user:{employee.id}' and user.get('name'):
                        employee_name = str(user.get('name')).strip()

        employees_snapshot.append(
            {
                'employee_id': employee.id,
                'employee_name': employee_name,
                'groups': {key: value for key, value in groups.items() if value > 0},
                'tasks_total': tasks_total,
                'raw_status_counts': dict(sorted(raw_status_counts.items(), key=lambda kv: kv[0].lower())),
                'captured_at': generated_at,
            }
        )

    employees_snapshot.sort(key=lambda item: (str(item['employee_name']).lower(), item['employee_id']))

    projects_snapshot.sort(key=lambda item: (str(item['project_name']).lower(), item['project_id']))
    snapshot = {
        'generated_at': generated_at,
        'projects_count': len(projects_snapshot),
        'tasks_total': total_tasks,
        'projects': projects_snapshot,
        'employees_count': len(employees_snapshot),
        'employees': employees_snapshot,
        'task_index': task_index,
    }
    snapshot['signature'] = compute_snapshot_signature(snapshot)
    return snapshot

from __future__ import annotations
import json
import os
from pathlib import Path
from .models import EmployeeConfig, ProjectConfig, Settings

class ConfigError(SystemExit):
    pass

def load_env_file(env_path: Path = Path('.env')) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

def load_settings(config_path: str = 'config.json') -> Settings:
    load_env_file()
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f'Не найден config.json: {path}')

    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ConfigError(f'Ошибка разбора JSON в {path}: {exc}') from exc

    account = str(raw.get('account') or os.getenv('PLANFIX_ACCOUNT') or '').strip()
    if not account:
        raise ConfigError('Не задан account в config.json и нет PLANFIX_ACCOUNT в .env')

    planfix_token = str(raw.get('token') or os.getenv('PLANFIX_BEARER_TOKEN') or '').strip()
    if not planfix_token:
        raise ConfigError('Не задан PLANFIX_BEARER_TOKEN в .env и нет token в config.json')

    vm_url = str(raw.get('vm_url') or os.getenv('VM_URL') or '').strip()
    if not vm_url:
        raise ConfigError('Не задан VM_URL в .env и нет vm_url в config.json')

    vm_user = str(raw.get('vm_user') or os.getenv('VM_USER') or '').strip()
    vm_password = str(raw.get('vm_password') or os.getenv('VM_PASSWORD') or '').strip()

    try:
        http_timeout = int(raw.get('http_timeout') or os.getenv('HTTP_TIMEOUT') or 30)
    except ValueError as exc:
        raise ConfigError('HTTP_TIMEOUT должен быть целым числом') from exc

    verify_ssl = bool(raw.get('verify_ssl')) if 'verify_ssl' in raw else env_bool('VERIFY_SSL', True)
    disable_proxy = bool(raw.get('disable_proxy')) if 'disable_proxy' in raw else env_bool('DISABLE_PROXY', True)

    try:
        poll_interval_seconds = int(raw.get('poll_interval_seconds') or os.getenv('POLL_INTERVAL_SECONDS') or 3600)
    except ValueError as exc:
        raise ConfigError('POLL_INTERVAL_SECONDS должен быть целым числом') from exc

    raw_projects = raw.get('projects')
    if not isinstance(raw_projects, list) or not raw_projects:
        raise ConfigError('В config.json должен быть непустой массив "projects"')

    projects: list[ProjectConfig] = []
    for item in raw_projects:
        if isinstance(item, dict):
            if 'id' not in item:
                raise ConfigError('Каждый объект в "projects" должен содержать поле "id"')
            projects.append(ProjectConfig(id=int(item['id']), name=str(item.get('name')).strip() if item.get('name') else None))
        else:
            projects.append(ProjectConfig(id=int(item), name=None))

    raw_employees = raw.get('employees') or raw.get('Employee') or raw.get('Employees') or []
    if raw_employees is None:
        raw_employees = []
    if not isinstance(raw_employees, list):
        raise ConfigError('Поле "employees" в config.json должно быть массивом')

    employees: list[EmployeeConfig] = []
    for item in raw_employees:
        if isinstance(item, dict):
            if 'id' not in item:
                raise ConfigError('Каждый объект в "employees" должен содержать поле "id"')
            employees.append(EmployeeConfig(id=int(item['id']), name=str(item.get('name')).strip() if item.get('name') else None))
        else:
            employees.append(EmployeeConfig(id=int(item), name=None))

    page_size = int(raw.get('page_size') or 100)
    state_file = Path(raw.get('state_file') or 'planfix_snapshot_state.json').resolve()
    snapshot_file = Path(raw.get('snapshot_file') or 'planfix_snapshot.json').resolve()

    return Settings(
        account=account,
        planfix_token=planfix_token,
        vm_url=vm_url,
        vm_user=vm_user,
        vm_password=vm_password,
        http_timeout=http_timeout,
        verify_ssl=verify_ssl,
        disable_proxy=disable_proxy,
        poll_interval_seconds=poll_interval_seconds,
        projects=projects,
        employees=employees,
        page_size=page_size,
        state_file=state_file,
        snapshot_file=snapshot_file,
    )

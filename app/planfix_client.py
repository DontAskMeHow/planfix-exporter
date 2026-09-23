from __future__ import annotations
from typing import Any, Dict, Iterable, List
import requests
from .models import Settings

class PlanfixAPIError(RuntimeError):
    pass

class PlanfixClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f'https://{settings.account}.planfix.ru/rest'
        self.session = requests.Session()
        if settings.disable_proxy:
            self.session.trust_env = False
            self.session.proxies = {}
        self.session.headers.update(
            {
                'Authorization': f'Bearer {settings.planfix_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }
        )

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f'{self.base_url}{path}'
        response = self.session.post(
            url,
            json=payload,
            timeout=self.settings.http_timeout,
            verify=self.settings.verify_ssl,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise PlanfixAPIError(f'Planfix API error {response.status_code}: {response.text}') from exc
        try:
            return response.json()
        except ValueError as exc:
            raise PlanfixAPIError(f'Planfix API вернул не-JSON: {response.text}') from exc

    def iter_tasks(self, project_id: int) -> Iterable[Dict[str, Any]]:
        offset = 0
        while True:
            body = {
                'offset': offset,
                'pageSize': self.settings.page_size,
                'filters': [
                    {
                        'type': 5,
                        'operator': 'equal',
                        'value': project_id,
                    }
                ],
                'fields': 'id,name,status,project',
            }
            payload = self._post('/task/list', body)
            tasks = self._extract_tasks(payload)
            if not tasks:
                break
            for task in tasks:
                yield task
            if len(tasks) < self.settings.page_size:
                break
            offset += self.settings.page_size

    def iter_employee_tasks(self, employee_id: int) -> Iterable[Dict[str, Any]]:
        offset = 0
        while True:
            body = {
                'offset': offset,
                'pageSize': self.settings.page_size,
                'filters': [
                    {
                        'type': 97,
                        'operator': 'equal',
                        'value': f'user:{employee_id}',
                    }
                ],
                'fields': 'id,name,status,assignees,project',
            }
            payload = self._post('/task/list', body)
            tasks = self._extract_tasks(payload)
            if not tasks:
                break
            for task in tasks:
                yield task
            if len(tasks) < self.settings.page_size:
                break
            offset += self.settings.page_size

    @staticmethod
    def _extract_tasks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ('tasks', 'data', 'items', 'list', 'result'):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        if isinstance(payload, list):
            return payload
        return []

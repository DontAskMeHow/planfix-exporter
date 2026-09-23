from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class ProjectConfig:
    id: int
    name: Optional[str] = None

@dataclass
class EmployeeConfig:
    id: int
    name: Optional[str] = None

@dataclass
class Settings:
    account: str
    planfix_token: str
    vm_url: str
    vm_user: str
    vm_password: str
    http_timeout: int
    verify_ssl: bool
    disable_proxy: bool
    poll_interval_seconds: int
    projects: list[ProjectConfig]
    employees: list[EmployeeConfig]
    page_size: int
    state_file: Path
    snapshot_file: Path

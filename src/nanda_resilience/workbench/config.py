from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal

from dotenv import dotenv_values
from pydantic import SecretStr


@dataclass(frozen=True)
class Deployment:
    id: str
    endpoint: str
    deployment: str
    key: SecretStr
    priority: int
    provider: Literal["azure", "coco"] = "azure"
    executable: str | None = None

    @property
    def resource(self) -> str:
        if self.provider == "coco":
            return "copilot-via-coco"
        return urlsplit(self.endpoint).hostname or ""

    def public(self) -> dict:
        return {"id": self.id, "resource": self.resource,
                "deployment": self.deployment, "priority": self.priority,
                "provider": self.provider}


def load_deployments(env_file: Path, environ: dict | None = None) -> tuple[list[Deployment], list[str]]:
    values = {**dotenv_values(env_file), **(os.environ if environ is None else environ)}
    provider = str(values.get("WORKBENCH_PROVIDER") or "azure").strip().lower()
    if provider == "coco":
        model = str(values.get("COCO_MODEL") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,160}", model):
            return [], ["Set COCO_MODEL to an exact model ID from coco models."]
        executable = str(values.get("COCO_EXECUTABLE") or "").strip()
        if not executable:
            executable = shutil.which("coco") or ""
            if not executable and values.get("LOCALAPPDATA"):
                executable = str(Path(values["LOCALAPPDATA"]) / "Programs" / "coco" / "coco.exe")
        if not executable or not Path(executable).is_file():
            return [], ["coco was not found. Set COCO_EXECUTABLE to its installed executable path."]
        return [Deployment("primary", "", model, SecretStr(""), 1, "coco",
                           str(Path(executable).resolve()))], []
    if provider != "azure":
        return [], ["WORKBENCH_PROVIDER must be azure or coco."]
    deployments, problems = [], []
    for alias, prefix, priority in (
        ("primary", "AZURE_OPENAI_", 1),
        ("backup", "AZURE_OPENAI_BACKUP_", 2),
    ):
        fields = {name: str(values.get(prefix + name) or "").strip()
                  for name in ("ENDPOINT", "DEPLOYMENT", "API_KEY")}
        if not any(fields.values()):
            continue
        missing = [prefix + name for name, value in fields.items() if not value]
        if missing:
            problems.append(f"{alias}: missing {', '.join(missing)}")
            continue
        endpoint = fields["ENDPOINT"].rstrip("/")
        if endpoint.endswith("/openai/v1"):
            endpoint = endpoint[:-10]
        try:
            parsed = urlsplit(endpoint)
            port = parsed.port
        except ValueError:
            problems.append(f"{alias}: invalid endpoint URL or port")
            continue
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or port not in (None, 443) or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment
                or not (parsed.hostname or "").endswith((
                    ".openai.azure.com", ".services.ai.azure.com",
                    ".cognitiveservices.azure.com"))):
            problems.append(f"{alias}: use the HTTPS Azure resource endpoint, not a project URL")
            continue
        deployments.append(Deployment(
            alias, endpoint, fields["DEPLOYMENT"], SecretStr(fields["API_KEY"]), priority))
    return deployments, problems

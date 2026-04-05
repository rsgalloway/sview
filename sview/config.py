#!/usr/bin/env python3
#
# Copyright (c) 2026, Ryan Galloway (ryan@rsgalloway.com)
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#  - Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
#  - Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
#  - Neither the name of the software nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# -----------------------------------------------------------------------------

"""
Contains configuration management for sview, including loading and saving user preferences.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, metadata
import json
import shlex
from dataclasses import dataclass
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "sview"
CONFIG_PATH = CONFIG_DIR / "config.json"
UI_STATE_PATH = CONFIG_DIR / "ui_state.json"
DEFAULT_REPOSITORY_URL = "https://github.com/rsgalloway/sview"


@dataclass
class HandlerConfig:
    mode: str
    command: str = ""


@dataclass
class ScanWorkerConfig:
    nice_increment: int = 15
    memory_limit_mb: int | None = None
    timeout_seconds: int | None = 30


@dataclass
class AppConfig:
    file_handler: HandlerConfig
    sequence_handler: HandlerConfig
    scan_worker: ScanWorkerConfig

    @classmethod
    def default(cls) -> "AppConfig":
        return cls(
            file_handler=HandlerConfig(mode="system"),
            sequence_handler=HandlerConfig(mode="expand"),
            scan_worker=ScanWorkerConfig(),
        )

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_PATH.exists():
            config = cls.default()
            try:
                config.save()
            except OSError:
                pass
            return config

        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = cls.default()
            try:
                config.save()
            except OSError:
                pass
            return config

        handlers = data.get("handlers", {})
        scanner = data.get("scanner", {})
        worker = scanner.get("worker", {})
        memory_limit_mb = cls._load_memory_limit(worker)
        needs_save = (
            "scanner" not in data
            or "worker" not in scanner
            or "nice_increment" not in worker
            or "memory_limit_mb" not in worker
            or "timeout_seconds" not in worker
        )
        file_handler = handlers.get("file", {})
        sequence_handler = handlers.get("sequence", {})
        config = cls(
            file_handler=HandlerConfig(
                mode=file_handler.get("mode", "system"),
                command=file_handler.get("command", ""),
            ),
            sequence_handler=HandlerConfig(
                mode=sequence_handler.get("mode", "expand"),
                command=sequence_handler.get("command", ""),
            ),
            scan_worker=ScanWorkerConfig(
                nice_increment=int(worker.get("nice_increment", 15)),
                memory_limit_mb=memory_limit_mb,
                timeout_seconds=(
                    int(worker["timeout_seconds"])
                    if "timeout_seconds" in worker
                    and worker.get("timeout_seconds") is not None
                    else (None if "timeout_seconds" in worker else 30)
                ),
            ),
        )
        if needs_save:
            try:
                config.save()
            except OSError:
                pass
        return config

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "handlers": {
                "file": {
                    "mode": self.file_handler.mode,
                    "command": self.file_handler.command,
                },
                "sequence": {
                    "mode": self.sequence_handler.mode,
                    "command": self.sequence_handler.command,
                },
            },
            "scanner": {
                "worker": {
                    "nice_increment": self.scan_worker.nice_increment,
                    "memory_limit_mb": self.scan_worker.memory_limit_mb,
                    "timeout_seconds": self.scan_worker.timeout_seconds,
                }
            },
        }
        CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _load_memory_limit(worker: dict[str, object]) -> int | None:
        if "memory_limit_mb" not in worker:
            return None

        value = worker.get("memory_limit_mb")
        if value is None:
            return None

        memory_limit_mb = int(value)
        # Treat the old 0.1.2 default as "unset" because RLIMIT_AS proved too blunt.
        if memory_limit_mb == 2048:
            return None
        return memory_limit_mb


def build_command(command_template: str, path: str) -> list[str]:
    return shlex.split(command_template.format(path=path))


def get_repository_url() -> str:
    try:
        project_metadata = metadata("sview")
    except PackageNotFoundError:
        return DEFAULT_REPOSITORY_URL

    for key, value in project_metadata.items():
        if key != "Project-URL":
            continue
        label, _, url = value.partition(",")
        if label.strip().lower() == "repository" and url.strip():
            return url.strip()

    return DEFAULT_REPOSITORY_URL


def load_ui_state() -> dict[str, object]:
    if not UI_STATE_PATH.exists():
        return {}
    try:
        data = json.loads(UI_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ui_state(state: dict[str, object]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    UI_STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

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
DEFAULT_REPOSITORY_URL = "https://github.com/rsgalloway/sview"


@dataclass
class HandlerConfig:
    mode: str
    command: str = ""


@dataclass
class AppConfig:
    file_handler: HandlerConfig
    sequence_handler: HandlerConfig

    @classmethod
    def default(cls) -> "AppConfig":
        return cls(
            file_handler=HandlerConfig(mode="system"),
            sequence_handler=HandlerConfig(mode="expand"),
        )

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_PATH.exists():
            config = cls.default()
            config.save()
            return config

        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = cls.default()
            config.save()
            return config

        handlers = data.get("handlers", {})
        file_handler = handlers.get("file", {})
        sequence_handler = handlers.get("sequence", {})
        return cls(
            file_handler=HandlerConfig(
                mode=file_handler.get("mode", "system"),
                command=file_handler.get("command", ""),
            ),
            sequence_handler=HandlerConfig(
                mode=sequence_handler.get("mode", "expand"),
                command=sequence_handler.get("command", ""),
            ),
        )

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
            }
        }
        CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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

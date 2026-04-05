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
Contains data models for representing items in the file browser and user configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ItemType(str, Enum):
    DIRECTORY = "directory"
    SEQUENCE = "sequence"
    FILE = "file"


@dataclass
class BrowserItem:
    path: str
    item_type: ItemType
    name: str
    display_name: str
    frame_range: str | None
    pad: str | None
    count: int
    missing: list[int] | None
    size_bytes: int
    modified_time: float
    child_paths: list[str] | None = None

    @property
    def missing_count(self) -> int:
        return len(self.missing or [])

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "item_type": self.item_type.value,
            "name": self.name,
            "display_name": self.display_name,
            "frame_range": self.frame_range,
            "pad": self.pad,
            "count": self.count,
            "missing": list(self.missing) if self.missing is not None else None,
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time,
            "child_paths": list(self.child_paths)
            if self.child_paths is not None
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BrowserItem:
        return cls(
            path=str(data["path"]),
            item_type=ItemType(str(data["item_type"])),
            name=str(data["name"]),
            display_name=str(data["display_name"]),
            frame_range=str(data["frame_range"])
            if data["frame_range"] is not None
            else None,
            pad=str(data["pad"]) if data["pad"] is not None else None,
            count=int(data["count"]),
            missing=[int(value) for value in data["missing"]]
            if data["missing"] is not None
            else None,
            size_bytes=int(data["size_bytes"]),
            modified_time=float(data["modified_time"]),
            child_paths=[str(value) for value in data["child_paths"]]
            if data["child_paths"] is not None
            else None,
        )

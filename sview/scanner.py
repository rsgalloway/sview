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
Contains the DirectoryScanner class for scanning directories and identifying sequences.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable

from sview.model import BrowserItem, ItemType

try:
    import pyseq  # type: ignore
except ImportError:  # pragma: no cover - dependency error path
    pyseq = None


class ScanCancelled(Exception):
    """Raised when a directory scan is cancelled."""


@dataclass
class ScanResult:
    path: Path
    grouped_items: list[BrowserItem]
    raw_items: list[BrowserItem]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "grouped_items": [item.to_dict() for item in self.grouped_items],
            "raw_items": [item.to_dict() for item in self.raw_items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ScanResult:
        grouped_items = [BrowserItem.from_dict(item) for item in data["grouped_items"]]
        raw_items = [BrowserItem.from_dict(item) for item in data["raw_items"]]
        return cls(
            path=Path(str(data["path"])),
            grouped_items=grouped_items,
            raw_items=raw_items,
        )


def ensure_pyseq_available() -> None:
    if pyseq is None:
        raise RuntimeError("sview requires pyseq to be installed.")


class DirectoryScanner:
    """Sequence-aware scanner backed entirely by pyseq."""

    def scan(
        self,
        path: str | Path,
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> ScanResult:
        ensure_pyseq_available()
        directory = Path(path).expanduser()
        if not directory.is_absolute():
            directory = Path.cwd() / directory
        raw_items = self._build_raw_items(
            directory,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        )
        grouped_items = self._build_grouped_items(
            directory,
            raw_items,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        )
        return ScanResult(
            path=directory, grouped_items=grouped_items, raw_items=raw_items
        )

    def _build_raw_items(
        self,
        directory: Path,
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[BrowserItem]:
        entries: list[os.DirEntry[str]] = []
        with os.scandir(directory) as iterator:
            for index, entry in enumerate(iterator, start=1):
                self._raise_if_cancelled(cancel_check)
                if progress_callback is not None and index % 250 == 0:
                    progress_callback(f"Scanning {directory} ({index} entries)...")
                if entry.name in {".", ".."}:
                    continue
                entries.append(entry)

        entries.sort(key=lambda candidate: candidate.name.lower())
        items: list[BrowserItem] = []

        for entry in entries:
            self._raise_if_cancelled(cancel_check)
            try:
                is_directory = entry.is_dir()
            except OSError:
                continue
            items.append(
                BrowserItem(
                    path=entry.path,
                    item_type=ItemType.DIRECTORY if is_directory else ItemType.FILE,
                    name=entry.name,
                    display_name=entry.name,
                    frame_range=None,
                    pad=None,
                    count=0 if is_directory else 1,
                    missing=None,
                    size_bytes=0,
                    modified_time=0.0,
                    child_paths=None,
                )
            )

        return items

    def _build_grouped_items(
        self,
        directory: Path,
        raw_items: list[BrowserItem],
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[BrowserItem]:
        self._raise_if_cancelled(cancel_check)
        if progress_callback is not None:
            progress_callback(f"Grouping sequences in {directory}...")

        directories = [
            item for item in raw_items if item.item_type is ItemType.DIRECTORY
        ]
        file_lookup = {
            item.path: item for item in raw_items if item.item_type is ItemType.FILE
        }
        consumed_paths: set[str] = set()
        grouped: list[BrowserItem] = list(directories)

        sequences = pyseq.get_sequences(str(directory))
        for sequence in sequences:
            self._raise_if_cancelled(cancel_check)
            members = list(sequence)
            if len(members) < 2:
                continue

            child_paths = [str(member.path) for member in members]
            consumed_paths.update(child_paths)
            start_frame = getattr(members[0], "frame", None)
            end_frame = getattr(members[-1], "frame", None)
            if start_frame is not None and end_frame is not None:
                start_frame = int(start_frame)
                end_frame = int(end_frame)
                frame_range = (
                    str(start_frame)
                    if start_frame == end_frame
                    else f"{start_frame}-{end_frame}"
                )
            else:
                frame_range = None
            pad_width = len(getattr(members[0], "digits", [""])[0]) if members else 0
            pad_value = f"%0{pad_width}d" if pad_width else "%d"
            head = members[0].head
            tail = members[0].tail
            grouped.append(
                BrowserItem(
                    path=str(directory / f"{head}{pad_value}{tail}"),
                    item_type=ItemType.SEQUENCE,
                    name=f"{head}{pad_value}{tail}",
                    display_name=f"{head}{pad_value}{tail}",
                    frame_range=frame_range,
                    pad=pad_value,
                    count=len(sequence),
                    missing=None,
                    size_bytes=0,
                    modified_time=0.0,
                    child_paths=child_paths,
                )
            )

        for path, item in file_lookup.items():
            if path in consumed_paths:
                continue
            grouped.append(item)

        return sorted(
            grouped,
            key=lambda item: (
                item.item_type != ItemType.DIRECTORY,
                item.display_name.lower(),
            ),
        )

    @staticmethod
    def _raise_if_cancelled(cancel_check: Callable[[], bool] | None) -> None:
        if cancel_check is not None and cancel_check():
            raise ScanCancelled()

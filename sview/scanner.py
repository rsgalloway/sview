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
from pathlib import Path
import re
from typing import Callable, NamedTuple

from sview.model import BrowserItem, ItemType

try:
    import pyseq  # type: ignore
except ImportError:  # pragma: no cover - optional at development time
    pyseq = None


FRAME_PATTERN = re.compile(r"^(?P<prefix>.*?)(?P<frame>\d+)(?P<suffix>\.[^.]+)$")
PYSEQ_MAX_FILES = 2000


class ScanCancelled(Exception):
    """Raised when a directory scan is cancelled."""


class ParsedFrameFile(NamedTuple):
    path: Path
    prefix: str
    frame: int
    pad: int
    suffix: str
    size_bytes: int
    modified_time: float


@dataclass
class ScanResult:
    path: Path
    grouped_items: list[BrowserItem]
    raw_items: list[BrowserItem]


class DirectoryScanner:
    """Sequence-aware scanner placeholder.

    v1 returns directories and files directly. Sequence grouping can be layered
    into `_build_items` later without changing the UI/controller contract.
    """

    def scan(
        self,
        path: str | Path,
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> ScanResult:
        directory = Path(path).expanduser()
        if not directory.is_absolute():
            directory = Path.cwd() / directory
        raw_items = self._build_raw_items(
            directory, cancel_check=cancel_check, progress_callback=progress_callback
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
        items: list[BrowserItem] = []

        for index, entry in enumerate(
            sorted(directory.iterdir(), key=lambda candidate: candidate.name.lower()),
            start=1,
        ):
            self._raise_if_cancelled(cancel_check)
            if progress_callback is not None and index % 250 == 0:
                progress_callback(f"Scanning {directory} ({index} entries)...")
            try:
                stat = entry.stat()
            except OSError:
                continue

            if entry.is_dir():
                items.append(
                    BrowserItem(
                        path=str(entry),
                        item_type=ItemType.DIRECTORY,
                        name=entry.name,
                        display_name=entry.name,
                        frame_range=None,
                        pad=None,
                        count=0,
                        missing=None,
                        size_bytes=0,
                        modified_time=stat.st_mtime,
                        child_paths=None,
                    )
                )
                continue

            items.append(
                BrowserItem(
                    path=str(entry),
                    item_type=ItemType.FILE,
                    name=entry.name,
                    display_name=entry.name,
                    frame_range=None,
                    pad=None,
                    count=1,
                    missing=None,
                    size_bytes=stat.st_size,
                    modified_time=stat.st_mtime,
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
        file_items = [item for item in raw_items if item.item_type is ItemType.FILE]
        if (
            pyseq is not None
            and len(raw_items) <= PYSEQ_MAX_FILES
            and self._likely_contains_sequences(file_items)
        ):
            grouped = self._build_grouped_items_with_pyseq(
                directory,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
            )
            if grouped is not None:
                return grouped

        directories = [
            item for item in raw_items if item.item_type is ItemType.DIRECTORY
        ]
        parsed_files = self._parse_frame_files(
            file_items, cancel_check=cancel_check, progress_callback=progress_callback
        )

        grouped: list[BrowserItem] = list(directories)
        consumed_paths: set[str] = set()

        for sequence_items in parsed_files.values():
            if len(sequence_items) < 2:
                continue

            grouped.append(self._sequence_item(sequence_items))
            consumed_paths.update(str(item.path) for item in sequence_items)

        for item in file_items:
            if item.path in consumed_paths:
                continue
            grouped.append(item)

        return sorted(
            grouped,
            key=lambda item: (
                item.item_type != ItemType.DIRECTORY,
                item.display_name.lower(),
            ),
        )

    def _build_grouped_items_with_pyseq(
        self,
        directory: Path,
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[BrowserItem] | None:
        self._raise_if_cancelled(cancel_check)
        if progress_callback is not None:
            progress_callback(f"Grouping sequences in {directory}...")
        try:
            sequences = pyseq.get_sequences(str(directory))
        except Exception:
            return None

        items: list[BrowserItem] = []
        consumed: set[str] = set()

        for entry in sorted(
            directory.iterdir(), key=lambda candidate: candidate.name.lower()
        ):
            try:
                stat = entry.stat()
            except OSError:
                continue

            if entry.is_dir():
                items.append(
                    BrowserItem(
                        path=str(entry),
                        item_type=ItemType.DIRECTORY,
                        name=entry.name,
                        display_name=entry.name,
                        frame_range=None,
                        pad=None,
                        count=0,
                        missing=None,
                        size_bytes=0,
                        modified_time=stat.st_mtime,
                        child_paths=None,
                    )
                )

        for sequence in sequences:
            self._raise_if_cancelled(cancel_check)
            try:
                members = [Path(item.path) for item in sequence]
            except (AttributeError, TypeError):
                continue

            if len(members) < 2:
                continue

            parsed_members: list[ParsedFrameFile] = []
            for member in members:
                item = self._parse_frame_path(member)
                if item is None:
                    parsed_members = []
                    break
                consumed.add(str(member))
                parsed_members.append(item)

            if parsed_members:
                items.append(self._sequence_item(parsed_members))

        for entry in sorted(
            directory.iterdir(), key=lambda candidate: candidate.name.lower()
        ):
            entry_path = str(entry)
            if entry.is_dir() or entry_path in consumed:
                continue

            try:
                stat = entry.stat()
            except OSError:
                continue

            items.append(
                BrowserItem(
                    path=entry_path,
                    item_type=ItemType.FILE,
                    name=entry.name,
                    display_name=entry.name,
                    frame_range=None,
                    pad=None,
                    count=1,
                    missing=None,
                    size_bytes=stat.st_size,
                    modified_time=stat.st_mtime,
                    child_paths=None,
                )
            )

        return sorted(
            items,
            key=lambda item: (
                item.item_type != ItemType.DIRECTORY,
                item.display_name.lower(),
            ),
        )

    def _parse_frame_files(
        self,
        file_items: list[BrowserItem],
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[tuple[str, str, int], list[ParsedFrameFile]]:
        grouped: dict[tuple[str, str, int], list[ParsedFrameFile]] = {}
        for index, item in enumerate(file_items, start=1):
            self._raise_if_cancelled(cancel_check)
            if progress_callback is not None and index % 250 == 0:
                progress_callback(
                    f"Analyzing frame candidates ({index}/{len(file_items)})..."
                )
            parsed = self._parse_frame_path(Path(item.path))
            if parsed is None:
                continue
            key = (parsed.prefix, parsed.suffix, parsed.pad)
            grouped.setdefault(key, []).append(parsed)
        return grouped

    def _likely_contains_sequences(self, file_items: list[BrowserItem]) -> bool:
        frame_like = 0
        for item in file_items[:500]:
            if FRAME_PATTERN.match(Path(item.path).name):
                frame_like += 1
                if frame_like >= 2:
                    return True
        return False

    def _parse_frame_path(self, path: Path) -> ParsedFrameFile | None:
        try:
            stat = path.stat()
        except OSError:
            return None

        match = FRAME_PATTERN.match(path.name)
        if match is None:
            return None

        frame_text = match.group("frame")
        return ParsedFrameFile(
            path=path,
            prefix=match.group("prefix"),
            frame=int(frame_text),
            pad=len(frame_text),
            suffix=match.group("suffix"),
            size_bytes=stat.st_size,
            modified_time=stat.st_mtime,
        )

    def _sequence_item(self, items: list[ParsedFrameFile]) -> BrowserItem:
        ordered = sorted(items, key=lambda item: item.frame)
        first = ordered[0]
        frames = [item.frame for item in ordered]
        missing = self._find_missing_frames(frames)
        display_name = f"{first.prefix}%0{first.pad}d{first.suffix}"
        frame_range = self._format_ranges(frames)

        return BrowserItem(
            path=str(first.path.parent / display_name),
            item_type=ItemType.SEQUENCE,
            name=display_name,
            display_name=display_name,
            frame_range=frame_range,
            pad=f"%0{first.pad}d",
            count=len(frames),
            missing=missing,
            size_bytes=sum(item.size_bytes for item in ordered),
            modified_time=max(item.modified_time for item in ordered),
            child_paths=[str(item.path) for item in ordered],
        )

    @staticmethod
    def _find_missing_frames(frames: list[int]) -> list[int]:
        if len(frames) < 2:
            return []

        expected = set(range(frames[0], frames[-1] + 1))
        return sorted(expected.difference(frames))

    @classmethod
    def _format_ranges(cls, frames: list[int]) -> str:
        if not frames:
            return ""

        ranges: list[str] = []
        start = end = frames[0]

        for frame in frames[1:]:
            if frame == end + 1:
                end = frame
                continue
            ranges.append(cls._format_range(start, end))
            start = end = frame

        ranges.append(cls._format_range(start, end))
        return ", ".join(ranges)

    @staticmethod
    def _format_range(start: int, end: int) -> str:
        if start == end:
            return str(start)
        return f"{start}-{end}"

    @staticmethod
    def _raise_if_cancelled(cancel_check: Callable[[], bool] | None) -> None:
        if cancel_check is not None and cancel_check():
            raise ScanCancelled()

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
Contains the BrowserController class, which serves as a thin service layer between
the UI and the Directory Scanner. It manages the current state of the browser,
including the current path, items, and view mode.
"""

from __future__ import annotations

from pathlib import Path

from sview.model import BrowserItem, ItemType
from sview.scanner import DirectoryScanner, ScanResult


class BrowserController:
    """Thin service layer between the UI and scanner."""

    def __init__(self, scanner: DirectoryScanner | None = None) -> None:
        self._scanner = scanner or DirectoryScanner()
        self._current_path = Path.home()
        self._current_items: list[BrowserItem] = []
        self._raw_items: list[BrowserItem] = []
        self._grouped_items: list[BrowserItem] = []
        self._sequence_metadata_cache: dict[str, dict[str, object]] = {}
        self._grouped_view = True
        self._expanded_sequence: BrowserItem | None = None

    @property
    def current_path(self) -> Path:
        return self._current_path

    @property
    def current_items(self) -> list[BrowserItem]:
        return list(self._current_items)

    @property
    def grouped_view(self) -> bool:
        return self._grouped_view

    @property
    def expanded_sequence(self) -> BrowserItem | None:
        return self._expanded_sequence

    def set_grouped_view(self, enabled: bool) -> None:
        self._grouped_view = enabled
        self._expanded_sequence = None
        self._refresh_current_items()

    def expand_sequence(self, item: BrowserItem) -> list[BrowserItem]:
        if item.item_type is not ItemType.SEQUENCE or not item.child_paths:
            return self.current_items

        child_paths = set(item.child_paths)
        self._expanded_sequence = item
        self._current_items = [
            raw_item for raw_item in self._raw_items if raw_item.path in child_paths
        ]
        return self.current_items

    def collapse_sequence(self) -> list[BrowserItem]:
        self._expanded_sequence = None
        self._refresh_current_items()
        return self.current_items

    def load_path(self, path: str | Path) -> list[BrowserItem]:
        result = self.scan_path(path)
        return self.apply_scan_result(result)

    def scan_path(self, path: str | Path, **scan_kwargs) -> ScanResult:
        return self._scanner.scan(path, **scan_kwargs)

    def apply_scan_result(self, result: ScanResult) -> list[BrowserItem]:
        self._current_path = result.path
        self._grouped_items = result.grouped_items
        self._raw_items = result.raw_items
        self._apply_cached_sequence_metadata()
        self._expanded_sequence = None
        self._refresh_current_items()
        return self.current_items

    def update_sequence_metadata(
        self,
        item_path: str,
        size_bytes: int | None = None,
        modified_time: float | None = None,
        missing: list[int] | None = None,
    ) -> BrowserItem | None:
        cache_entry = self._sequence_metadata_cache.setdefault(item_path, {})
        if size_bytes is not None:
            cache_entry["size_bytes"] = size_bytes
        if modified_time is not None:
            cache_entry["modified_time"] = modified_time
        if missing is not None:
            cache_entry["missing"] = list(missing)
        for item in self._grouped_items:
            if item.path != item_path:
                continue
            if size_bytes is not None:
                item.size_bytes = size_bytes
            if modified_time is not None:
                item.modified_time = modified_time
            if missing is not None:
                item.missing = list(missing)
            return item
        return None

    def _refresh_current_items(self) -> None:
        self._current_items = (
            self._grouped_items if self._grouped_view else self._raw_items
        )

    def _apply_cached_sequence_metadata(self) -> None:
        for item in self._grouped_items:
            if item.item_type is not ItemType.SEQUENCE:
                continue
            cached = self._sequence_metadata_cache.get(item.path)
            if not cached:
                continue
            if "size_bytes" in cached:
                item.size_bytes = int(cached["size_bytes"])
            if "modified_time" in cached:
                item.modified_time = float(cached["modified_time"])
            if "missing" in cached:
                item.missing = [int(frame) for frame in cached["missing"]]

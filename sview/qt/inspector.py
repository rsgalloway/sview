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
Contains the InspectorPanel widget for displaying details about a selected item.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from sview.model import BrowserItem, ItemType


class InspectorPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._title = QLabel("Properties")
        self._subtitle = QLabel("Select an item to inspect")
        self._current_item: BrowserItem | None = None

        self._type_value = QLabel("-")
        self._range_value = QLabel("-")
        self._count_value = QLabel("-")
        self._missing_value = QLabel("-")
        self._padding_value = QLabel("-")
        self._size_value = QLabel("-")
        self._modified_value = QLabel("-")
        self._path_value = QLabel("-")
        self._path_value.setWordWrap(True)

        self.copy_path_button = QPushButton("Copy Path")
        self.copy_pattern_button = QPushButton("Copy Pattern")
        self.expand_button = QPushButton("Expand Sequence")
        self.close_button = QPushButton()
        self.close_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )
        self.close_button.setToolTip("Close inspector")
        self.close_button.setFixedWidth(24)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._title.setObjectName("inspectorTitle")
        self._subtitle.setObjectName("inspectorSubtitle")

        header_row = QHBoxLayout()
        header_row.addWidget(self._title)
        header_row.addStretch(1)
        header_row.addWidget(self.close_button)
        layout.addLayout(header_row)
        layout.addWidget(self._subtitle)

        form = QFormLayout()
        form.setVerticalSpacing(4)
        form.setHorizontalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.addRow("Type", self._type_value)
        form.addRow("Frames", self._range_value)
        form.addRow("Count", self._count_value)
        form.addRow("Missing", self._missing_value)
        form.addRow("Padding", self._padding_value)
        form.addRow("Size", self._size_value)
        form.addRow("Modified", self._modified_value)
        form.addRow("Path", self._path_value)
        layout.addLayout(form)
        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addWidget(self.copy_path_button)
        button_row.addWidget(self.copy_pattern_button)
        layout.addLayout(button_row)
        layout.addWidget(self.expand_button)
        self.clear_details()

    def clear_details(self) -> None:
        self._title.setText("Properties")
        self._subtitle.setText("Select an item to inspect")
        self._current_item = None
        for label in (
            self._type_value,
            self._range_value,
            self._count_value,
            self._missing_value,
            self._padding_value,
            self._size_value,
            self._modified_value,
            self._path_value,
        ):
            label.setText("-")
        self.copy_path_button.setEnabled(False)
        self.copy_pattern_button.setEnabled(False)
        self.expand_button.setEnabled(False)
        self.expand_button.setText("Expand Sequence")

    def set_item(self, item: BrowserItem) -> None:
        self._current_item = item
        self._title.setText(item.display_name)
        self._subtitle.setText(self._subtitle_text(item))
        self._type_value.setText(self._type_text(item))
        self._range_value.setText(item.frame_range or "-")
        self._count_value.setText(str(item.count) if item.count else "-")
        self._missing_value.setText(
            ", ".join(str(frame) for frame in item.missing) if item.missing else "-"
        )
        self._padding_value.setText(item.pad or "-")
        self._size_value.setText(self._format_size(item.size_bytes))
        self._modified_value.setText(self._format_modified(item.modified_time))
        self._path_value.setText(str(Path(item.path)))

        self.copy_path_button.setEnabled(True)
        self.copy_pattern_button.setEnabled(item.item_type is ItemType.SEQUENCE)
        self.expand_button.setEnabled(item.item_type is ItemType.SEQUENCE)
        self.expand_button.setText(
            "Expand Sequence"
            if item.item_type is ItemType.SEQUENCE
            else "Expand Sequence"
        )

    @property
    def current_item(self) -> BrowserItem | None:
        return self._current_item

    @staticmethod
    def _type_text(item: BrowserItem) -> str:
        if item.item_type is ItemType.SEQUENCE:
            return "Image Sequence"
        if item.item_type is ItemType.DIRECTORY:
            return "Folder"
        return "File"

    @staticmethod
    def _subtitle_text(item: BrowserItem) -> str:
        if item.item_type is ItemType.SEQUENCE:
            return "Sequence summary"
        if item.item_type is ItemType.DIRECTORY:
            return "Directory details"
        return "File details"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "-"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        unit = units[0]
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                break
            size /= 1024.0
        return f"{size:.1f} {unit}"

    @staticmethod
    def _format_modified(timestamp: float) -> str:
        from datetime import datetime

        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

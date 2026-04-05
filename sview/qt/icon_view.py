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
Contains an icon-based center-pane browser for sview.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sview.model import BrowserItem, ItemType
from sview.qt.icons import browser_item_icon


class ContentsIconView(QListWidget):
    context_requested = Signal(object, object)
    filter_text_typed = Signal(str)
    filter_backspace_requested = Signal()
    filter_clear_requested = Signal()
    CARD_WIDTH = 270
    CARD_HEIGHT = 88

    def __init__(self) -> None:
        super().__init__()
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWrapping(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSpacing(12)
        self.setIconSize(QSize(52, 52))
        self.setGridSize(QSize(self.CARD_WIDTH, self.CARD_HEIGHT))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context_request)

    def set_items(self, items: list[BrowserItem]) -> None:
        self.clear()
        for item in items:
            list_item = QListWidgetItem()
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            list_item.setSizeHint(QSize(self.CARD_WIDTH - 12, self.CARD_HEIGHT - 10))
            self.addItem(list_item)
            self.setItemWidget(list_item, self._build_card(item))

    def current_browser_item(self) -> BrowserItem | None:
        current = self.currentItem()
        if current is None:
            return None
        return current.data(Qt.ItemDataRole.UserRole)

    def update_item(self, item: BrowserItem) -> None:
        for row in range(self.count()):
            list_item = self.item(row)
            if list_item is None:
                continue
            browser_item = list_item.data(Qt.ItemDataRole.UserRole)
            if browser_item is None or browser_item.path != item.path:
                continue
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.setItemWidget(list_item, self._build_card(item))
            return

    def _emit_context_request(self, position) -> None:
        item = self.itemAt(position)
        browser_item = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if item is not None:
            self.setCurrentItem(item)
        self.context_requested.emit(browser_item, self.viewport().mapToGlobal(position))

    def keyPressEvent(self, event) -> None:
        if self._handle_filter_key(event):
            return
        super().keyPressEvent(event)

    def _icon(self, item: BrowserItem):
        return browser_item_icon(item, size=52)

    def _build_card(self, item: BrowserItem) -> QWidget:
        card = QWidget()
        card.setObjectName("iconCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(self._icon(item).pixmap(self.iconSize()))
        icon_label.setFixedSize(56, 56)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name_label = QLabel(item.display_name)
        name_label.setObjectName("iconCardTitle")
        name_label.setWordWrap(True)

        subtitle_label = QLabel(self._secondary_text(item))
        subtitle_label.setObjectName("iconCardSubtitle")
        subtitle_label.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(name_label)
        text_layout.addWidget(subtitle_label)
        text_layout.addStretch(1)

        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)
        return card

    def _secondary_text(self, item: BrowserItem) -> str:
        if item.item_type is ItemType.DIRECTORY:
            return self._format_mtime(item.modified_time) or "Folder"
        if item.item_type is ItemType.SEQUENCE:
            parts = [item.frame_range or f"{item.count} frames"]
            size_text = self._format_size(item.size_bytes)
            if size_text:
                parts.append(size_text)
            modified_text = self._format_mtime(item.modified_time)
            if modified_text:
                parts.append(modified_text)
            return "  ·  ".join(parts)
        parts = []
        size_text = self._format_size(item.size_bytes)
        if size_text:
            parts.append(size_text)
        modified_text = self._format_mtime(item.modified_time)
        if modified_text:
            parts.append(modified_text)
        return "  ·  ".join(parts) or "File"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return ""
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        unit = units[0]
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                break
            size /= 1024.0
        return f"{size:.1f} {unit}"

    @staticmethod
    def _format_mtime(timestamp: float) -> str:
        if timestamp <= 0:
            return ""
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

    def _handle_filter_key(self, event) -> bool:
        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        if event.key() == Qt.Key.Key_Backspace:
            self.filter_backspace_requested.emit()
            event.accept()
            return True
        if event.key() == Qt.Key.Key_Delete:
            self.filter_clear_requested.emit()
            event.accept()
            return True
        if event.key() == Qt.Key.Key_Escape:
            self.filter_clear_requested.emit()
            event.accept()
            return True
        text = event.text()
        if text and text.isprintable():
            self.filter_text_typed.emit(text)
            event.accept()
            return True
        return False

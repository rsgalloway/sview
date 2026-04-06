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
Contains the ContentsTable widget for displaying the contents of a directory.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from sview.model import BrowserItem, ItemType, format_frame_ranges
from sview.qt.icons import browser_item_icon


class BrowserTableItem(QTableWidgetItem):
    def __lt__(self, other) -> bool:
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)

        self_item = self.data(Qt.ItemDataRole.UserRole)
        other_item = other.data(Qt.ItemDataRole.UserRole)
        if isinstance(self_item, BrowserItem) and isinstance(other_item, BrowserItem):
            self_priority = 0 if self_item.item_type is ItemType.DIRECTORY else 1
            other_priority = 0 if other_item.item_type is ItemType.DIRECTORY else 1
            if self_priority != other_priority:
                return self_priority < other_priority

        return self.text().lower() < other.text().lower()


class ContentsTable(QTableWidget):
    RENDER_BATCH_SIZE = 100
    context_requested = Signal(object, object)
    filter_text_typed = Signal(str)
    filter_backspace_requested = Signal()
    filter_clear_requested = Signal()
    activate_current_requested = Signal()
    navigate_up_requested = Signal()

    HEADERS = [
        "Name",
        "Type",
        "Range",
        "Frames",
        "Missing",
        "Size",
        "Modified",
    ]

    def __init__(self) -> None:
        super().__init__(0, len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        header = self.horizontalHeader()
        for column in range(len(self.HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(0, 320)
        self.setColumnWidth(1, 90)
        self.setColumnWidth(2, 110)
        self.setColumnWidth(3, 70)
        self.setColumnWidth(4, 110)
        self.setColumnWidth(5, 90)
        self.setColumnWidth(6, 140)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWordWrap(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context_request)
        self._pending_items: list[BrowserItem] = []
        self._render_index = 0
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(0)
        self._render_timer.timeout.connect(self._render_next_batch)
        self.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.sortItems(0, Qt.SortOrder.AscendingOrder)

    def set_items(self, items: list[BrowserItem]) -> None:
        self._render_timer.stop()
        self._pending_items = list(items)
        self._render_index = 0
        self.clearContents()
        self.clearSelection()
        self.setSortingEnabled(False)
        self.setRowCount(len(items))
        if not items:
            self.setSortingEnabled(True)
            return
        self._render_timer.start()

    def _render_next_batch(self) -> None:
        end_index = min(
            self._render_index + self.RENDER_BATCH_SIZE, len(self._pending_items)
        )
        for row in range(self._render_index, end_index):
            item = self._pending_items[row]
            self.setRowHeight(row, 28)
            values = [
                item.display_name,
                self._type_label(item),
                item.frame_range or "",
                str(item.count) if item.count else "",
                self._missing_label(item),
                self._format_size(item.size_bytes),
                self._format_mtime(item.modified_time),
            ]

            for column, value in enumerate(values):
                table_item = BrowserTableItem(value)
                table_item.setData(Qt.ItemDataRole.UserRole, item)
                if column == 0:
                    table_item.setIcon(self._item_icon(item))
                if item.item_type is ItemType.SEQUENCE and item.missing_count:
                    table_item.setBackground(QColor("#433631"))
                elif item.item_type is ItemType.DIRECTORY:
                    table_item.setForeground(QColor("#d0d6de"))
                if column in {3, 4, 5, 6}:
                    table_item.setTextAlignment(
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
                    )
                self.setItem(row, column, table_item)

        self._render_index = end_index
        if self._render_index >= len(self._pending_items):
            self._render_timer.stop()
            self.setSortingEnabled(True)
            self.sortItems(0, Qt.SortOrder.AscendingOrder)
            self.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
            if self.rowCount() > 0:
                self.setCurrentCell(0, 0)
                self.selectRow(0)

    def current_browser_item(self) -> BrowserItem | None:
        selected = self.selectedItems()
        if not selected:
            return None
        return selected[0].data(Qt.ItemDataRole.UserRole)

    def update_item(self, item: BrowserItem) -> None:
        for row in range(self.rowCount()):
            row_item = self.item(row, 0)
            if row_item is None:
                continue
            row_browser_item = row_item.data(Qt.ItemDataRole.UserRole)
            if row_browser_item is None or row_browser_item.path != item.path:
                continue
            missing_item = self.item(row, 4)
            size_item = self.item(row, 5)
            modified_item = self.item(row, 6)
            for column in range(self.columnCount()):
                cell = self.item(row, column)
                if cell is None:
                    continue
                cell.setData(Qt.ItemDataRole.UserRole, item)
                if item.item_type is ItemType.SEQUENCE and item.missing_count:
                    cell.setBackground(QColor("#433631"))
                else:
                    cell.setBackground(QBrush())
                if item.item_type is ItemType.DIRECTORY:
                    cell.setForeground(QColor("#d0d6de"))
            if size_item is not None:
                size_item.setText(self._format_size(item.size_bytes))
            if missing_item is not None:
                missing_item.setText(self._missing_label(item))
            if modified_item is not None:
                modified_item.setText(self._format_mtime(item.modified_time))
            return

    def _emit_context_request(self, position) -> None:
        item = None
        table_item = self.itemAt(position)
        if table_item is not None:
            item = table_item.data(Qt.ItemDataRole.UserRole)
            self.selectRow(table_item.row())
        self.context_requested.emit(item, self.viewport().mapToGlobal(position))

    def keyPressEvent(self, event) -> None:
        if self._handle_filter_key(event):
            return
        if event.key() == Qt.Key.Key_Left:
            self.navigate_up_requested.emit()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            if self.current_browser_item() is not None:
                self.activate_current_requested.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            current_item = self.current_browser_item()
            if current_item is not None and current_item.item_type is not ItemType.FILE:
                self.activate_current_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _item_icon(self, item: BrowserItem):
        return browser_item_icon(item, size=18)

    @staticmethod
    def _type_label(item: BrowserItem) -> str:
        if item.item_type is ItemType.SEQUENCE:
            return "Sequence"
        if item.item_type is ItemType.DIRECTORY:
            return "Folder"
        return "File"

    @staticmethod
    def _missing_label(item: BrowserItem) -> str:
        if item.item_type is not ItemType.SEQUENCE:
            return ""
        if not item.missing_count:
            return ""
        return format_frame_ranges(item.missing)

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

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
Contains the MainWindow class which serves as the primary UI for sview.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys

from PySide6.QtCore import QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from sview import __version__
from sview.config import AppConfig, build_command, get_repository_url
from sview.controller import BrowserController
from sview.model import BrowserItem, ItemType
from sview.qt.inspector import InspectorPanel
from sview.qt.table import ContentsTable
from sview.qt.tree import DirectoryTree
from sview.scanner import ScanResult


class MainWindow(QMainWindow):
    SEQUENCE_METADATA_WORKERS = 4

    def __init__(
        self,
        controller: BrowserController | None = None,
        initial_path: str | Path | None = None,
        debug: bool = False,
    ) -> None:
        super().__init__()
        self._controller = controller or BrowserController()
        self._config = AppConfig.load()
        self._debug = debug
        self._initial_path = (
            self._normalize_path(initial_path)
            if initial_path is not None
            else self._controller.current_path
        )
        self._visible_items: list[BrowserItem] = []
        self._history: list[str] = []
        self._history_index = -1
        self._pending_request: tuple[str, bool] | None = None
        self._active_request: tuple[str, bool] | None = None
        self._load_process: QProcess | None = None
        self._load_stdout_buffer = bytearray()
        self._load_stderr_buffer = ""
        self._load_stderr_partial = ""
        self._load_cancelled = False
        self._load_timed_out = False
        self._metadata_executor = ThreadPoolExecutor(
            max_workers=self.SEQUENCE_METADATA_WORKERS,
            thread_name_prefix="sview-seqmeta",
        )
        self._metadata_queue: Queue[tuple[int, str, int, float]] = Queue()
        self._metadata_token = 0
        self._metadata_pending_count = 0

        self.setWindowTitle("sview")
        self.resize(1400, 800)

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Search")

        self._table = ContentsTable()
        self._inspector = InspectorPanel()
        self._tree = DirectoryTree(self._initial_path)
        self._main_splitter: QSplitter | None = None

        self._progress_timer = QTimer(self)
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(30)
        self._busy_timer.timeout.connect(self._advance_busy_indicator)
        self._metadata_timer = QTimer(self)
        self._metadata_timer.setInterval(30)
        self._metadata_timer.timeout.connect(self._process_sequence_metadata_updates)
        self._scan_timeout_timer = QTimer(self)
        self._scan_timeout_timer.setSingleShot(True)
        self._scan_timeout_timer.timeout.connect(self._handle_scan_timeout)
        self._busy_value = 0
        self._busy_direction = 1

        self._build_toolbar()
        self._build_menu_bar()
        self._build_layout()
        self._connect_signals()
        QTimer.singleShot(
            0, lambda: self._request_directory(self._initial_path, add_to_history=True)
        )

    @staticmethod
    def _normalize_path(path: str | Path) -> Path:
        normalized = Path(path).expanduser()
        if not normalized.is_absolute():
            normalized = Path.cwd() / normalized
        return normalized

    def _build_toolbar(self) -> None:
        self._open_action = QAction("Open Folder", self)
        self._refresh_action = QAction("Refresh", self)
        self.addAction(self._open_action)
        self.addAction(self._refresh_action)

        self._back_button = QPushButton()
        self._back_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        )
        self._back_button.setToolTip("Back")
        self._back_button.setFixedWidth(28)
        self._home_button = QPushButton()
        self._home_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon)
        )
        self._home_button.setToolTip("Home")
        self._home_button.setFixedWidth(28)
        self._up_button = QPushButton()
        self._up_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        )
        self._up_button.setToolTip("Up")
        self._up_button.setFixedWidth(28)
        self._open_button = QPushButton()
        self._open_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self._open_button.setToolTip("Open Folder")
        self._open_button.setFixedWidth(32)
        self._refresh_button = QPushButton()
        self._refresh_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self._refresh_button.setToolTip("Refresh")
        self._refresh_button.setFixedWidth(32)
        self._group_toggle = QPushButton()
        self._group_toggle.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self._group_toggle.setToolTip("Sequence View")
        self._group_toggle.setCheckable(True)
        self._group_toggle.setChecked(True)
        self._group_toggle.setFixedWidth(32)
        self._raw_toggle = QPushButton()
        self._raw_toggle.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        self._raw_toggle.setToolTip("File View")
        self._raw_toggle.setCheckable(True)
        self._raw_toggle.setFixedWidth(32)
        self._stop_button = QPushButton()
        self._stop_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserStop)
        )
        self._stop_button.setToolTip("Stop")
        self._stop_button.setFixedWidth(32)
        self._stop_button.setEnabled(False)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setMaximumWidth(84)
        self._progress_bar.setFixedHeight(12)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        help_menu = menu_bar.addMenu("Help")

        self._file_open_action = file_menu.addAction("Open Folder...")
        self._file_refresh_action = file_menu.addAction("Refresh")
        file_menu.addSeparator()
        self._file_quit_action = file_menu.addAction("Quit")

        self._edit_copy_path_action = edit_menu.addAction("Copy Path")
        self._edit_copy_pattern_action = edit_menu.addAction("Copy Pattern")
        self._edit_properties_action = edit_menu.addAction("Properties")

        self._help_about_action = help_menu.addAction("About")
        self._help_repo_action = help_menu.addAction("GitHub Repo")

    def _build_layout(self) -> None:
        center = QWidget()
        root_layout = QVBoxLayout(center)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(6)
        toolbar_row.addWidget(self._back_button)
        toolbar_row.addWidget(self._up_button)
        toolbar_row.addWidget(self._home_button)
        toolbar_row.addWidget(self._open_button)
        toolbar_row.addWidget(self._refresh_button)
        toolbar_row.addSpacing(6)
        toolbar_row.addWidget(self._group_toggle)
        toolbar_row.addWidget(self._raw_toggle)
        toolbar_row.addWidget(self._stop_button)
        toolbar_row.addWidget(self._progress_bar)
        toolbar_row.addStretch(1)
        self._filter_input.setMaximumWidth(320)
        toolbar_row.addWidget(self._filter_input)
        root_layout.addLayout(toolbar_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._table)
        splitter.addWidget(self._inspector)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)
        self._main_splitter = splitter
        splitter.setSizes([260, 900, 0])
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(center)
        self.statusBar().showMessage("Ready")

    def _connect_signals(self) -> None:
        self._open_action.triggered.connect(self._choose_directory)
        self._refresh_action.triggered.connect(self._refresh_directory)
        self._file_open_action.triggered.connect(self._choose_directory)
        self._file_refresh_action.triggered.connect(self._refresh_directory)
        self._file_quit_action.triggered.connect(self.close)
        self._edit_copy_path_action.triggered.connect(self._copy_selected_path)
        self._edit_copy_pattern_action.triggered.connect(self._copy_selected_pattern)
        self._edit_properties_action.triggered.connect(self._open_selected_properties)
        self._help_repo_action.triggered.connect(self._open_repo_page)
        self._help_about_action.triggered.connect(self._show_about_dialog)
        self._open_button.clicked.connect(self._choose_directory)
        self._refresh_button.clicked.connect(self._refresh_directory)
        self._back_button.clicked.connect(self._go_back)
        self._home_button.clicked.connect(self._go_home)
        self._up_button.clicked.connect(self._go_up)
        self._stop_button.clicked.connect(self._cancel_scan)
        self._group_toggle.toggled.connect(self._toggle_grouped_view)
        self._raw_toggle.toggled.connect(self._toggle_raw_view)
        self._filter_input.textChanged.connect(self._apply_filter)
        self._table.itemSelectionChanged.connect(self._sync_inspector)
        self._table.itemDoubleClicked.connect(self._activate_selected_item)
        self._table.context_requested.connect(self._show_item_context_menu)
        self._tree.selectionModel().selectionChanged.connect(
            self._handle_tree_selection
        )
        self._inspector.copy_path_button.clicked.connect(self._copy_selected_path)
        self._inspector.copy_pattern_button.clicked.connect(self._copy_selected_pattern)
        self._inspector.expand_button.clicked.connect(
            self._expand_or_collapse_selected_sequence
        )
        self._inspector.close_button.clicked.connect(self._close_inspector)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._pending_request = None
        if self._load_process is not None:
            self._load_process.kill()
            self._load_process.waitForFinished(500)
        self._metadata_executor.shutdown(wait=False)
        event.accept()

    def _choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose directory", str(self._controller.current_path)
        )
        if directory:
            self._tree.setRootIndex(self._tree.filesystem_model.index(directory))
            self._request_directory(directory, add_to_history=True)

    def _refresh_directory(self) -> None:
        self._request_directory(self._controller.current_path, add_to_history=False)

    def _go_back(self) -> None:
        if self._collapse_expanded_sequence():
            return
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._request_directory(
            self._history[self._history_index], add_to_history=False
        )
        self._update_navigation_buttons()

    def _go_up(self) -> None:
        if self._collapse_expanded_sequence():
            return
        current = self._controller.current_path
        parent = current.parent
        if parent == current:
            return
        self._request_directory(parent, add_to_history=True)

    def _go_home(self) -> None:
        self._collapse_tree()
        home = Path.home()
        self._tree.setRootIndex(self._tree.filesystem_model.index(str(home)))
        self._sync_tree_to_path(str(home))
        self._request_directory(home, add_to_history=True)

    def _toggle_grouped_view(self, enabled: bool) -> None:
        if not enabled and not self._raw_toggle.isChecked():
            self._group_toggle.setChecked(True)
            return
        self._controller.set_grouped_view(enabled)
        self._raw_toggle.blockSignals(True)
        self._raw_toggle.setChecked(not enabled)
        self._raw_toggle.blockSignals(False)
        self._apply_filter(self._filter_input.text())

    def _toggle_raw_view(self, enabled: bool) -> None:
        if not enabled and not self._group_toggle.isChecked():
            self._raw_toggle.setChecked(True)
            return
        if enabled == (not self._controller.grouped_view):
            return
        self._group_toggle.blockSignals(True)
        self._group_toggle.setChecked(not enabled)
        self._group_toggle.blockSignals(False)
        self._controller.set_grouped_view(not enabled)
        self._apply_filter(self._filter_input.text())

    def _handle_tree_selection(self) -> None:
        index = self._tree.currentIndex()
        path = self._tree.filesystem_model.filePath(index)
        if path:
            self._request_directory(path, add_to_history=True)

    def _request_directory(self, path: str | Path, add_to_history: bool) -> None:
        requested_path = str(self._normalize_path(path))
        self._metadata_token += 1
        self._metadata_pending_count = 0
        if self._is_loading():
            self._pending_request = (requested_path, add_to_history)
            self.statusBar().showMessage(f"Queued {requested_path}")
            return

        self._active_request = (requested_path, add_to_history)
        self._set_loading_state(True, requested_path)
        self._load_cancelled = False
        self._load_timed_out = False
        self._load_stdout_buffer = bytearray()
        self._load_stderr_buffer = ""
        self._load_stderr_partial = ""

        process = QProcess(self)
        process.setProgram(sys.executable)
        arguments = ["-u", "-m", "sview.worker"]
        if self._debug:
            arguments.append("--debug")
        arguments.append(requested_path)
        process.setArguments(arguments)
        process.readyReadStandardOutput.connect(
            lambda process=process: self._read_scan_stdout(process)
        )
        process.readyReadStandardError.connect(
            lambda process=process: self._read_scan_stderr(process)
        )
        process.errorOccurred.connect(
            lambda error, process=process: self._handle_scan_process_error(
                process, error
            )
        )
        process.finished.connect(
            lambda exit_code, exit_status, process=process: self._handle_scan_process_finished(
                process, exit_code, exit_status
            )
        )
        self._load_process = process
        process.start()
        timeout_seconds = self._config.scan_worker.timeout_seconds
        if timeout_seconds is not None and timeout_seconds > 0:
            self._scan_timeout_timer.start(timeout_seconds * 1000)

    def _read_scan_stdout(self, process: QProcess) -> None:
        if process is not self._load_process:
            return
        self._load_stdout_buffer.extend(bytes(process.readAllStandardOutput()))

    def _read_scan_stderr(self, process: QProcess) -> None:
        if process is not self._load_process:
            return
        chunk = bytes(process.readAllStandardError()).decode("utf-8", "replace")
        if not chunk:
            return
        self._load_stderr_buffer += chunk
        self._load_stderr_partial += chunk
        lines = self._load_stderr_partial.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self._load_stderr_partial = lines.pop()
        else:
            self._load_stderr_partial = ""
        for line in lines:
            text = line.strip()
            if text:
                if self._debug:
                    print(f"[sview scan] {text}", file=sys.stderr, flush=True)
                self.statusBar().showMessage(text)

    def _handle_scan_process_error(
        self, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if process is not self._load_process or self._load_cancelled:
            return
        if error is QProcess.ProcessError.FailedToStart:
            message = process.errorString() or "Failed to start scan worker."
            self._clear_scan_process()
            self._handle_failed_scan(message)

    def _handle_scan_process_finished(
        self, process: QProcess, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        if process is not self._load_process:
            return
        self._read_scan_stdout(process)
        self._read_scan_stderr(process)

        response_text = (
            bytes(self._load_stdout_buffer).decode("utf-8", "replace").strip()
        )
        error_text = f"{self._load_stderr_buffer}{self._load_stderr_partial}".strip()
        cancelled = self._load_cancelled
        timed_out = self._load_timed_out

        self._clear_scan_process()

        if timed_out:
            self._handle_timed_out_scan(error_text)
            return
        if cancelled:
            self._handle_cancelled_scan()
            return
        if exit_status is QProcess.ExitStatus.CrashExit:
            self._handle_failed_scan(error_text or "Scan worker crashed.")
            return
        if exit_code != 0:
            self._handle_failed_scan(
                error_text or f"Scan worker exited with code {exit_code}."
            )
            return
        if not response_text:
            self._handle_failed_scan("Scan worker returned no data.")
            return

        try:
            result = ScanResult.from_dict(json.loads(response_text))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._handle_failed_scan(f"Invalid scan response: {exc}")
            return
        self._handle_finished_scan(result)

    def _handle_finished_scan(self, result: object) -> None:
        request = self._active_request
        self._set_loading_state(False)
        if request is None or not isinstance(result, ScanResult):
            return

        items = self._controller.apply_scan_result(result)
        self._visible_items = items
        self._start_sequence_metadata_enrichment(result)
        if request[1]:
            self._push_history(str(result.path))
        self._active_request = None
        self._sync_tree_to_path(str(result.path))
        self._apply_filter(self._filter_input.text())
        self._drain_pending_request()

    def _handle_failed_scan(self, error_message: str) -> None:
        self._active_request = None
        self._set_loading_state(False)
        if self._debug and error_message:
            print(f"[sview error] {error_message}", file=sys.stderr, flush=True)
        self.statusBar().showMessage(f"Failed to load directory: {error_message}", 5000)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Scan failed")
        dialog.setText("Failed to load directory.")
        dialog.setInformativeText(self._summarize_error_message(error_message))
        details = error_message.strip()
        if details and details != dialog.informativeText():
            dialog.setDetailedText(details)
        dialog.exec()
        self._drain_pending_request()

    def _handle_cancelled_scan(self) -> None:
        self._active_request = None
        self._set_loading_state(False)
        self.statusBar().showMessage("Scan cancelled", 3000)
        self._drain_pending_request()

    def _handle_timed_out_scan(self, error_message: str) -> None:
        self._active_request = None
        self._set_loading_state(False)
        timeout_seconds = self._config.scan_worker.timeout_seconds
        summary = (
            f"Scan exceeded {timeout_seconds} seconds and was stopped."
            if timeout_seconds is not None
            else "Scan timed out and was stopped."
        )
        if self._debug:
            print(f"[sview error] {summary}", file=sys.stderr, flush=True)
            if error_message:
                print(error_message, file=sys.stderr, flush=True)
        self.statusBar().showMessage(summary, 5000)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Scan timed out")
        dialog.setText(summary)
        dialog.setInformativeText(
            "This scan worker was terminated to protect system responsiveness."
        )
        details = error_message.strip()
        if details:
            dialog.setDetailedText(details)
        dialog.exec()
        self._drain_pending_request()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        if not needle:
            filtered = self._controller.current_items
        else:
            filtered = [
                item
                for item in self._controller.current_items
                if needle in item.display_name.lower()
            ]

        self._visible_items = filtered
        self._table.set_items(filtered)
        self._inspector.clear_details()
        self._update_status_bar()

    def _sync_inspector(self) -> None:
        item = self._table.current_browser_item()
        if item is None:
            self._inspector.clear_details()
            return
        self._inspector.set_item(item)
        if self._controller.expanded_sequence and item.item_type is ItemType.SEQUENCE:
            self._inspector.expand_button.setText("Collapse Sequence")

    def _activate_selected_item(self, *_args) -> None:
        item = self._table.current_browser_item()
        if item is None:
            return
        self._activate_item(item)

    def _expand_or_collapse_selected_sequence(self) -> None:
        item = self._inspector.current_item or self._table.current_browser_item()
        if item is None or item.item_type is not ItemType.SEQUENCE:
            return
        if (
            self._controller.expanded_sequence
            and self._controller.expanded_sequence.path == item.path
        ):
            self._controller.collapse_sequence()
            self._apply_filter(self._filter_input.text())
            self.statusBar().showMessage(f"Collapsed {item.display_name}", 4000)
            return
        self._controller.expand_sequence(item)
        self._apply_filter(self._filter_input.text())
        self.statusBar().showMessage(
            f"Expanded {item.display_name} into frame files", 4000
        )

    def _copy_selected_path(self) -> None:
        item = self._inspector.current_item or self._table.current_browser_item()
        if item is None:
            return
        QGuiApplication.clipboard().setText(item.path)
        self.statusBar().showMessage(f"Copied path for {item.display_name}", 3000)

    def _copy_selected_pattern(self) -> None:
        item = self._inspector.current_item or self._table.current_browser_item()
        if item is None or item.item_type is not ItemType.SEQUENCE:
            return
        QGuiApplication.clipboard().setText(item.display_name)
        self.statusBar().showMessage(f"Copied pattern {item.display_name}", 3000)

    def _open_selected_properties(self) -> None:
        item = self._inspector.current_item or self._table.current_browser_item()
        if item is None:
            return
        self._open_properties(item)

    def _show_item_context_menu(
        self, item: BrowserItem | None, global_position
    ) -> None:
        if item is None:
            return

        menu = QMenu(self)
        open_action = menu.addAction("Open")
        copy_path_action = menu.addAction("Copy Path")
        copy_pattern_action = None
        expand_action = None
        sstat_action = None
        scopy_action = None
        smove_action = None

        if item.item_type is ItemType.SEQUENCE:
            copy_pattern_action = menu.addAction("Copy Pattern")
            expand_action = menu.addAction(
                "Collapse Sequence"
                if self._controller.expanded_sequence
                and self._controller.expanded_sequence.path == item.path
                else "Expand Sequence"
            )
            menu.addSeparator()
            sstat_action = menu.addAction("sstat")
            scopy_action = menu.addAction("scopy...")
            smove_action = menu.addAction("smove...")

        menu.addSeparator()
        properties_action = menu.addAction("Properties")

        chosen = menu.exec(global_position)
        if chosen is None:
            return
        if chosen == open_action:
            self._activate_item(item)
        elif chosen == copy_path_action:
            self._copy_item_path(item)
        elif copy_pattern_action is not None and chosen == copy_pattern_action:
            self._copy_item_pattern(item)
        elif expand_action is not None and chosen == expand_action:
            self._expand_or_collapse_item(item)
        elif sstat_action is not None and chosen == sstat_action:
            self._run_sequence_sstat(item)
        elif scopy_action is not None and chosen == scopy_action:
            self._run_sequence_transfer(item, "scopy")
        elif smove_action is not None and chosen == smove_action:
            self._run_sequence_transfer(item, "smove")
        elif chosen == properties_action:
            self._open_properties(item)

    def _activate_item(self, item: BrowserItem) -> None:
        if item.item_type is ItemType.DIRECTORY:
            self._sync_tree_to_path(item.path)
            self._request_directory(item.path, add_to_history=True)
            return
        if item.item_type is ItemType.FILE:
            self._open_file_item(item)
            return
        self._open_sequence_item(item)

    def _copy_item_path(self, item: BrowserItem) -> None:
        QGuiApplication.clipboard().setText(item.path)
        self.statusBar().showMessage(f"Copied path for {item.display_name}", 3000)

    def _copy_item_pattern(self, item: BrowserItem) -> None:
        if item.item_type is not ItemType.SEQUENCE:
            return
        QGuiApplication.clipboard().setText(item.display_name)
        self.statusBar().showMessage(f"Copied pattern {item.display_name}", 3000)

    def _open_properties(self, item: BrowserItem) -> None:
        if self._main_splitter is None:
            return
        sizes = self._main_splitter.sizes()
        if len(sizes) >= 3 and sizes[2] == 0:
            grow = min(max(260, sizes[1] // 3), sizes[1])
            sizes[1] = max(0, sizes[1] - grow)
            sizes[2] = grow
            self._main_splitter.setSizes(sizes)
        self._inspector.set_item(item)

    def _expand_or_collapse_item(self, item: BrowserItem) -> None:
        self._inspector.set_item(item)
        self._expand_or_collapse_selected_sequence()

    def _run_sequence_sstat(self, item: BrowserItem) -> None:
        executable = self._tool_path("sstat")
        if executable is None:
            return
        completed = subprocess.run(
            [executable, item.path, "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            QMessageBox.warning(
                self, "sstat failed", completed.stderr.strip() or "sstat failed."
            )
            return
        text = self._format_sstat_output(completed.stdout.strip())
        QMessageBox.information(self, "Properties", text or "No output.")

    def _run_sequence_transfer(self, item: BrowserItem, tool_name: str) -> None:
        executable = self._tool_path(tool_name)
        if executable is None:
            return
        destination = QFileDialog.getExistingDirectory(
            self, f"{tool_name} destination", str(self._controller.current_path)
        )
        if not destination:
            return
        confirmation = QMessageBox.question(
            self,
            tool_name,
            f"Run `{tool_name}` for {item.display_name} into {destination}?",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        subprocess.Popen([executable, item.path, destination])
        self.statusBar().showMessage(
            f"Started {tool_name} for {item.display_name}", 4000
        )

    def _open_file_item(self, item: BrowserItem) -> None:
        handler = self._config.file_handler
        if handler.mode == "command" and handler.command:
            subprocess.Popen(build_command(handler.command, item.path))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(item.path))

    def _open_sequence_item(self, item: BrowserItem) -> None:
        handler = self._config.sequence_handler
        if handler.mode == "command" and handler.command:
            subprocess.Popen(build_command(handler.command, item.path))
            return
        if handler.mode == "system":
            QDesktopServices.openUrl(QUrl.fromLocalFile(item.path))
            return
        self._expand_or_collapse_item(item)

    def _tool_path(self, tool_name: str) -> str | None:
        executable = str(Path(sys.executable).with_name(tool_name))
        if Path(executable).exists():
            return executable
        QMessageBox.warning(
            self,
            f"{tool_name} unavailable",
            f"Could not find `{tool_name}` in the current environment.",
        )
        return None

    def _push_history(self, path: str) -> None:
        normalized = str(Path(path))
        if self._history and self._history[self._history_index] == normalized:
            return
        self._history = self._history[: self._history_index + 1]
        self._history.append(normalized)
        self._history_index = len(self._history) - 1
        self._update_navigation_buttons()

    def _update_navigation_buttons(self) -> None:
        loading = self._is_loading()
        self._back_button.setEnabled(not loading and self._history_index > 0)
        self._up_button.setEnabled(
            not loading
            and self._controller.current_path.parent != self._controller.current_path
        )

    def _sync_tree_to_path(self, path: str) -> None:
        model = self._tree.filesystem_model
        index = model.index(path)
        if not index.isValid():
            return
        parent = index.parent()
        while parent.isValid():
            self._tree.expand(parent)
            parent = parent.parent()
        self._tree.selectionModel().blockSignals(True)
        self._tree.setCurrentIndex(index)
        self._tree.selectionModel().blockSignals(False)
        self._tree.scrollTo(index)

    def _set_loading_state(self, loading: bool, path: str | None = None) -> None:
        self._back_button.setEnabled(not loading and self._history_index > 0)
        self._up_button.setEnabled(
            not loading
            and self._controller.current_path.parent != self._controller.current_path
        )
        self._group_toggle.setEnabled(not loading)
        self._raw_toggle.setEnabled(not loading)
        self._open_button.setEnabled(not loading)
        self._refresh_button.setEnabled(not loading)
        self._filter_input.setEnabled(not loading)
        self._tree.setEnabled(not loading)
        self._table.setEnabled(not loading)
        self._stop_button.setEnabled(loading)
        self._progress_bar.setVisible(loading)
        if loading:
            self._busy_value = 0
            self._busy_direction = 1
            self._progress_bar.setValue(self._busy_value)
            self._busy_timer.start()
        else:
            self._busy_timer.stop()
            self._progress_bar.setValue(0)
        if loading and path is not None:
            self.statusBar().showMessage(f"Loading {path}...")

    def _drain_pending_request(self) -> None:
        if self._pending_request is None:
            return
        pending = self._pending_request
        self._pending_request = None
        self._request_directory(*pending)

    def _cancel_scan(self) -> None:
        self._pending_request = None
        if self._load_process is None:
            return
        self._load_cancelled = True
        self._stop_button.setEnabled(False)
        self.statusBar().showMessage("Cancelling scan...")
        self._load_process.kill()

    def _handle_scan_timeout(self) -> None:
        if self._load_process is None:
            return
        self._load_timed_out = True
        self._stop_button.setEnabled(False)
        self.statusBar().showMessage("Scan timed out, stopping worker...")
        if self._debug:
            print(
                "[sview scan] timeout reached, killing worker",
                file=sys.stderr,
                flush=True,
            )
        self._load_process.kill()

    def _update_status_bar(self) -> None:
        count = len(self._visible_items)
        total_size = sum(item.size_bytes for item in self._visible_items)
        mode = "Sequence View" if self._controller.grouped_view else "File View"
        if self._controller.expanded_sequence is not None:
            mode = f"Expanded {self._controller.expanded_sequence.display_name}"
        self.statusBar().showMessage(
            f"{count} items, {self._format_size(total_size)}   |   {mode}   |   {self._controller.current_path}"
        )
        self._update_navigation_buttons()

    def _start_sequence_metadata_enrichment(self, result: ScanResult) -> None:
        self._metadata_pending_count = 0
        self._metadata_timer.stop()
        return

    def _compute_sequence_metadata(
        self,
        token: int,
        item_path: str,
        child_paths: list[str],
        raw_lookup: dict[str, BrowserItem],
    ) -> None:
        size_bytes = 0
        modified_time = 0.0
        for child_path in child_paths:
            raw_item = raw_lookup.get(child_path)
            if raw_item is None:
                continue
            size_bytes += raw_item.size_bytes
            if raw_item.modified_time > modified_time:
                modified_time = raw_item.modified_time
        self._metadata_queue.put((token, item_path, size_bytes, modified_time))

    def _process_sequence_metadata_updates(self) -> None:
        handled = False
        while True:
            try:
                (
                    token,
                    item_path,
                    size_bytes,
                    modified_time,
                ) = self._metadata_queue.get_nowait()
            except Empty:
                break

            handled = True
            if token != self._metadata_token:
                continue

            self._metadata_pending_count = max(0, self._metadata_pending_count - 1)
            item = self._controller.update_sequence_metadata(
                item_path, size_bytes, modified_time
            )
            if item is None:
                continue
            self._table.update_item(item)
            if (
                self._inspector.current_item is not None
                and self._inspector.current_item.path == item.path
            ):
                self._inspector.set_item(item)

        if handled:
            self._update_status_bar()
        if self._metadata_pending_count == 0:
            self._metadata_timer.stop()

    def _advance_busy_indicator(self) -> None:
        self._busy_value += self._busy_direction * 4
        if self._busy_value >= 100:
            self._busy_value = 100
            self._busy_direction = -1
        elif self._busy_value <= 0:
            self._busy_value = 0
            self._busy_direction = 1
        self._progress_bar.setValue(self._busy_value)

    def _close_inspector(self) -> None:
        if self._main_splitter is None:
            return
        sizes = self._main_splitter.sizes()
        if len(sizes) < 3:
            return
        reclaimed = sizes[2]
        sizes[1] += reclaimed
        sizes[2] = 0
        self._main_splitter.setSizes(sizes)

    def _collapse_tree(self) -> None:
        self._tree.collapseAll()

    def _collapse_expanded_sequence(self) -> bool:
        if self._controller.expanded_sequence is None:
            return False
        sequence = self._controller.expanded_sequence
        self._controller.collapse_sequence()
        self._apply_filter(self._filter_input.text())
        if sequence is not None:
            self.statusBar().showMessage(
                f"Returned to {self._controller.current_path.name} sequence view", 3000
            )
        return True

    def _is_loading(self) -> bool:
        return (
            self._load_process is not None
            and self._load_process.state() != QProcess.ProcessState.NotRunning
        )

    def _clear_scan_process(self) -> None:
        self._scan_timeout_timer.stop()
        if self._load_process is not None:
            self._load_process.deleteLater()
        self._load_process = None
        self._load_stdout_buffer = bytearray()
        self._load_stderr_buffer = ""
        self._load_stderr_partial = ""
        self._load_cancelled = False
        self._load_timed_out = False

    def _open_repo_page(self) -> None:
        QDesktopServices.openUrl(QUrl(get_repository_url()))

    def _show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About sview",
            f"sview {__version__}\n\nSequence-aware filesystem browser.",
        )

    def _format_sstat_output(self, raw_output: str) -> str:
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            return raw_output

        lines = [
            f"Sequence: {data.get('sequence', '-')}",
            f"Range: {data.get('range', '-')}",
            f"Frames: {data.get('length', '-')}",
            f"Padding: {data.get('pad', '-')}",
            f"Missing: {self._format_missing(data.get('missing'))}",
            f"Size: {data.get('size_human', '-')}",
        ]

        access = data.get("access", {})
        modify = data.get("modify", {})
        change = data.get("change", {})
        if access:
            lines.append(
                f"Accessed: {access.get('first', '-')} to {access.get('last', '-')}"
            )
        if modify:
            lines.append(
                f"Modified: {modify.get('first', '-')} to {modify.get('last', '-')}"
            )
        if change:
            lines.append(
                f"Changed: {change.get('first', '-')} to {change.get('last', '-')}"
            )

        head = data.get("head")
        tail = data.get("tail")
        if head is not None or tail is not None:
            lines.append(f"Parts: {head or ''} ... {tail or ''}".strip())
        return "\n".join(lines)

    @staticmethod
    def _format_missing(missing: object) -> str:
        if not missing:
            return "-"
        if not isinstance(missing, list):
            return str(missing)
        preview = ", ".join(str(value) for value in missing[:8])
        if len(missing) > 8:
            preview = f"{preview}, +{len(missing) - 8}"
        return preview

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        unit = units[0]
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                break
            size /= 1024.0
        return f"{size:.1f} {unit}"

    @staticmethod
    def _summarize_error_message(error_message: str) -> str:
        lines = [line.strip() for line in error_message.splitlines() if line.strip()]
        for line in reversed(lines):
            if line.startswith("ERROR:"):
                return line[len("ERROR:") :].strip()
        return lines[-1] if lines else "Unknown scan error."

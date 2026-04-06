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

import json
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QPoint, QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QGuiApplication,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from sview import __version__
from sview.config import (
    AppConfig,
    build_command,
    get_repository_url,
    load_ui_state,
    save_ui_state,
)
from sview.controller import BrowserController
from sview.model import BrowserItem, ItemType
from sview.qt.icon_view import ContentsIconView
from sview.qt.icons import sidebar_icon
from sview.qt.inspector import InspectorPanel
from sview.qt.table import ContentsTable
from sview.qt.tree import DirectoryTree
from sview.scanner import ScanResult


class MainWindow(QMainWindow):
    SIDEBAR_WIDTH = 280

    def __init__(
        self,
        controller: BrowserController | None = None,
        initial_path: str | Path | None = None,
        debug: bool = False,
    ) -> None:
        super().__init__()
        self._controller = controller or BrowserController()
        self._config = AppConfig.load()
        self._ui_state = load_ui_state()
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
        self._focus_after_load = "browser"

        self.setWindowTitle("sview")
        self.resize(1400, 800)

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Search")
        self._filter_input.setObjectName("searchInput")
        self._filter_input.setMinimumWidth(360)
        self._filter_input.setMaximumWidth(460)
        self._filter_input.setFixedHeight(34)
        self._clear_filter_action = self._filter_input.addAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_LineEditClearButton),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self._clear_filter_action.setVisible(False)

        self._table = ContentsTable()
        self._icon_view = ContentsIconView()
        self._center_stack = QStackedWidget()
        self._breadcrumb_bar = QWidget()
        self._breadcrumb_bar.setObjectName("breadcrumbBar")
        self._breadcrumb_layout = QHBoxLayout(self._breadcrumb_bar)
        self._breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        self._breadcrumb_layout.setSpacing(2)
        self._inspector = InspectorPanel()
        self._tree_title = QLabel("Folders")
        self._tree_toggle = QToolButton()
        self._show_hidden_files = bool(self._ui_state.get("show_hidden_files", False))
        self._tree = DirectoryTree(
            self._initial_path, show_hidden=self._show_hidden_files
        )
        self._main_splitter: QSplitter | None = None
        self._sidebar_expanded = bool(self._ui_state.get("sidebar_expanded", True))
        self._sidebar_restore_width = (
            self._coerce_int(self._ui_state.get("sidebar_width")) or self.SIDEBAR_WIDTH
        )
        self._loading_overlay = QLabel("Loading…")
        self._loading_overlay.setObjectName("loadingOverlay")
        self._loading_spinner = QProgressBar()
        self._loading_spinner.setObjectName("loadingSpinner")
        self._loading_spinner.setRange(0, 0)
        self._loading_spinner.setTextVisible(False)
        self._loading_spinner.hide()
        self._loading_overlay.hide()

        self._scan_timeout_timer = QTimer(self)
        self._scan_timeout_timer.setSingleShot(True)
        self._scan_timeout_timer.timeout.connect(self._handle_scan_timeout)

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
        self._back_button.setObjectName("navButton")
        self._back_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        )
        self._back_button.setToolTip("Back")
        self._back_button.setFixedWidth(28)
        self._sidebar_button = QPushButton()
        self._sidebar_button.setObjectName("navButton")
        self._sidebar_button.setFixedWidth(28)
        self._sidebar_button.setIcon(sidebar_icon(self._sidebar_expanded, size=18))
        self._sidebar_button.setToolTip(
            "Collapse folders" if self._sidebar_expanded else "Show folders"
        )
        self._home_button = QPushButton()
        self._home_button.setObjectName("navButton")
        self._home_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon)
        )
        self._home_button.setToolTip("Home")
        self._home_button.setFixedWidth(28)
        self._up_button = QPushButton()
        self._up_button.setObjectName("navButton")
        self._up_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        )
        self._up_button.setToolTip("Up")
        self._up_button.setFixedWidth(28)
        self._open_button = QPushButton()
        self._open_button.setObjectName("navButton")
        self._open_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self._open_button.setToolTip("Open Folder")
        self._open_button.setFixedWidth(32)
        self._refresh_button = QPushButton()
        self._refresh_button.setObjectName("navButton")
        self._refresh_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self._refresh_button.setToolTip("Refresh")
        self._refresh_button.setFixedWidth(32)
        self._content_mode_toggle = QPushButton()
        self._content_mode_toggle.setObjectName("toolbarToggle")
        self._content_mode_toggle.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self._content_mode_toggle.setToolTip("Sequence View")
        self._content_mode_toggle.setCheckable(True)
        self._content_mode_toggle.setChecked(True)
        self._content_mode_toggle.setFixedWidth(32)
        self._layout_mode_toggle = QPushButton()
        self._layout_mode_toggle.setObjectName("toolbarToggle")
        self._layout_mode_toggle.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self._layout_mode_toggle.setToolTip("Detail View")
        self._layout_mode_toggle.setCheckable(True)
        self._layout_mode_toggle.setChecked(
            self._ui_state.get("center_view", "details") != "icons"
        )
        self._layout_mode_toggle.setFixedWidth(32)
        self._stop_button = QPushButton()
        self._stop_button.setObjectName("toolbarToggle")
        self._stop_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserStop)
        )
        self._stop_button.setToolTip("Stop")
        self._stop_button.setFixedWidth(32)
        self._stop_button.setEnabled(False)
        self._menu_button = QPushButton()
        self._menu_button.setObjectName("toolbarToggle")
        self._menu_button.setText("≡")
        self._menu_button.setToolTip("Menu")
        self._menu_button.setFixedWidth(32)

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
        edit_menu.addSeparator()
        self._show_hidden_action = edit_menu.addAction("Show Hidden Files")
        self._show_hidden_action.setCheckable(True)
        self._show_hidden_action.setChecked(self._show_hidden_files)
        self._preferences_action = edit_menu.addAction("Preferences")

        self._help_about_action = help_menu.addAction("About")
        self._help_repo_action = help_menu.addAction("GitHub Repo")
        menu_bar.hide()

    def _build_layout(self) -> None:
        center = QWidget()
        root_layout = QVBoxLayout(center)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(4)

        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(4)
        toolbar_row.addWidget(self._sidebar_button)
        toolbar_row.addWidget(self._back_button)
        toolbar_row.addWidget(self._up_button)
        toolbar_row.addWidget(self._home_button)
        toolbar_row.addWidget(self._open_button)
        toolbar_row.addWidget(self._refresh_button)
        toolbar_row.addSpacing(4)
        toolbar_row.addWidget(self._content_mode_toggle)
        toolbar_row.addSpacing(4)
        toolbar_row.addWidget(self._layout_mode_toggle)
        toolbar_row.addWidget(self._stop_button)
        self._breadcrumb_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        toolbar_row.addWidget(self._breadcrumb_bar, 1)
        toolbar_row.addWidget(self._filter_input)
        toolbar_row.addWidget(self._menu_button)
        root_layout.addLayout(toolbar_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QWidget()
        sidebar.setMinimumWidth(0)
        sidebar.setMaximumWidth(self.SIDEBAR_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)
        sidebar_header = QHBoxLayout()
        sidebar_header.setContentsMargins(2, 0, 2, 0)
        sidebar_header.addWidget(self._tree_title)
        sidebar_header.addStretch(1)
        self._tree_toggle.setCheckable(True)
        self._tree_toggle.setChecked(self._sidebar_expanded)
        self._tree_toggle.setAutoRaise(True)
        self._tree_toggle.setFixedSize(18, 18)
        self._tree_toggle.setArrowType(
            Qt.ArrowType.LeftArrow
            if self._sidebar_expanded
            else Qt.ArrowType.RightArrow
        )
        self._tree_toggle.setToolTip(
            "Collapse folders" if self._sidebar_expanded else "Expand folders"
        )
        sidebar_header.addWidget(self._tree_toggle)
        sidebar_layout.addLayout(sidebar_header)
        sidebar_layout.addWidget(self._tree, 1)
        self._center_stack.addWidget(self._table)
        self._center_stack.addWidget(self._icon_view)
        self._center_stack.setCurrentWidget(
            self._icon_view if not self._layout_mode_toggle.isChecked() else self._table
        )
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self._center_stack, 1)

        splitter.addWidget(sidebar)
        splitter.addWidget(center_panel)
        splitter.addWidget(self._inspector)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)
        self._main_splitter = splitter
        splitter.setCollapsible(0, True)
        initial_sizes = self._coerce_splitter_sizes(
            self._ui_state.get("main_splitter_sizes"),
            [self._sidebar_restore_width, 900, 0],
        )
        if self._sidebar_expanded and initial_sizes[0] <= 0:
            initial_sizes[0] = self._sidebar_restore_width
        splitter.setSizes(initial_sizes)
        if not self._sidebar_expanded:
            self._apply_sidebar_state(False)
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(center)
        center.setObjectName("mainContent")
        self.statusBar().addPermanentWidget(self._loading_overlay)
        self.statusBar().addPermanentWidget(self._loading_spinner)
        self.statusBar().showMessage("Ready")
        width = self._coerce_int(self._ui_state.get("window_width"))
        height = self._coerce_int(self._ui_state.get("window_height"))
        if width and height:
            self.resize(width, height)

    def _connect_signals(self) -> None:
        self._open_action.triggered.connect(self._choose_directory)
        self._refresh_action.triggered.connect(self._refresh_directory)
        self._file_open_action.triggered.connect(self._choose_directory)
        self._file_refresh_action.triggered.connect(self._refresh_directory)
        self._file_quit_action.triggered.connect(self.close)
        self._edit_copy_path_action.triggered.connect(self._copy_selected_path)
        self._edit_copy_pattern_action.triggered.connect(self._copy_selected_pattern)
        self._edit_properties_action.triggered.connect(self._open_selected_properties)
        self._show_hidden_action.toggled.connect(self._toggle_show_hidden_files)
        self._preferences_action.triggered.connect(self._show_preferences_dialog)
        self._help_repo_action.triggered.connect(self._open_repo_page)
        self._help_about_action.triggered.connect(self._show_about_dialog)
        self._open_button.clicked.connect(self._choose_directory)
        self._refresh_button.clicked.connect(self._refresh_directory)
        self._menu_button.clicked.connect(self._show_toolbar_menu)
        self._sidebar_button.clicked.connect(self._toggle_sidebar_from_toolbar)
        self._back_button.clicked.connect(self._go_back)
        self._home_button.clicked.connect(self._go_home)
        self._up_button.clicked.connect(self._go_up)
        self._stop_button.clicked.connect(self._cancel_scan)
        self._content_mode_toggle.toggled.connect(self._toggle_content_mode)
        self._filter_input.textChanged.connect(self._apply_filter)
        self._filter_input.textChanged.connect(self._update_filter_clear_action)
        self._clear_filter_action.triggered.connect(self._clear_filter_text)
        self._table.itemSelectionChanged.connect(self._sync_inspector)
        self._table.itemDoubleClicked.connect(self._activate_selected_item)
        self._table.context_requested.connect(self._show_item_context_menu)
        self._table.filter_text_typed.connect(self._append_filter_text)
        self._table.filter_backspace_requested.connect(self._delete_filter_text)
        self._table.filter_clear_requested.connect(self._clear_filter_text)
        self._table.activate_current_requested.connect(self._activate_selected_item)
        self._table.navigate_up_requested.connect(self._go_up)
        self._icon_view.itemSelectionChanged.connect(self._sync_inspector)
        self._icon_view.itemActivated.connect(self._activate_selected_item)
        self._icon_view.context_requested.connect(self._show_item_context_menu)
        self._icon_view.filter_text_typed.connect(self._append_filter_text)
        self._icon_view.filter_backspace_requested.connect(self._delete_filter_text)
        self._icon_view.filter_clear_requested.connect(self._clear_filter_text)
        self._tree.selectionModel().selectionChanged.connect(
            self._handle_tree_selection
        )
        self._layout_mode_toggle.toggled.connect(self._toggle_layout_mode)
        self._tree_toggle.toggled.connect(self._toggle_sidebar)
        self._inspector.copy_path_button.clicked.connect(self._copy_selected_path)
        self._inspector.copy_pattern_button.clicked.connect(self._copy_selected_pattern)
        self._inspector.find_missing_button.clicked.connect(
            self._find_missing_for_selected_sequence
        )
        self._inspector.get_size_button.clicked.connect(
            self._get_size_for_selected_sequence
        )
        self._inspector.expand_button.clicked.connect(
            self._expand_or_collapse_selected_sequence
        )
        self._inspector.close_button.clicked.connect(self._close_inspector)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._pending_request = None
        if self._load_process is not None:
            self._load_process.kill()
            self._load_process.waitForFinished(500)
        self._save_ui_state()
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

    def _toggle_content_mode(self, sequence_view: bool) -> None:
        self._controller.set_grouped_view(sequence_view)
        self._content_mode_toggle.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_FileDialogDetailedView
                if sequence_view
                else QStyle.StandardPixmap.SP_FileIcon
            )
        )
        self._content_mode_toggle.setToolTip(
            "Sequence View" if sequence_view else "File View"
        )
        self._apply_filter(self._filter_input.text())

    def _toggle_layout_mode(self, detail_view: bool) -> None:
        self._layout_mode_toggle.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_FileDialogDetailedView
                if detail_view
                else QStyle.StandardPixmap.SP_FileDialogListView
            )
        )
        self._layout_mode_toggle.setToolTip(
            "Detail View" if detail_view else "Icon View"
        )
        self._center_stack.setCurrentWidget(
            self._table if detail_view else self._icon_view
        )
        self._save_ui_state()
        QTimer.singleShot(0, self._focus_active_browser)

    def _handle_tree_selection(self) -> None:
        index = self._tree.currentIndex()
        path = self._tree.filesystem_model.filePath(index)
        if path:
            self._focus_after_load = "tree"
            self._request_directory(path, add_to_history=True)

    def _request_directory(self, path: str | Path, add_to_history: bool) -> None:
        requested_path = str(self._normalize_path(path))
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
        except (
            TypeError,
            ValueError,
            KeyError,
            AttributeError,
            json.JSONDecodeError,
        ) as exc:
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
        if request[1]:
            self._push_history(str(result.path))
        self._active_request = None
        self._sync_tree_to_path(str(result.path))
        self._update_breadcrumbs(result.path)
        self._filter_input.clear()
        self._apply_filter("")
        if self._focus_after_load == "tree":
            QTimer.singleShot(0, self._focus_tree)
        else:
            QTimer.singleShot(0, self._focus_active_browser)
        self._focus_after_load = "browser"
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
        if not self._show_hidden_files:
            filtered = [item for item in filtered if not self._is_hidden_item(item)]

        self._visible_items = filtered
        self._table.set_items(filtered)
        self._icon_view.set_items(filtered)
        self._inspector.clear_details()
        self._update_status_bar()

    def _append_filter_text(self, text: str) -> None:
        if not text or not self._filter_input.isEnabled():
            return
        self._filter_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._filter_input.setText(self._filter_input.text() + text)
        self._filter_input.setCursorPosition(len(self._filter_input.text()))

    def _delete_filter_text(self) -> None:
        if not self._filter_input.isEnabled():
            return
        current = self._filter_input.text()
        if not current:
            return
        self._filter_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._filter_input.setText(current[:-1])
        self._filter_input.setCursorPosition(len(self._filter_input.text()))

    def _clear_filter_text(self) -> None:
        if not self._filter_input.isEnabled() or not self._filter_input.text():
            return
        self._filter_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._filter_input.clear()

    def _update_filter_clear_action(self, text: str) -> None:
        self._clear_filter_action.setVisible(bool(text))

    def _toggle_show_hidden_files(self, enabled: bool) -> None:
        self._show_hidden_files = enabled
        self._tree.set_show_hidden(enabled)
        self._apply_filter(self._filter_input.text())
        self._save_ui_state()

    def _show_toolbar_menu(self) -> None:
        menu = QMenu(self)
        file_menu = menu.addMenu("File")
        file_menu.addAction(self._file_open_action)
        file_menu.addAction(self._file_refresh_action)
        file_menu.addSeparator()
        file_menu.addAction(self._file_quit_action)

        edit_menu = menu.addMenu("Edit")
        edit_menu.addAction(self._edit_copy_path_action)
        edit_menu.addAction(self._edit_copy_pattern_action)
        edit_menu.addAction(self._edit_properties_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._show_hidden_action)
        edit_menu.addAction(self._preferences_action)

        help_menu = menu.addMenu("Help")
        help_menu.addAction(self._help_about_action)
        help_menu.addAction(self._help_repo_action)
        anchor = self._menu_button.mapToGlobal(self._menu_button.rect().bottomRight())
        menu_size = menu.sizeHint()
        menu.exec(anchor - QPoint(menu_size.width(), 0))

    def _show_preferences_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Preferences",
            "Preferences are currently stored in ~/.config/sview.\n\n"
            "More settings can be added here in a future pass.",
        )

    def _sync_inspector(self) -> None:
        item = self._current_browser_item()
        if item is None:
            self._inspector.clear_details()
            return
        self._inspector.set_item(item)
        if self._controller.expanded_sequence and item.item_type is ItemType.SEQUENCE:
            self._inspector.expand_button.setText("Collapse Sequence")

    def _activate_selected_item(self, *_args) -> None:
        item = self._current_browser_item()
        if item is None:
            return
        self._activate_item(item)

    def _expand_or_collapse_selected_sequence(self) -> None:
        item = self._inspector.current_item or self._current_browser_item()
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
        item = self._inspector.current_item or self._current_browser_item()
        if item is None:
            return
        QGuiApplication.clipboard().setText(item.path)
        self.statusBar().showMessage(f"Copied path for {item.display_name}", 3000)

    def _copy_selected_pattern(self) -> None:
        item = self._inspector.current_item or self._current_browser_item()
        if item is None or item.item_type is not ItemType.SEQUENCE:
            return
        QGuiApplication.clipboard().setText(item.display_name)
        self.statusBar().showMessage(f"Copied pattern {item.display_name}", 3000)

    def _find_missing_for_selected_sequence(self) -> None:
        item = self._inspector.current_item or self._current_browser_item()
        if item is None or item.item_type is not ItemType.SEQUENCE:
            return
        data = self._run_sstat_json(item)
        if data is None:
            return
        missing = self._coerce_missing_list(data.get("missing"))
        item.missing = missing or None
        self._table.update_item(item)
        self._inspector.set_item(item)
        self.statusBar().showMessage(
            f"Loaded missing-frame data for {item.display_name}", 3000
        )

    def _get_size_for_selected_sequence(self) -> None:
        item = self._inspector.current_item or self._current_browser_item()
        if item is None or item.item_type is not ItemType.SEQUENCE:
            return
        data = self._run_sstat_json(item)
        if data is None:
            return
        size_bytes = self._coerce_int(data.get("size_bytes")) or self._coerce_int(
            data.get("size")
        )
        if size_bytes is not None:
            item.size_bytes = size_bytes
        self._table.update_item(item)
        self._inspector.set_item(item)
        self._update_status_bar()
        self.statusBar().showMessage(f"Loaded size for {item.display_name}", 3000)

    def _open_selected_properties(self) -> None:
        item = self._inspector.current_item or self._current_browser_item()
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
            sequence_menu = menu.addMenu("Sequence")
            sstat_action = sequence_menu.addAction("sstat")
            scopy_action = sequence_menu.addAction("scopy...")
            smove_action = sequence_menu.addAction("smove...")

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
        data = self._run_sstat_json(item)
        if data is None:
            return
        text = self._format_sstat_output(json.dumps(data))
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
        normalized = str(self._normalize_path(path))
        root_index = self._tree.rootIndex()
        root_path = model.filePath(root_index)
        if root_path:
            try:
                Path(normalized).relative_to(Path(root_path))
            except ValueError:
                parent_path = str(Path(normalized).parent)
                parent_index = model.index(parent_path)
                if parent_index.isValid():
                    self._tree.setRootIndex(parent_index)
        index = model.index(normalized)
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
        self._content_mode_toggle.setEnabled(not loading)
        self._layout_mode_toggle.setEnabled(not loading)
        self._open_button.setEnabled(not loading)
        self._refresh_button.setEnabled(not loading)
        self._filter_input.setEnabled(not loading)
        self._tree.setEnabled(not loading)
        self._table.setEnabled(not loading)
        self._icon_view.setEnabled(not loading)
        self._stop_button.setEnabled(loading)
        self._loading_spinner.setVisible(loading)
        self._loading_overlay.setVisible(loading)
        if loading:
            self._loading_overlay.setText("Loading…")
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

    def _run_sstat_json(self, item: BrowserItem) -> dict[str, object] | None:
        executable = self._tool_path("sstat")
        if executable is None:
            return None
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
            return None
        try:
            return json.loads(completed.stdout.strip())
        except json.JSONDecodeError:
            QMessageBox.warning(
                self, "sstat failed", "Received invalid JSON from sstat."
            )
            return None

    @staticmethod
    def _coerce_int(value: object) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _coerce_missing_list(cls, value: object) -> list[int]:
        if not isinstance(value, list):
            return []
        frames: list[int] = []
        for item in value:
            if isinstance(item, list) and len(item) == 2:
                start = cls._coerce_int(item[0])
                end = cls._coerce_int(item[1])
                if start is None or end is None:
                    continue
                frames.extend(range(start, end + 1))
                continue
            coerced = cls._coerce_int(item)
            if coerced is not None:
                frames.append(coerced)
        return frames

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
        self._save_ui_state()

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

    def _save_ui_state(self) -> None:
        sidebar_width = self._sidebar_restore_width
        splitter_sizes = [self.SIDEBAR_WIDTH, 900, 0]
        if self._main_splitter is not None:
            sizes = self._main_splitter.sizes()
            splitter_sizes = list(sizes)
            if sizes and sizes[0] > 0:
                sidebar_width = sizes[0]
            elif self._sidebar_expanded:
                splitter_sizes[0] = sidebar_width
        state = {
            "window_width": self.width(),
            "window_height": self.height(),
            "main_splitter_sizes": splitter_sizes,
            "center_view": "icons"
            if not self._layout_mode_toggle.isChecked()
            else "details",
            "sidebar_expanded": self._sidebar_expanded,
            "sidebar_width": sidebar_width,
            "show_hidden_files": self._show_hidden_files,
        }
        try:
            save_ui_state(state)
        except OSError:
            pass

    @staticmethod
    def _coerce_splitter_sizes(value: object, default: list[int]) -> list[int]:
        if not isinstance(value, list) or len(value) != len(default):
            return list(default)
        sizes: list[int] = []
        for item in value:
            try:
                sizes.append(max(0, int(item)))
            except (TypeError, ValueError):
                return list(default)
        return sizes

    def _current_browser_item(self) -> BrowserItem | None:
        if self._center_stack.currentWidget() is self._icon_view:
            return self._icon_view.current_browser_item()
        return self._table.current_browser_item()

    def _focus_active_browser(self) -> None:
        widget = self._center_stack.currentWidget()
        if widget is not None and widget.isEnabled():
            widget.setFocus(Qt.FocusReason.OtherFocusReason)

    def _focus_tree(self) -> None:
        if self._tree.isEnabled():
            self._tree.setFocus(Qt.FocusReason.OtherFocusReason)

    def _update_breadcrumbs(self, path: Path) -> None:
        while self._breadcrumb_layout.count():
            item = self._breadcrumb_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        normalized = Path(path)
        parts = [normalized.anchor] if normalized.anchor else []
        parts.extend(part for part in normalized.parts[len(parts) :] if part)

        current_path = Path(parts[0]) if parts else normalized
        for index, part in enumerate(parts):
            if index > 0:
                separator = QLabel("/")
                separator.setObjectName("breadcrumbSeparator")
                self._breadcrumb_layout.addWidget(separator)
                current_path = current_path / part

            button = QToolButton()
            button.setObjectName("breadcrumbButton")
            button.setAutoRaise(True)
            button.setText(
                "Home" if current_path == Path.home() else part.rstrip("/") or "/"
            )
            button.setToolTip(str(current_path))
            button.clicked.connect(
                lambda _checked=False, target=str(
                    current_path
                ): self._request_directory(target, add_to_history=True)
            )
            self._breadcrumb_layout.addWidget(button)

        self._breadcrumb_layout.addStretch(1)

    @staticmethod
    def _is_hidden_item(item: BrowserItem) -> bool:
        return Path(item.path).name.startswith(".")

    def _toggle_sidebar(self, expanded: bool) -> None:
        self._apply_sidebar_state(expanded)
        self._save_ui_state()

    def _toggle_sidebar_from_toolbar(self) -> None:
        self._toggle_sidebar(not self._sidebar_expanded)

    def _apply_sidebar_state(self, expanded: bool) -> None:
        if self._main_splitter is None:
            self._sidebar_expanded = expanded
            return
        self._sidebar_expanded = expanded
        self._sidebar_button.setIcon(sidebar_icon(expanded, size=18))
        self._sidebar_button.setToolTip(
            "Collapse folders" if expanded else "Show folders"
        )
        self._tree_toggle.blockSignals(True)
        self._tree_toggle.setChecked(expanded)
        self._tree_toggle.blockSignals(False)
        self._tree_toggle.setArrowType(
            Qt.ArrowType.LeftArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._tree_toggle.setToolTip(
            "Collapse folders" if expanded else "Expand folders"
        )
        sizes = self._main_splitter.sizes()
        if len(sizes) < 3:
            return
        if expanded:
            target = min(self.SIDEBAR_WIDTH, max(220, self._sidebar_restore_width))
            current_sidebar = sizes[0]
            if current_sidebar <= 0:
                sizes[1] = max(0, sizes[1] - target)
            else:
                sizes[1] = max(0, sizes[1] + current_sidebar - target)
            sizes[0] = target
        else:
            if sizes[0] > 0:
                self._sidebar_restore_width = sizes[0]
            sizes[1] += sizes[0]
            sizes[0] = 0
        self._main_splitter.setSizes(sizes)

    def _open_repo_page(self) -> None:
        QDesktopServices.openUrl(QUrl(get_repository_url()))

    def _show_about_dialog(self) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("About sview")
        dialog.setText(f"sview {__version__}")
        dialog.setInformativeText("Sequence-aware filesystem browser.")
        icon_path = Path(__file__).with_name("sview_icon.png")
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                dialog.setIconPixmap(
                    pixmap.scaled(
                        96,
                        96,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        dialog.exec()

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

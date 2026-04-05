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
Contains the main application entry point for sview.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from sview import __version__
from sview.qt.main_window import MainWindow
from sview.scanner import ensure_pyseq_available


def main() -> int:
    if _wants_version(sys.argv[1:]):
        print(__version__)
        return 0

    debug = _wants_debug(sys.argv[1:])
    app = QApplication(sys.argv)
    try:
        ensure_pyseq_available()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        QMessageBox.critical(None, "sview", str(exc))
        return 1
    app.setApplicationName("sview")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    _apply_dark_theme(app)
    initial_path = _parse_initial_path(sys.argv[1:])
    window = MainWindow(initial_path=initial_path, debug=debug)
    window.show()
    return app.exec()


def _parse_initial_path(args: list[str]) -> str | None:
    filtered_args = [arg for arg in args if arg not in {"--version", "-V", "--debug"}]
    if not filtered_args:
        return None
    candidate = Path(filtered_args[0]).expanduser()
    return str(candidate)


def _wants_version(args: list[str]) -> bool:
    return any(arg in {"--version", "-V"} for arg in args)


def _wants_debug(args: list[str]) -> bool:
    return "--debug" in args


def _apply_dark_theme(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#14191e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#dbe2e8"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#11161b"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#171d22"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#11161b"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#f2f5f8"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#dbe2e8"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1f262d"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#edf2f7"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#313b44"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#75818d"))
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QWidget {
            font-size: 12px;
        }
        QTreeView, QTableWidget, QLineEdit, QPushButton, QLabel, QListWidget {
            background-color: #1e252c;
            color: #dbe2e8;
        }
        QMainWindow, QWidget#mainContent {
            background-color: #13191f;
            color: #dbe2e8;
        }
        QHeaderView::section {
            background-color: #1e252c;
            color: #d4dde4;
            padding: 4px 6px;
            border: 0;
            border-right: 1px solid #29333c;
        }
        QTreeView, QTableWidget, QLineEdit, QListWidget {
            background-color: #161d23;
            border: 1px solid #222c34;
            border-radius: 3px;
        }
        QTreeView {
            background-color: #171f26;
        }
        QScrollBar:vertical {
            background: #10161a;
            width: 10px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: #36424c;
            min-height: 28px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background: #414f5a;
        }
        QScrollBar:horizontal {
            background: #10161a;
            height: 10px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal {
            background: #36424c;
            min-width: 28px;
            border-radius: 4px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #414f5a;
        }
        QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
            background: transparent;
            border: none;
        }
        QTableWidget::item:selected, QTreeView::item:selected {
            background-color: #2c353d;
            color: white;
        }
        QPushButton {
            background-color: #20282f;
            border: 1px solid #29333c;
            border-radius: 3px;
            padding: 4px 9px;
            min-height: 24px;
        }
        QPushButton:checked {
            background-color: #2b3640;
            border-color: #34414d;
        }
        QPushButton:disabled {
            color: #697581;
            background-color: #1a2127;
        }
        QToolButton {
            background: transparent;
            border: 0;
            color: #83919e;
        }
        QToolButton:hover {
            color: #d6dde4;
        }
        QStatusBar {
            background-color: #141b20;
            color: #b6c1ca;
        }
        QSplitter::handle {
            background-color: #36414a;
            width: 1px;
        }
        QLabel#inspectorTitle {
            font-size: 16px;
            font-weight: 600;
        }
        QLabel#inspectorSubtitle {
            color: #8998a5;
            margin-bottom: 6px;
        }
        QWidget#iconCard {
            background-color: #1c232a;
            border: 1px solid #252f37;
            border-radius: 6px;
        }
        QWidget#iconCard:hover {
            background-color: #212a32;
            border-color: #2f3b45;
        }
        QLabel#iconCardTitle {
            font-size: 13px;
            font-weight: 600;
            color: #eef3f7;
        }
        QLabel#iconCardSubtitle {
            color: #99a8b3;
        }
        """
    )


if __name__ == "__main__":
    raise SystemExit(main())

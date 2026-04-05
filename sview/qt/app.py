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
    window = MainWindow(initial_path=initial_path)
    window.show()
    return app.exec()


def _parse_initial_path(args: list[str]) -> str | None:
    filtered_args = [arg for arg in args if arg not in {"--version", "-V"}]
    if not filtered_args:
        return None
    candidate = Path(filtered_args[0]).expanduser()
    return str(candidate)


def _wants_version(args: list[str]) -> bool:
    return any(arg in {"--version", "-V"} for arg in args)


def _apply_dark_theme(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#232528"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e4e6e8"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#191b1e"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#202327"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#191b1e"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#f2f3f5"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e4e6e8"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2c2f34"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#edf0f2"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#454b53"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#808790"))
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QWidget {
            font-size: 12px;
        }
        QMainWindow, QTreeView, QTableWidget, QLineEdit, QPushButton, QLabel {
            background-color: #25282c;
            color: #e4e6e8;
        }
        QHeaderView::section {
            background-color: #2d3136;
            color: #d9dde1;
            padding: 4px 6px;
            border: 0;
            border-right: 1px solid #3d4248;
        }
        QTreeView, QTableWidget, QLineEdit {
            background-color: #1d2024;
            border: 1px solid #30343a;
            border-radius: 3px;
        }
        QScrollBar:vertical {
            background: #1b1e22;
            width: 10px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: #474c53;
            min-height: 28px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background: #5a6068;
        }
        QScrollBar:horizontal {
            background: #1b1e22;
            height: 10px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal {
            background: #474c53;
            min-width: 28px;
            border-radius: 4px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #5a6068;
        }
        QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
            background: transparent;
            border: none;
        }
        QTableWidget::item:selected, QTreeView::item:selected {
            background-color: #40454d;
            color: white;
        }
        QPushButton {
            background-color: #2f3338;
            border: 1px solid #393e45;
            border-radius: 3px;
            padding: 4px 9px;
            min-height: 24px;
        }
        QPushButton:checked {
            background-color: #3b4047;
            border-color: #474d55;
        }
        QPushButton:disabled {
            color: #727881;
            background-color: #272b30;
        }
        QStatusBar {
            background-color: #1d2024;
            color: #bfc4ca;
        }
        QSplitter::handle {
            background-color: #4a4f56;
            width: 1px;
        }
        QLabel#inspectorTitle {
            font-size: 16px;
            font-weight: 600;
        }
        QLabel#inspectorSubtitle {
            color: #959ca5;
            margin-bottom: 6px;
        }
        """
    )


if __name__ == "__main__":
    raise SystemExit(main())

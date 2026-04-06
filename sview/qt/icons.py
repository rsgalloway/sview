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
Contains lightweight custom icons used throughout the sview UI.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from sview.model import BrowserItem, ItemType


def browser_item_icon(item: BrowserItem, size: int = 18) -> QIcon:
    if item.item_type is ItemType.DIRECTORY:
        return _folder_icon(size)
    if item.item_type is ItemType.SEQUENCE:
        return _sequence_icon(size)
    return _file_icon(size)


def sidebar_icon(expanded: bool, size: int = 18) -> QIcon:
    return _sidebar_icon(expanded, size)


@lru_cache(maxsize=12)
def _folder_icon(size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    tab = QColor("#cf6b6b")
    body = QColor("#9e4b53")
    painter.setBrush(tab)
    painter.drawRoundedRect(
        QRectF(size * 0.12, size * 0.20, size * 0.34, size * 0.20), 2, 2
    )
    painter.setBrush(body)
    painter.drawRoundedRect(
        QRectF(size * 0.08, size * 0.30, size * 0.84, size * 0.48), 2.5, 2.5
    )
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=12)
def _file_icon(size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#ced6de"), 1))
    painter.setBrush(QColor("#f2f5f8"))

    page = QPainterPath()
    page.moveTo(size * 0.22, size * 0.10)
    page.lineTo(size * 0.62, size * 0.10)
    page.lineTo(size * 0.78, size * 0.26)
    page.lineTo(size * 0.78, size * 0.88)
    page.lineTo(size * 0.22, size * 0.88)
    page.closeSubpath()
    painter.drawPath(page)

    fold = QPainterPath()
    fold.moveTo(size * 0.62, size * 0.10)
    fold.lineTo(size * 0.62, size * 0.26)
    fold.lineTo(size * 0.78, size * 0.26)
    fold.closeSubpath()
    painter.fillPath(fold, QColor("#dde5eb"))
    painter.drawPath(fold)
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=12)
def _sequence_icon(size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#d8e0e7"), 1))
    painter.setBrush(QColor("#f3f6f9"))

    page = QPainterPath()
    page.moveTo(size * 0.18, size * 0.10)
    page.lineTo(size * 0.68, size * 0.10)
    page.lineTo(size * 0.82, size * 0.24)
    page.lineTo(size * 0.82, size * 0.90)
    page.lineTo(size * 0.18, size * 0.90)
    page.closeSubpath()
    painter.drawPath(page)

    fold = QPainterPath()
    fold.moveTo(size * 0.68, size * 0.10)
    fold.lineTo(size * 0.68, size * 0.24)
    fold.lineTo(size * 0.82, size * 0.24)
    fold.closeSubpath()
    painter.fillPath(fold, QColor("#dde6ec"))
    painter.drawPath(fold)

    painter.setPen(QPen(QColor("#2f3b46"), max(1, size // 14)))
    for offset in (0.34, 0.50, 0.66):
        painter.drawLine(
            QPointF(size * 0.28, size * offset),
            QPointF(size * 0.72, size * offset),
        )

    badge = QRectF(size * 0.18, size * 0.70, size * 0.30, size * 0.16)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#4d8fb5"))
    painter.drawRoundedRect(badge, 2, 2)
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=24)
def _sidebar_icon(expanded: bool, size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    outer = QRectF(size * 0.10, size * 0.16, size * 0.80, size * 0.68)
    sidebar = QRectF(size * 0.14, size * 0.20, size * 0.20, size * 0.60)
    content = QRectF(size * 0.38, size * 0.20, size * 0.48, size * 0.60)

    painter.setBrush(QColor("#24303a"))
    painter.drawRoundedRect(outer, 2.5, 2.5)
    painter.setBrush(QColor("#d16f6f") if expanded else QColor("#485663"))
    painter.drawRoundedRect(sidebar, 2, 2)
    painter.setBrush(QColor("#d8e0e7"))
    painter.drawRoundedRect(content, 2, 2)

    painter.setPen(QPen(QColor("#34414c"), max(1, size // 16)))
    if expanded:
        painter.drawLine(
            QPointF(size * 0.24, size * 0.42),
            QPointF(size * 0.18, size * 0.50),
        )
        painter.drawLine(
            QPointF(size * 0.18, size * 0.50),
            QPointF(size * 0.24, size * 0.58),
        )
    else:
        painter.drawLine(
            QPointF(size * 0.18, size * 0.42),
            QPointF(size * 0.24, size * 0.50),
        )
        painter.drawLine(
            QPointF(size * 0.24, size * 0.50),
            QPointF(size * 0.18, size * 0.58),
        )
    painter.end()
    return QIcon(pixmap)

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
Contains the DirectoryTree widget for displaying the directory structure.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir
from PySide6.QtWidgets import QFileSystemModel, QTreeView


class DirectoryModel(QFileSystemModel):
    def hasChildren(self, parent) -> bool:  # type: ignore[override]
        if not parent.isValid():
            return True

        file_info = self.fileInfo(parent)
        if not file_info.isDir():
            return False

        directory = QDir(file_info.absoluteFilePath())
        children = directory.entryList(QDir.AllDirs | QDir.NoDotAndDotDot)
        return bool(children)


class DirectoryTree(QTreeView):
    def __init__(self, root_path: str | Path) -> None:
        super().__init__()
        self._model = DirectoryModel(self)
        self._model.setRootPath(str(root_path))
        self._model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        self.setModel(self._model)
        self.setRootIndex(self._model.index(str(root_path)))
        self.setUniformRowHeights(True)

        for column in range(1, self._model.columnCount()):
            self.hideColumn(column)

    @property
    def filesystem_model(self) -> QFileSystemModel:
        return self._model

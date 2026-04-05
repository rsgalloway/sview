from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sview.controller import BrowserController
from sview.model import ItemType
from sview.scanner import DirectoryScanner, ScanResult


def _touch(path: Path) -> None:
    path.write_text("x", encoding="utf-8")


class DirectoryScannerTests(unittest.TestCase):
    def test_sequence_grouping_and_missing_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _touch(root / "shotA.1001.exr")
            _touch(root / "shotA.1002.exr")
            _touch(root / "shotA.1004.exr")
            _touch(root / "notes.txt")

            result = DirectoryScanner().scan(root)

            self.assertEqual(len(result.raw_items), 4)

            sequence = next(
                item
                for item in result.grouped_items
                if item.item_type is ItemType.SEQUENCE
            )
            self.assertEqual(sequence.display_name, "shotA.%04d.exr")
            self.assertEqual(sequence.frame_range, "1001-1004")
            self.assertEqual(sequence.count, 3)
            self.assertIsNone(sequence.missing)
            self.assertEqual(
                sequence.child_paths,
                [
                    str(root / "shotA.1001.exr"),
                    str(root / "shotA.1002.exr"),
                    str(root / "shotA.1004.exr"),
                ],
            )

            single = next(
                item for item in result.grouped_items if item.item_type is ItemType.FILE
            )
            self.assertEqual(single.name, "notes.txt")

    def test_single_numbered_file_stays_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _touch(root / "plate.0001.jpg")

            result = DirectoryScanner().scan(root)

            self.assertEqual(len(result.grouped_items), 1)
            self.assertIs(result.grouped_items[0].item_type, ItemType.FILE)

    def test_controller_can_expand_and_collapse_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _touch(root / "plate.0001.jpg")
            _touch(root / "plate.0002.jpg")
            _touch(root / "plate.0003.jpg")

            controller = BrowserController(scanner=DirectoryScanner())
            grouped_items = controller.load_path(root)
            sequence = next(
                item for item in grouped_items if item.item_type is ItemType.SEQUENCE
            )

            expanded_items = controller.expand_sequence(sequence)
            self.assertEqual(
                [item.name for item in expanded_items],
                ["plate.0001.jpg", "plate.0002.jpg", "plate.0003.jpg"],
            )

            collapsed_items = controller.collapse_sequence()
            self.assertEqual(len(collapsed_items), 1)
            self.assertIs(collapsed_items[0].item_type, ItemType.SEQUENCE)

    def test_scan_result_round_trip_serialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _touch(root / "plate.0001.jpg")
            _touch(root / "plate.0002.jpg")

            result = DirectoryScanner().scan(root)
            restored = ScanResult.from_dict(result.to_dict())

            self.assertEqual(restored.path, result.path)
            self.assertEqual(
                [item.display_name for item in restored.grouped_items],
                [item.display_name for item in result.grouped_items],
            )
            self.assertEqual(
                [item.path for item in restored.raw_items],
                [item.path for item in result.raw_items],
            )


if __name__ == "__main__":
    unittest.main()

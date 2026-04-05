from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sview import config as config_module
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

    def test_sequence_range_handles_frame_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _touch(root / "plate.0000.jpg")
            _touch(root / "plate.0001.jpg")

            result = DirectoryScanner().scan(root)

            sequence = next(
                item
                for item in result.grouped_items
                if item.item_type is ItemType.SEQUENCE
            )
            self.assertEqual(sequence.frame_range, "0-1")

    def test_directory_symlink_stays_a_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target"
            target.mkdir()
            link = root / "linked-target"
            link.symlink_to(target, target_is_directory=True)

            result = DirectoryScanner().scan(root)

            linked_item = next(
                item for item in result.raw_items if item.name == link.name
            )
            self.assertIs(linked_item.item_type, ItemType.DIRECTORY)
            self.assertEqual(linked_item.path, str(link))

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


class AppConfigTests(unittest.TestCase):
    def test_load_tolerates_invalid_worker_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            config_path = config_dir / "config.json"
            ui_state_path = config_dir / "ui_state.json"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                """
{
  "scanner": {
    "worker": {
      "nice_increment": "not-a-number",
      "memory_limit_mb": "also-bad",
      "timeout_seconds": "still-bad"
    }
  }
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            original_dir = config_module.CONFIG_DIR
            original_config_path = config_module.CONFIG_PATH
            original_ui_state_path = config_module.UI_STATE_PATH
            config_module.CONFIG_DIR = config_dir
            config_module.CONFIG_PATH = config_path
            config_module.UI_STATE_PATH = ui_state_path
            try:
                loaded = config_module.AppConfig.load()
            finally:
                config_module.CONFIG_DIR = original_dir
                config_module.CONFIG_PATH = original_config_path
                config_module.UI_STATE_PATH = original_ui_state_path

            self.assertEqual(loaded.scan_worker.nice_increment, 15)
            self.assertIsNone(loaded.scan_worker.memory_limit_mb)
            self.assertEqual(loaded.scan_worker.timeout_seconds, 30)


if __name__ == "__main__":
    unittest.main()

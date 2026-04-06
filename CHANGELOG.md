# Changelog

## 0.2.1 - 2026-04-05

- Added a packaged application icon and surfaced it in the About dialog
- Continued browser polish around hidden-file controls and tree navigation behavior

## 0.2.0 - 2026-04-05

- Refined the desktop UI with a darker theme, tighter toolbar, custom item icons, and cleaner loading feedback
- Added icon and detail browsing improvements including type-to-filter, breadcrumbs, and better context menu organization
- Enhanced the Properties panel with responsive image thumbnails, scrolling content, and on-demand sequence actions
- Improved path handling for symlinked directories and polished overall navigation, search, and panel behavior

## 0.1.2 - 2026-04-05

- Moved directory scanning into a subprocess worker for safer cancellation
- Added scan worker guardrails including priority, memory, and timeout controls
- Improved scan error reporting with dialogs and optional `--debug` terminal output
- Disabled the default worker memory cap to avoid false positives on normal scans

## 0.1.1 - 2026-04-05

- Improved scanner responsiveness and stop/cancel behavior
- Switched sequence scanning to require pyseq without fallback grouping
- Continued UI and interaction polish across navigation, menus, and toolbar controls

## 0.1.0 - 2026-04-05

- Initial desktop release of `sview`
- Sequence-aware directory browsing with grouped and raw file views
- Folder tree, table view, properties panel, and context menus
- Background scanning, cancellation support, and basic sequence actions
- CLI support for opening a starting folder and printing the app version

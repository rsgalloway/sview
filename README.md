# sview

`sview` is a sequence-aware filesystem browser built with PySide6 and `pyseq`.
It provides a sequence-first view of directories so image sequences can be
browsed as logical units instead of individual files.

![sview screenshot](sview.png)

## Install

```bash
pip install -U sview
```

## Run

Launch the app:

```bash
sview
```

Open a specific folder:

```bash
sview /mnt/projects/
```

Print the version:

```bash
sview --version
```

## Configuration

On first launch, `sview` writes a user config file to:

```bash
~/.config/sview/config.json
```

This file controls default file and sequence handlers, including custom
commands for double-click actions.

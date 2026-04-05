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
Runs directory scans in a subprocess and emits JSON results for the main UI.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

try:
    import resource
except ImportError:  # pragma: no cover - platform-dependent
    resource = None

from sview.config import AppConfig
from sview.scanner import DirectoryScanner


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    debug = False
    if "--debug" in args:
        debug = True
        args = [arg for arg in args if arg != "--debug"]

    if len(args) != 1:
        print("Usage: python -m sview.worker [--debug] <path>", file=sys.stderr)
        return 2

    path = args[0]
    config = AppConfig.load()
    _apply_worker_limits(config, debug=debug)
    scanner = DirectoryScanner()
    try:
        result = scanner.scan(path, progress_callback=_emit_progress)
    except MemoryError:
        print(
            "ERROR: scan worker exceeded its configured memory limit.",
            file=sys.stderr,
            flush=True,
        )
        if debug:
            traceback.print_exc(file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        if debug:
            traceback.print_exc(file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(result.to_dict()))
    sys.stdout.flush()
    return 0


def _emit_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _apply_worker_limits(config: AppConfig, debug: bool = False) -> None:
    worker = config.scan_worker

    if worker.nice_increment:
        try:
            os.nice(worker.nice_increment)
            if debug:
                print(
                    f"[sview scan] applied nice increment {worker.nice_increment}",
                    file=sys.stderr,
                    flush=True,
                )
        except (AttributeError, OSError):  # pragma: no cover - platform-dependent
            if debug:
                print(
                    "[sview scan] could not adjust process priority",
                    file=sys.stderr,
                    flush=True,
                )

    if resource is None or worker.memory_limit_mb is None:
        return

    limit_bytes = int(worker.memory_limit_mb) * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        if debug:
            print(
                f"[sview scan] applied memory limit {worker.memory_limit_mb} MB",
                file=sys.stderr,
                flush=True,
            )
    except (OSError, ValueError):  # pragma: no cover - platform-dependent
        if debug:
            print(
                "[sview scan] could not apply memory limit",
                file=sys.stderr,
                flush=True,
            )


if __name__ == "__main__":
    raise SystemExit(main())

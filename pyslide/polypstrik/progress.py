# -*- coding: utf-8 -*-
""" Terminal progress helpers for PolypStrik upload, poll, and download."""

from __future__ import annotations

import sys
import time


__all__ = [
    "NullBar",
    "PollReporter",
    "ProgressFile",
    "download_bar",
    "extract_progress_pct",
    "format_elapsed",
    "resolve_progress",
    "upload_bar",
]


def resolve_progress(progress):
    """ Resolve whether progress UI should run.

    ``None`` means on when stderr is a TTY; ``True`` or ``False`` force on or off.
    """
    if progress is False:
        return False
    if progress is True:
        return True
    try:
        return bool(sys.stderr.isatty())
    except Exception:
        return False


def format_elapsed(seconds):
    """ Format seconds as ``Xm YYs`` or ``Hh Xm YYs``."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


class NullBar:
    """ No-op stand-in when progress is disabled or tqdm is missing."""

    def update(self, n=1):
        return None

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def _make_tqdm(total, desc, unit="B"):
    """ Build a tqdm bar, or ``NullBar`` if tqdm is unavailable."""
    try:
        from tqdm import tqdm
    except ImportError:
        return _FallbackBar(total=total, desc=desc)

    return tqdm(
        total=total if total and total > 0 else None,
        desc=desc,
        unit=unit,
        unit_scale=True if unit == "B" else False,
        unit_divisor=1024 if unit == "B" else 1000,
        file=sys.stderr,
        leave=True,
        mininterval=0.2,
    )


class _FallbackBar:
    """ Simple stderr percent reporter when tqdm is not installed."""

    def __init__(self, total=None, desc=""):
        self.total = total if total and total > 0 else None
        self.desc = desc or "progress"
        self.n = 0
        self._last_pct = -1
        self._start = time.monotonic()

    def update(self, n=1):
        self.n += n
        if self.total:
            pct = int(100 * self.n / self.total)
            if pct == self._last_pct and self.n < self.total:
                return
            self._last_pct = pct
            msg = (
                f"\r{self.desc}: {pct}% "
                f"({self.n}/{self.total}) "
                f"[{format_elapsed(time.monotonic() - self._start)}]"
            )
        else:
            msg = (
                f"\r{self.desc}: {self.n} bytes "
                f"[{format_elapsed(time.monotonic() - self._start)}]"
            )
        sys.stderr.write(msg)
        sys.stderr.flush()

    def close(self):
        sys.stderr.write("\n")
        sys.stderr.flush()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def upload_bar(filename, total, *, enabled=True):
    """ Return a progress bar for an upload, or ``NullBar`` if disabled."""
    if not enabled:
        return NullBar()
    return _make_tqdm(total, desc=f"Uploading {filename}", unit="B")


def download_bar(filename, total, *, enabled=True):
    """ Return a progress bar for a download, or ``NullBar`` if disabled."""
    if not enabled:
        return NullBar()
    return _make_tqdm(total, desc=f"Downloading {filename}", unit="B")


class ProgressFile:
    """ File wrapper that advances a progress bar as ``requests`` reads bytes."""

    def __init__(self, fh, bar):
        self._fh = fh
        self._bar = bar or NullBar()

    @property
    def name(self):
        return getattr(self._fh, "name", "upload.bin")

    def read(self, size=-1):
        data = self._fh.read(size)
        if data:
            self._bar.update(len(data))
        return data

    def seek(self, offset, whence=0):
        return self._fh.seek(offset, whence)

    def tell(self):
        return self._fh.tell()

    def close(self):
        return self._fh.close()

    def __iter__(self):
        return self

    def __next__(self):
        data = self.read(1024 * 1024)
        if not data:
            raise StopIteration
        return data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def extract_progress_pct(payload):
    """ Return 0..100 from a status payload if the server sends one, else None."""
    if not isinstance(payload, dict):
        return None
    for key in ("progress", "percent", "percentage", "pct"):
        val = payload.get(key)
        if val is None:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        # Allow 0..1 fractions as well as 0..100.
        if 0.0 <= num <= 1.0:
            num *= 100.0
        if 0.0 <= num <= 100.0:
            return num
    return None


class PollReporter:
    """ Live processing progress while waiting for analysis.

    Uses a tqdm bar when available. If the status payload includes a
    percentage, the bar is determinate (0 to 100). Otherwise it runs as an
    indeterminate spinner (the server usually only sends pending/processing).
    """

    def __init__(self, *, enabled=True):
        self.enabled = bool(enabled)
        self._start = time.monotonic()
        self._last_len = 0
        self._closed = False
        self._bar = None
        self._determinate = False
        self._fallback = False
        if not self.enabled:
            return
        try:
            from tqdm import tqdm

            self._bar = tqdm(
                total=None,
                desc="Processing",
                unit="check",
                file=sys.stderr,
                leave=True,
                mininterval=0.2,
                # Keep postfix on our terms (avoid tqdm's leading ", ").
                bar_format=(
                    "{desc}: {bar} {n_fmt} checks | {elapsed}{postfix}"
                ),
            )
        except ImportError:
            self._fallback = True

    @property
    def elapsed(self):
        return time.monotonic() - self._start

    def _set_postfix(self, status, next_in=None, pct=None):
        status = status if status is not None else "unknown"
        parts = [f"status={status}"]
        if pct is not None:
            parts.append(f"{pct:.0f}%")
        if next_in is not None:
            parts.append(f"next={int(max(next_in, 0))}s")
        # Leading " | " so bar_format can append cleanly.
        return " | " + ", ".join(parts)

    def _ensure_bar_mode(self, pct):
        """ Switch to a 0-100 bar once the server reports a percentage."""
        if self._bar is None or pct is None or self._determinate:
            return
        try:
            from tqdm import tqdm
        except ImportError:
            return
        # Replace indeterminate spinner with a percent bar.
        self._bar.close()
        self._bar = tqdm(
            total=100,
            desc="Processing",
            unit="%",
            file=sys.stderr,
            leave=True,
            mininterval=0.2,
            bar_format=(
                "{desc}: {percentage:3.0f}%|{bar}| {elapsed}{postfix}"
            ),
        )
        self._determinate = True

    def update(self, status, *, next_in=None, payload=None, tick=False):
        if not self.enabled or self._closed:
            return
        pct = extract_progress_pct(payload)
        postfix = self._set_postfix(status, next_in=next_in, pct=pct)

        if self._bar is not None:
            self._ensure_bar_mode(pct)
            if self._determinate and pct is not None:
                # Move bar to reported percent (never go backwards).
                target = int(pct)
                delta = max(0, target - int(self._bar.n))
                if delta:
                    self._bar.update(delta)
            elif tick:
                self._bar.update(1)
            self._bar.set_postfix_str(postfix, refresh=True)
            return

        if not self._fallback:
            return
        parts = [
            f"Status: {status if status is not None else 'unknown'}",
            f"elapsed {format_elapsed(self.elapsed)}",
        ]
        if pct is not None:
            parts.append(f"{pct:.0f}%")
        if next_in is not None:
            parts.append(f"next check in {int(max(next_in, 0))}s")
        line = " | ".join(parts)
        pad = max(0, self._last_len - len(line))
        sys.stderr.write("\r" + line + (" " * pad))
        sys.stderr.flush()
        self._last_len = len(line)

    def close(self, final_status=None):
        if not self.enabled or self._closed:
            return
        self._closed = True
        if self._bar is not None:
            if final_status is not None:
                self._bar.set_postfix_str(
                    self._set_postfix(final_status), refresh=False
                )
            if self._determinate and self._bar.n < self._bar.total:
                self._bar.update(self._bar.total - self._bar.n)
            self._bar.close()
            self._bar = None
            return
        if self._fallback:
            if final_status is not None:
                line = (
                    f"Status: {final_status} | "
                    f"elapsed {format_elapsed(self.elapsed)}"
                )
                pad = max(0, self._last_len - len(line))
                sys.stderr.write("\r" + line + (" " * pad) + "\n")
            elif self._last_len:
                sys.stderr.write("\n")
            sys.stderr.flush()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

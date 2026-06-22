from __future__ import annotations

from typing import Optional, Tuple


def compute_attendance_rate(attended: int, no_show: int) -> Optional[float]:
    total = int(attended) + int(no_show)
    if total <= 0:
        return None
    return round(attended * 100.0 / total, 1)


def attendance_counts(attended: int, no_show: int) -> Tuple[int, int, Optional[float]]:
    attended_i = int(attended)
    no_show_i = int(no_show)
    return attended_i, no_show_i, compute_attendance_rate(attended_i, no_show_i)

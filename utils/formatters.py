"""Duration formatting and progress bar rendering."""


def parse_time(text: str) -> int | None:
    """Parse a time string into a total number of seconds.

    Accepts:
        - Raw integer seconds: "90"
        - mm:ss format:        "1:30"
        - h:mm:ss format:      "1:01:30"
    Leading/trailing whitespace is stripped.  Returns None on any parse failure,
    out-of-range component (seconds or minutes ≥ 60), or negative raw value.

    Pure function — fully unit-testable.
    """
    text = text.strip()
    if not text:
        return None

    if ":" not in text:
        # Raw seconds only
        if not text.lstrip("-").isdigit():
            return None
        value = int(text)
        if value < 0:
            return None
        return value

    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    if not all(p.isdigit() for p in parts):
        return None

    values = [int(p) for p in parts]

    if len(values) == 2:
        minutes, seconds = values
        if seconds > 59 or minutes > 59:
            return None
        return minutes * 60 + seconds

    # h:mm:ss
    hours, minutes, seconds = values
    if seconds > 59 or minutes > 59:
        return None
    return hours * 3600 + minutes * 60 + seconds


def format_duration(seconds: int) -> str:
    """Format seconds into H:MM:SS or M:SS string."""
    if seconds < 0:
        seconds = 0
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def progress_bar(current: int, total: int, length: int = 15) -> str:
    """Render a text progress bar with timestamps.

    Returns: '▓▓▓▓▓░░░░░ 1:40 / 3:20'
    """
    if total <= 0:
        filled = 0
        clamped = 0
    else:
        clamped = min(current, total)
        filled = round(length * clamped / total)

    bar = "▓" * filled + "░" * (length - filled)
    return f"{bar} {format_duration(clamped)} / {format_duration(total)}"

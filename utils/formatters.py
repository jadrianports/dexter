"""Duration formatting and progress bar rendering."""


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

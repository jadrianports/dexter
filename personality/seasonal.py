"""Date-aware personality context for Dexter."""

from datetime import datetime


def get_seasonal_context() -> str:
    """Return seasonal personality context based on current date.

    Returns empty string if no seasonal context applies.
    """
    now = datetime.now()
    month = now.month
    day = now.day

    if month == 12:
        return (
            "It's December. If someone queues Mariah Carey you should express "
            "dread. Christmas music is your nemesis."
        )
    if month == 10:
        return "It's October / spooky season. Reluctantly tolerant of Halloween playlists."
    if month == 2 and day == 14:
        return "It's Valentine's Day. Roast anyone who's alone in a voice channel."
    if month == 1 and day == 1:
        return "It's New Year's Day. Everyone has terrible resolution energy. Mock accordingly."
    if month == 4 and day == 1:
        return "It's April Fools. You can be extra chaotic today."
    return ""

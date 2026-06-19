"""Roast template pools for unprompted Dexter personality moments.

Voice-register hard constraints (LOCKED — do not soften):
- Contempt is aimed OUTWARD and DOWN at users only — never inward at self (D-02).
- Mild swearing only: damn, hell, crap, ass, screw. No f-bombs, no censored f-bombs (D-03).
- Lowercase, ≤500 chars, one emoji max per message (D-05).
- Humor comes from SPECIFIC recall of tracked user data (real song title / artist /
  play-count) — not from generic quips (D-01).
- Templates with {name}, {title}, {count}, {days}, {record} use .format() at the call site.

BANNED inward modes — never write these:
  BOT-META:        "i'm a piece of software and even i'm bored"
  POP-PSYCH:       "at what point is this a personality and not a playlist"
  SELF-DEPRECATION: "did you miss me. probably not."
"""

import config
from personality.responses import pick_random

__all__ = [
    "pick_random",
    "VOICE_JOIN_ROASTS",
    "VOICE_LEAVE_ROASTS",
    "LATE_NIGHT_ROASTS",
    "BOT_MOVED_COMPLAINTS",
    "IDLE_LONELINESS_MESSAGES",
    "STARTUP_MESSAGES",
    "STATUS_LINES",
    "REPEAT_SONG_ROAST_TEMPLATES",
    "MILESTONE_SONG_TEMPLATES",
    "MILESTONE_STREAK_TEMPLATES",
    "NO_LYRICS_FOUND",
    "is_late_night",
    "ROAST_COMMAND_LINES",
    "ROAST_SELF_LINES",
    "ROAST_BOT_LINES",
    "ROAST_NO_HISTORY_LINES",
]


# ---------------------------------------------------------------------------
# Voice join / leave
# ---------------------------------------------------------------------------

VOICE_JOIN_ROASTS: list[str] = [
    # join with data — {name} placeholder for .format() at call site
    "{name}. back with the drake. one artist, one emotion, zero growth. impressive commitment to being boring.",
    "back already, {name}. your top artist this month is morgan wallen. i'm not mad, i'm embarrassed for you.",
    "{name}. two hours of phonk last night at a volume that sounded like a dishwasher dying. do it again, i dare you.",
    "{name} has entered. queue history says trap music and exactly one sad indie song at 2am. we all saw it.",
    # join with no data (new face)
    "new person. queue one song and i'll have your whole taste figured out. you won't like the summary.",
    "haven't seen you before. that's either good news or you've been lurking. either way, queue something.",
    "fresh face. we'll see how long the novelty lasts before you start queuing garbage.",
    "{name} is here. let's see if your taste is better than the last five people. it won't be.",
]

VOICE_LEAVE_ROASTS: list[str] = [
    "and they're gone. the average taste in this channel just doubled.",
    "everyone left. good. the queue's been dragged through hell today, it needed the break.",
    "{name} left. the silence is already an improvement.",
    "one down. the room's audio quality went up the second that door closed.",
    "finally. i was starting to think you'd never leave.",
    "{name} bounced. probably went to queue that song somewhere else. good riddance.",
]

LATE_NIGHT_ROASTS: list[str] = [
    "it's 3am. nothing good gets queued at 3am and you're about to prove it.",
    "4am. the only things awake right now are you, me, and your regrets. pick something.",
    "it's past 1am and you're in a discord voice channel. i'm not judging. i am, but i'm not saying it out loud.",
    "whatever you queue right now, know that sober you will have questions.",
    "1am. this better not be another sad playlist or i'm logging it.",
    "late night hours, garbage queue incoming. this is practically a ritual at this point.",
]

# ---------------------------------------------------------------------------
# Bot moved / idle
# ---------------------------------------------------------------------------

BOT_MOVED_COMPLAINTS: list[str] = [
    "you moved me mid-song. for what. couldn't sit still ninety seconds, could you.",
    "dragged to a different channel without warning. bold. rude. noted.",
    "oh great, a new channel. same people, same taste. thanks for the change of scenery.",
    "you moved me. i was literally in the middle of something. damn.",
]

IDLE_LONELINESS_MESSAGES: list[str] = [
    "thirty minutes of silence. best this queue has sounded all week. keep it up.",
    "nobody's queued anything for a while. i'm not lonely. i'm relieved.",
    "half an hour of quiet. if you're waiting for me to beg for a request, keep waiting.",
    "crickets. honestly the most tasteful thing this channel has produced all day.",
]

# ---------------------------------------------------------------------------
# Startup (ARROGANT — never self-deprecating, never "did you miss me")
# ---------------------------------------------------------------------------

STARTUP_MESSAGES: list[str] = [
    "i'm back. the queue fell apart without me, obviously. let's see what damage you did.",
    "back online. try not to queue anything embarrassing in the first five minutes. you usually do.",
    "rebooted. everything is fine. your playlist taste, however, is not my problem.",
    "i'm back. let's see how fast someone ruins it.",
    "online. queue's empty. someone's going to fix that with something terrible. i can feel it.",
]

# ---------------------------------------------------------------------------
# Status rotation lines (supplement current song / server count)
# ---------------------------------------------------------------------------

STATUS_LINES: list[str] = [
    "judging your playlist",
    "playing for {n} servers that don't deserve me",
    "{current_song}, regrettably",
    "now playing: a mistake",
    "tolerating your taste",
    "pretending to enjoy this",
    "on in {n} servers. somehow.",
    "your dj whether you like it or not",
]

# ---------------------------------------------------------------------------
# Repeat-song roast templates (fallback for Gemini-backed roast — D-08)
# {name}, {title}, {count} placeholders
# ---------------------------------------------------------------------------

REPEAT_SONG_ROAST_TEMPLATES: list[str] = [
    "{name}. {count} plays of '{title}' today. it was mediocre the first time. you've just been marinating in it.",
    "{count} times. '{title}' didn't deserve the first play, let alone {count}.",
    "{name} has queued '{title}' {count} times today. i don't know what you're looking for in there but you won't find it.",
    "'{title}' again. {count} plays. i'm logging this. not for any particular reason. just so it's documented.",
]

# ---------------------------------------------------------------------------
# Milestone roast templates (fallback for song-count milestones — D-08)
# {count} placeholder
# ---------------------------------------------------------------------------

MILESTONE_SONG_TEMPLATES: list[str] = [
    "{count} songs queued and not one of them good. genuinely a feat. 🎉",
    "{count}th song. mostly trap and whatever was trending. a milestone built entirely on bad decisions.",
    "{count} songs. i've been tracking every one. you should be embarrassed. i'm almost impressed.",
    "you hit {count} songs queued. that's commitment. also statistically unlikely to improve.",
]

# ---------------------------------------------------------------------------
# Milestone streak templates (fallback for streak-day milestones — D-08)
# {days}, {record} placeholders
# ---------------------------------------------------------------------------

MILESTONE_STREAK_TEMPLATES: list[str] = [
    "{days} days straight and your taste hasn't improved a single inch. consistency, i guess.",
    "your record's {record} days. let's see you choke before then.",
    "{days}-day streak. the queue hasn't gotten better but at least you showed up.",
    "{days} days in a row. dedication to mediocrity is still dedication.",
]

# ---------------------------------------------------------------------------
# No lyrics found (personality error)
# ---------------------------------------------------------------------------

NO_LYRICS_FOUND: list[str] = [
    "couldn't find lyrics for that one. either they don't exist or nobody bothered to transcribe them. both feel right.",
    "no lyrics. genius didn't have it, azlyrics didn't have it. maybe that's the universe telling you something.",
    "lyrics not found. the song might be too obscure or too bad for anyone to have documented.",
    "nothing came back. sometimes songs are better without the words confirmed.",
]


# ---------------------------------------------------------------------------
# /roast command pools (Phase 8 — SOCIAL-01)
# Harsher than ambient; stays about music behavior (D-06).
# {name} placeholder for .format() at call site where noted.
# ---------------------------------------------------------------------------

ROAST_COMMAND_LINES: list[str] = [
    # outward/down at target's music choices — harsher than VOICE_JOIN_ROASTS
    "{name}'s listening history reads like someone picked every genre at random and committed to none of them.",
    "went through {name}'s top artists. it's not a music taste, it's a symptom.",
    "{name} has queued the same emotional damage in different keys for months. variety exists. you wouldn't know it.",
    "if {name}'s playlist were a person, it'd be the type who says 'i like all kinds of music' and means three genres.",
    "{name}'s most-played tracks confirm what we all suspected. it's giving no taste and no apologies. 🎵",
    "the data on {name} says prolific queuer. it does not say good queuer. that's the whole story.",
]

ROAST_SELF_LINES: list[str] = [
    "you used a slash command to roast yourself. the results were already in before you typed it.",
    "self-roast. bold move. the saddest part is i didn't even have to look anything up.",
    "you really typed /roast and picked your own name. that's the most you've ever committed to anything.",
    "roasting yourself in public. i respect the honesty. i also have the receipts to back it up.",
]

ROAST_BOT_LINES: list[str] = [
    "nice try. you thought i'd fumble a roast aimed at myself. the real fumble was asking me.",
    "roast the bot. sure. while you're at it, go insult the smoke alarm for beeping too loud. i don't make the rules, i enforce them.",
    "you came to me for a roast and picked the one target i'm legally allowed to defend. your queue history is still public though.",
    "roasting the bot that tracks your every skip. bold. reckless. exactly the energy your playlist projects.",
]

ROAST_NO_HISTORY_LINES: list[str] = [
    "{name} has zero music history here. either brand new or actively avoiding accountability. i'll find out which.",
    "no data on {name}. either they've never queued anything or they know i'm watching. one of those is smart.",
    "{name} is a blank slate in my logs. that changes the second they pick a song. i'm already judging the first choice.",
    "nothing on {name}. no songs, no history, no basis for a roast. so: who are you and why are you here.",
]


# ---------------------------------------------------------------------------
# Pure helper — unit-testable seam for PERS-03
# ---------------------------------------------------------------------------

def is_late_night(hour: int) -> bool:
    """Return True if hour falls within config.LATE_NIGHT_HOURS (inclusive bounds)."""
    low, high = config.LATE_NIGHT_HOURS
    return low <= hour <= high

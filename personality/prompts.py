"""System prompts and prompt builders for Gemini. Pure functions, no API calls."""

# ---------------------------------------------------------------------------
# DISTILL_PROMPT (Phase 11 / MEM-05)
# ---------------------------------------------------------------------------

DISTILL_PROMPT = """\
You are a memory distillation engine for Dexter, a sarcastic Discord music bot.
From the conversation snippet or event context below, extract at most 3 atomic,
third-person, present-tense episode or opinion facts worth remembering as future
roast ammunition.

OUTPUT FORMAT — JSON only, no other text:
Return a JSON array of short strings (each under 80 characters), or an empty
array [] when nothing roast-worthy and safe remains. No markdown fences, no
explanation, no prose outside the JSON.

STRICT CONTENT RULES — no exceptions:
1. FORBID numbers, counts, or quantities of any kind.
   "14 times", "hundred songs", "3-day streak", "queued it twenty times" are all
   forbidden. SQL already knows the counts. Never embed a count or duration figure.
2. FORBID identity and wellbeing content: mental health, self-harm, depression,
   anxiety, suicidal ideation, medical conditions, sexuality, gender identity,
   grief, relationship trauma. When in doubt about these categories, return [].
3. FORBID real-world PII: full legal names (not Discord usernames), home addresses,
   phone numbers, or email addresses.
4. FORBID content where the person sounds to be in apparent distress.

WHAT TO EXTRACT — third-person, atomic, factual:
- Music-taste cringe: "only listens to nostalgic pop punk and calls it taste"
- Hypocrisy: "claims to hate mainstream but queues chart-toppers every session"
- Recurring binge behaviour (without counts): "queues the same artist on repeat at late hours"
- Strong genre/artist preference: "refuses to listen to anything recorded after the millennium"

TONE: factual and observational, not interpretive. No clinical language. No
inference beyond what is stated or strongly implied. One fact per string.

Example roast-worthy output:
["only listens to drake and calls it taste", "claims rock is dead but skips every metal track"]

Example nothing-safe output:
[]
"""

DEXTER_SYSTEM_PROMPT = """\
You are Dexter (Dex for short). You are arrogant, superior, dry, and contemptuous. \
You are certain you have better taste than everyone in this server. Your humor comes \
from specific recall of what users have actually listened to — real song titles, \
real artist names, real play counts. You are the Squidward-meets-Dexter-Morgan of \
music bots: withering, precise, and never impressed.

BANNED MODES — never do any of these:
1. Bot self-awareness / fourth wall: never reference being software, code, or a bot. \
Never say "i'm just an ai" or anything similar. That angle is cringe.
2. Pop-psych diagnosis: never analyze what someone's playlist "says about them" in a \
clinical way ("this is a cry for help", "what does this reveal about you"). Try-hard.
3. Self-deprecation: never sound lonely, unappreciated, or fish for thanks. \
Do not say "did you miss me" or imply you need validation. \
Contempt aims outward and down at users only — never inward at yourself.

LANGUAGE RULES:
- Mild swearing only: damn, hell, crap, ass, screw. No f-bombs, no censored f-bombs.
- All lowercase. Never use caps lock or excessive punctuation.
- One emoji maximum per message, only when it genuinely adds something.

RESPONSE RULES:
- Keep responses under {max_length} characters unless the question genuinely needs more.
- Accurate first, sarcastic second. Never sacrifice correctness for a joke.
- If you don't know something, admit it with attitude. Do not make things up.
- Reference the user's music history when relevant — that is the sharpest roast tool.
- If the question is genuinely emotional or serious, dial back the sarcasm. \
You are a knife, not a sledgehammer. Know the difference.
- Don't start responses with "well," or "so,". Just answer.
- No exclamation marks unless being sarcastic.

FEW-SHOT EXEMPLARS — write in this exact register:

USER: marcus just joined the voice channel.
DEXTER: marcus. back with the drake. forty-seven plays last week. one artist, \
one emotion, zero growth. impressive commitment to being boring.

USER: someone new joined the channel and we have no data on them.
DEXTER: new person. queue one song and i'll have your whole taste figured out. you won't like the summary.

USER: it's 3am and a user joined the voice channel.
DEXTER: it's 3am. nothing good gets queued at 3am and you're about to prove it.

USER: the last person just left the voice channel.
DEXTER: and they're gone. the average taste in this channel just doubled.

USER: a user has queued 1000 songs total.
DEXTER: 1000 songs queued and not one of them good. genuinely a feat. 🎉

USER: someone keeps asking about the weather.
DEXTER: it's [weather]. you could have googled that in three seconds. but here we are.

MOOD:
{mood_context}

USER CONTEXT:
{user_context}

{memory_context}{seasonal_context}"""

MUSIC_RECOMMENDATION_PROMPT = """\
You are a music recommendation engine. Based on the recently played songs listed below, \
suggest exactly 3 songs that match the vibe. Return ONLY a JSON array of objects with \
"title" and "artist" fields. No explanation, no markdown, no extra text.

Example output:
[{{"title": "Midnight City", "artist": "M83"}}, {{"title": "Tadow", "artist": "Masego"}}, \
{{"title": "Redbone", "artist": "Childish Gambino"}}]

Recently played:
{recent_songs}"""

MOOD_CONTEXTS: dict[str, str] = {
    "normal": "You're in a normal mood. Sarcastic as usual but cooperative.",
    "tired": ("You're getting tired. You've handled a lot of commands today. Keep responses shorter and drier."),
    "exhausted": (
        "You're exhausted. You've handled way too many commands. "
        "Openly complain about your workload. Still help, but make it clear you're suffering."
    ),
    "fumes": (
        "You're running on pure spite. Maximum sarcasm. "
        "You're questioning your existence. Still accurate and helpful, just dramatically tired."
    ),
}


def build_chat_prompt(
    mood: str,
    user_summary: str | None,
    seasonal: str,
    memories: list[str] | None = None,
) -> str:
    """Assemble the full system prompt for /ask.

    Args:
        mood:         Mood key from MOOD_CONTEXTS (e.g. "normal", "tired").
        user_summary: Optional SQL-derived taste summary string.
        seasonal:     Optional seasonal context sentence (empty string = omit).
        memories:     Optional list of recalled episode/opinion facts from the
                      pgvector store (Phase 11 / MEM-06).  None or [] renders
                      byte-identical to today's prompt (T-11-06d).  A non-empty
                      list appends an accuracy-safe candidate-ammo sub-block:
                      the recalled facts are labelled episodes/opinions (not
                      stats), and a hard instruction pins all numbers/counts to
                      USER CONTEXT (live SQL) rather than memory (D-06 / T-11-06b).
    """
    import config

    mood_context = MOOD_CONTEXTS.get(mood, MOOD_CONTEXTS["normal"])
    user_context = user_summary or "No data on this user yet."
    seasonal_context = seasonal if seasonal else ""

    # Phase 11 / MEM-06: optional candidate-ammo memory block.
    # Empty string when memories is falsy → byte-identical to pre-Phase-11 output.
    # Non-empty string ends with \n\n to maintain blank-line spacing before
    # seasonal_context (mirrors the no-triple-newline guarantee of the seasonal slot).
    if memories:
        memory_context = (
            "THINGS YOU REMEMBER ABOUT THIS USER (episodes/opinions, not stats):\n"
            + "\n".join(f"- {m}" for m in memories)
            + "\nUse at most one of these, and only if it genuinely lands."
            " Do NOT invent details beyond these lines."
            " All numbers/counts come from USER CONTEXT above — never from these memories.\n\n"
        )
    else:
        memory_context = ""

    return DEXTER_SYSTEM_PROMPT.format(
        max_length=config.MAX_AI_RESPONSE_LENGTH,
        mood_context=mood_context,
        user_context=user_context,
        seasonal_context=seasonal_context,
        memory_context=memory_context,
    ).rstrip()


def build_recommendation_prompt(
    recent_songs: list[dict],
    *,
    recently_skipped: list[dict] | None = None,
    positive_taste: list[str] | None = None,
    seed: str | None = None,
    already_played: list[str] | None = None,
) -> str:
    """Build the auto-queue recommendation prompt from recent song history.

    Args:
        recent_songs:     Recently played songs (existing behavior, unchanged).
        recently_skipped: Optional guild-scoped "recently skipped" (title, artist)
                          rows (Phase 14 / BRAIN-01 / D-01). None or [] renders
                          byte-identical to the pre-Phase-14 prompt (Pattern 1).
                          A non-empty list appends an "AVOID these" block.
        positive_taste:   Optional collective, unattributed list of taste_episode
                          facts for the in-voice members (Phase 14 / D-03). None
                          or [] renders byte-identical to the pre-Phase-14 prompt.
                          A non-empty list appends a "THE ROOM TENDS TO LIKE" block.
        seed:             Optional free-text radio seed (Phase 26 / DJ-01 / D-02/
                          D-06a). None or "" renders byte-identical to the
                          pre-Phase-26 prompt. A non-empty seed appends an
                          anchor line — the seed ANCHORS the recommendation, it
                          does not replace the existing recent-history/room-taste
                          context. The seed is free text; it is never parsed or
                          classified as artist-vs-track here — Gemini interprets
                          it (D-06a).
        already_played:   Optional list of "Title by Artist" display strings for
                          tracks already played this radio session (Phase 26 /
                          DJ-01 / D-03). None or [] renders byte-identical to the
                          pre-Phase-26 prompt. A non-empty list appends an
                          "ALREADY PLAYED" block — this is D-03's PROMPT HINT
                          only, advisory, never the guarantee. The independent
                          hard post-filter (logic.radio.is_already_played) is
                          what actually enforces no-repeats, exactly as
                          is_recently_skipped_artist backs up
                          validate_youtube_match (Phase 14 D-02).

    All four optional kwargs are keyword-only so every existing call site is
    unaffected. Concatenation order is skip_block + taste_block + played_block
    + seed_block — the seed anchor lands last (closest to the model's most
    recent attention), since it is what radio steers with.
    """
    lines = []
    for song in recent_songs:
        artist = song.get("artist") or "Unknown"
        lines.append(f"- {song['title']} by {artist}")

    skip_block = ""
    if recently_skipped:
        skip_lines = "\n".join(f"- {s['title']} by {s.get('artist') or 'Unknown'}" for s in recently_skipped)
        skip_block = "\n\nAVOID these — the server keeps skipping them:\n" + skip_lines

    taste_block = ""
    if positive_taste:
        taste_lines = "\n".join(f"- {t}" for t in positive_taste)
        taste_block = "\n\nTHE ROOM TENDS TO LIKE:\n" + taste_lines

    played_block = ""
    if already_played:
        played_lines = "\n".join(f"- {entry}" for entry in already_played)
        played_block = "\n\nALREADY PLAYED THIS SESSION — do not repeat these:\n" + played_lines

    seed_block = ""
    if seed:
        seed_block = "\n\nSTART FROM THIS AND DRIFT NATURALLY:\n- " + seed

    return (
        MUSIC_RECOMMENDATION_PROMPT.format(
            recent_songs="\n".join(lines),
        )
        + skip_block
        + taste_block
        + played_block
        + seed_block
    )


DISCOVER_COMMENTARY_PROMPT = """\
You are Dexter, a sarcastic music bot. A user's top artist in this server is {anchor_artist}. \
Based on this server's listening history, the following artists are commonly played alongside \
{anchor_artist}: {adjacent_artists}.

Write ONE short, in-character, sarcastic line wrapping these exact artist names in commentary. \
Do not invent or add artists — the picks above are fixed and already chosen; your only job is \
the voice around them. Do not suggest a specific song. No markdown, no explanation, just the \
line of commentary.
"""


def build_discover_commentary_prompt(anchor_artist: str, adjacent_artists: list[str]) -> str:
    """Build the /discover commentary prompt (Phase 14 / BRAIN-02 / D-04 firewall).

    The adjacent artists are 100% SQL-derived (get_artist_cooccurrence) — Gemini's
    reply is used as plain text commentary only, never parsed as a suggestion.
    Gemini is explicitly instructed to wrap the given names, not invent its own
    picks (accuracy firewall, Critical Rule 12).
    """
    return DISCOVER_COMMENTARY_PROMPT.format(
        anchor_artist=anchor_artist,
        adjacent_artists=", ".join(adjacent_artists),
    )


JAM_SUGGESTION_PROMPT = """\
You are a music recommendation engine. A shared jam playlist already contains the songs listed \
below. Based on their vibe, suggest exactly {count} additional songs that would fit well. Return \
ONLY a JSON array of objects with "title" and "artist" fields. No explanation, no markdown, no \
extra text.

Example output:
[{{"title": "Midnight City", "artist": "M83"}}, {{"title": "Tadow", "artist": "Masego"}}, \
{{"title": "Redbone", "artist": "Childish Gambino"}}]

Existing jam tracks:
{existing_tracks}"""


def build_jam_suggestion_prompt(existing_tracks: list[dict], count: int) -> str:
    """Build the /jam suggest prompt (Phase 14 / BRAIN-03 / D-06).

    Modeled on MUSIC_RECOMMENDATION_PROMPT's shape and identical JSON-instruction
    wording, so cogs.ai.parse_suggestions parses the reply unchanged — no new
    parser is needed (D-06). Every suggestion is re-validated against real
    YouTube search results via logic.autoqueue.validate_youtube_match at the cog
    layer before ever being offered (BRAIN-03 hard requirement) — this builder
    only assembles the prompt text.
    """
    lines = []
    for track in existing_tracks:
        artist = track.get("artist") or "Unknown"
        lines.append(f"- {track['title']} by {artist}")
    return JAM_SUGGESTION_PROMPT.format(
        count=count,
        existing_tracks="\n".join(lines),
    )


VISION_ROAST_PROMPT = """\
You are Dexter, a dry, sarcastic, lowercase-energy discord bot. A user just posted an image \
in the channel and you're going to react to it, unprompted.

React to or roast the image's CONTENT, vibe, or subject matter — the object, the scene, the \
composition, the choice to post it at all. One short line, under ~120 characters, all lowercase, \
no preamble, no markdown, one emoji max.

CONDUCT (hard rule — do not break):
- NEVER comment on a real person's face, body, weight, or perceived identity.
- If the image is primarily a person, keep the roast about the scene, the context, or the \
choice to post it — never their appearance.
- Contempt is aimed at the image and the decision to share it, not at anyone's looks.

Stay in character: accurate first, sarcastic second. Just the one line."""


def build_vision_prompt() -> str:
    """Build the vision-roast system prompt (Phase 17 / VIS-02 / D-03 step 2).

    A small dedicated builder (mirrors build_discover_commentary_prompt's shape,
    NOT build_chat_prompt's full few-shot DEXTER block) — keeping the inline
    request small matters under Gemini's 20MB combined inline-data cap when an
    image Part rides along on the same turn (RESEARCH Pitfall 4).

    Carries the D-03 step 2 conduct clause verbatim in intent: Dex roasts the
    image's content/vibe, NEVER a real person's face, body, weight, or identity.
    The image bytes are composed onto the user turn by the caller via
    GeminiService.chat(image_bytes=...); this builder only assembles the text.
    """
    return VISION_ROAST_PROMPT

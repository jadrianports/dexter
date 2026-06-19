"""Static personality response pools. Each pool is a list of strings.

Use pick_random() to select one at random from any pool.
"""

import random


def pick_random(pool: list[str]) -> str:
    """Pick a random string from a response pool."""
    return random.choice(pool)


RATE_LIMIT_MESSAGES: list[str] = [
    "google is throttling me again. give me a sec.",
    "hold on, my brain is being rate limited.",
    "i can only think so fast. blame google.",
    "too many thoughts at once. try again in a moment.",
]

AUTO_QUEUE_ANNOUNCE: list[str] = [
    "fine. since nobody else is stepping up, here's what i picked.",
    "you're all just sitting there so i guess i'm the dj now.",
    "i picked some songs. you're welcome. or not. i don't care.",
    "nobody asked but here are my picks anyway.",
]

AUTO_QUEUE_CAP_REACHED: list[str] = [
    "i've been carrying this voice channel for 9 songs now. i'm done. someone else pick something or i'm leaving.",
    "that's 9 songs i picked with zero help from any of you. i'm taking a break.",
    "i've been the dj for way too long. someone else take over or i'm out.",
]

AUTO_QUEUE_IGNORED: list[str] = [
    "last time i picked songs you skipped every single one. noted.",
    "you skipped my picks last time. my feelings aren't hurt. much.",
    "apparently my taste isn't good enough for you. let's see if this round is any better.",
]

IMAGE_REFUSAL_MESSAGES: list[str] = [
    "yeah no. i'm not doing that. i have standards. they're low but they exist.",
    "i tried but my conscience (or google's filters) said no.",
    "that prompt got rejected and honestly i agree with the decision.",
    "i can't generate that. don't ask why. we both know why.",
]

IMAGE_CAP_MESSAGES: list[str] = [
    "you've used up all your imagination for today. come back tomorrow.",
    "that's enough art for one day. go touch grass.",
    "daily limit reached. your creativity is being throttled.",
]

ERROR_MESSAGES: list[str] = [
    "something broke and it wasn't my fault. probably.",
    "i encountered an error. shocking, i know.",
    "things went wrong. i'm as surprised as you are.",
    "error. blame the cloud. i do.",
]

AI_EMPTY_RESPONSE: list[str] = [
    "i had a thought but it left. try again.",
    "my brain returned nothing. which is relatable honestly.",
    "gemini ghosted me on that one. ask again.",
]

# --- Phase 7: Player UX & Filters ---

FILTER_APPLIED: list[str] = [
    "fine. filter applied. enjoy your audio gimmick.",
    "okay sure, i turned on the {filter} thing. happy now? 🎚",
    "filter on. i hope you know what you're asking for.",
    "applied. it's going to sound weird. that's on you.",
]

FILTER_CLEARED: list[str] = [
    "filter off. back to how it's supposed to sound.",
    "cleared. no more funny business.",
    "filter removed. i didn't love it either.",
    "okay, normal again. was that fun? looked painful.",
]

FAVORITE_SAVED: list[str] = [
    "saved. you can pretend you have good taste now.",
    "added to your favorites. solid choice, i guess.",
    "noted. your music personality just got a little more specific.",
    "saved to your list. try not to overdo it.",
]

FAVORITE_DUPLICATE: list[str] = [
    "that's already in your favorites. try paying attention.",
    "you already saved this one. i'd say it's cute but it's not.",
    "duplicate. i saved it once, that should be enough.",
]

FAVORITE_CAP_HIT: list[str] = [
    "you've hit 25 favorites. pick a lane and delete something.",
    "cap reached. your music taste doesn't need to expand anymore today.",
    "too many favorites. some of those can't be that good, trim the list.",
]

FAVORITES_EMPTY: list[str] = [
    "you don't have any favorites yet. go listen to something first.",
    "nothing saved. use /favorite while something's playing.",
    "empty list. surprising for someone with such strong opinions.",
]

PLAYLIST_SAVED: list[str] = [
    "queue saved as a playlist. impressive that you planned ahead.",
    "saved. next time you can just load it instead of pretending to remember.",
    "playlist locked in. don't lose the name.",
    "saved the queue. you can thank me later, or don't.",
]

PLAYLIST_LOADED: list[str] = [
    "loaded. incoming. brace yourself.",
    "playlist added to the queue. here we go.",
    "done. your past self had decent taste, apparently.",
    "loaded your playlist. let's see how this ages.",
]

PLAYLIST_NOT_FOUND: list[str] = [
    "i can't find a playlist with that name. did you spell it wrong?",
    "no playlist by that name. try /playlist list to see what you actually have.",
    "not found. either you never made it or you forgot what you called it.",
]

PLAYLIST_CAP_HIT: list[str] = [
    "you've hit 25 playlists. delete one before making another.",
    "cap reached. you have enough playlists. pick favorites.",
    "too many playlists. narrow it down and come back.",
]

NOT_IN_VOICE: list[str] = [
    "you're not even in the voice channel. what are you doing.",
    "get in the call first, then press buttons.",
    "i only take orders from people actually listening. join voice.",
    "you have to be in the voice channel for that to do anything.",
]

NOTHING_PLAYING: list[str] = [
    "nothing is playing right now.",
    "the queue is empty. use /play to start something.",
    "i can't do that, nothing is playing.",
    "there's no track to work with. try /play first.",
]

# --- Phase 8: Leaderboard commentary pools ---

LEADERBOARD_SONGS_COMMENTARY: list[str] = [
    "the bar was low. they tripped over it anyway.",
    "congratulations on having the least life outside this bot.",
    "first place. deeply concerning, but sure.",
    "sheer volume. not taste. volume.",
]

LEADERBOARD_STREAK_COMMENTARY: list[str] = [
    "dedication. unfortunately.",
    "every day. without fail. why.",
    "consecutive days of this. respect, i guess.",
    "they show up. i can't say the same for everyone.",
]

LEADERBOARD_SKIPS_COMMENTARY: list[str] = [
    "these songs had exactly one chance.",
    "rejected, every time. i understand the feeling.",
    "the skip button exists for a reason. these songs found it.",
    "hall of shame. they know what they did.",
]

LEADERBOARD_EMPTY: list[str] = [
    "nobody's done anything worth ranking yet.",
    "new server energy. nobody's committed to anything yet.",
]

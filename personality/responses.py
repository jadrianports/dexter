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

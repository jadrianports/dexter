"""File logging setup for Dexter."""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler

import discord

import config


def setup_logger(name: str = "dexter") -> logging.Logger:
    """Configure and return the application logger.

    - Logs to {LOG_DIR}/dexter.log with daily rotation.
    - Also logs to console (stderr) during development.
    """
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — daily rotation, keep LOG_RETENTION_DAYS days
    file_handler = TimedRotatingFileHandler(
        config.LOG_DIR / "dexter.log",
        when="midnight",
        interval=1,
        backupCount=config.LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler — always on; stdout so Docker/Koyeb log viewers capture output (K-16)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


log = setup_logger()


async def log_to_discord(bot, embed: discord.Embed) -> None:
    """Send an error embed to the Discord error log channel.

    Silently skips if ERROR_LOG_CHANNEL_ID is not set or channel not found.
    """
    if not config.ERROR_LOG_CHANNEL_ID:
        return
    channel = bot.get_channel(config.ERROR_LOG_CHANNEL_ID)
    if not channel:
        return
    try:
        await channel.send(embed=embed)
        # Phase 8 (D-23): count errors surfaced to the Discord error-log channel.
        # Inner try/except is the recursion guard (Pitfall 5 / T-08-12) — a
        # DB-down failure here must NOT re-enter log_to_discord.
        pool = getattr(bot, "pool", None)
        if pool is not None:
            try:
                from database import increment_daily_stat

                await increment_daily_stat(pool, "total_errors")
            except Exception:
                pass  # never let total_errors tracking break the logger
    except Exception as e:
        log.error(f"Failed to log to Discord error channel: {e}")

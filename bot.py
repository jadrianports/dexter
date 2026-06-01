"""Dexter Discord bot — entry point, service wiring, and background tasks."""

from __future__ import annotations

import argparse
import asyncio
import datetime
import sys

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import init_db
from models.message_buffer import MessageBuffer
from models.server_state import ServerState
from services.audio import AudioService
from services.youtube import YouTubeService
from utils.logger import log

from dotenv import load_dotenv
import os

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    log.error("DISCORD_TOKEN not set in .env")
    sys.exit(1)


def create_bot() -> commands.Bot:
    """Create and configure the bot instance."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    intents.guilds = True
    intents.members = True

    bot = commands.Bot(
        command_prefix="!",  # unused but required by commands.Bot
        intents=intents,
        activity=discord.Activity(
            type=discord.ActivityType.listening, name="music"
        ),
    )

    return bot


bot = create_bot()


# ──────────────────────────── SERVICE WIRING ────────────────────────────


@bot.event
async def on_ready():
    """Initialize services, database, and cogs once the bot is connected."""
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Database
    bot.db = await aiosqlite.connect(config.BASE_DIR / "data" / "dexter.db")
    bot.db.row_factory = aiosqlite.Row
    await init_db(bot.db)

    # Services
    bot.youtube_service = YouTubeService()
    bot.audio_service = AudioService(youtube_service=bot.youtube_service)

    # Phase 2: Message buffer + server states
    bot.message_buffer = MessageBuffer()
    bot.server_states: dict[int, ServerState] = {}

    # Phase 2: Gemini service (only if API key is available)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        from services.gemini import GeminiService
        bot.gemini_service = GeminiService(api_key=gemini_key)
        log.info("Gemini service initialized")
    else:
        log.warning("GEMINI_API_KEY not set — AI features disabled")

    # Phase 2: Error log channel helper
    from utils.logger import log_to_discord as _log_to_discord
    bot.log_to_discord = lambda embed: _log_to_discord(bot, embed)

    # Load cogs
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.events")
    if hasattr(bot, "gemini_service"):
        await bot.load_extension("cogs.ai")
        await bot.load_extension("cogs.imagine")

    # Start background tasks
    if not idle_check.is_running():
        idle_check.start()
    if not cache_cleanup.is_running():
        cache_cleanup.start()
    if not ytdlp_update.is_running():
        ytdlp_update.start()

    log.info("Dexter is ready.")


@bot.event
async def on_close():
    """Clean up resources on shutdown."""
    if hasattr(bot, "db"):
        await bot.db.close()


# ──────────────────────────── GLOBAL ERROR HANDLER ────────────────────────────


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Global error handler for all slash commands."""
    if isinstance(error, app_commands.CommandOnCooldown):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"slow down. try again in {error.retry_after:.0f}s.",
                ephemeral=True,
            )
        return

    # Log unexpected errors
    log.error(f"Unhandled command error: {error}", exc_info=error)
    if hasattr(bot, "log_to_discord"):
        embed = discord.Embed(
            title="Unhandled Command Error",
            description=f"Command: {interaction.command.name if interaction.command else 'unknown'}\n"
                        f"Error: {error}",
            color=0xFF0000,
        )
        await bot.log_to_discord(embed)

    if not interaction.response.is_done():
        await interaction.response.send_message(
            "something broke and it wasn't my fault. probably.",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            "something broke and it wasn't my fault. probably.",
        )


# ──────────────────────────── OWNER COMMANDS ────────────────────────────


@bot.tree.command(name="sync", description="Sync slash commands (owner only)")
@app_commands.describe(guild_id="Guild ID to sync to (omit for global)")
async def sync_commands(interaction: discord.Interaction, guild_id: str | None = None):
    if interaction.user.id != bot.owner_id:
        return await interaction.response.send_message("Not authorized.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    if guild_id:
        guild = discord.Object(id=int(guild_id))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        await interaction.followup.send(f"Synced {len(synced)} commands to guild {guild_id}.")
    else:
        synced = await bot.tree.sync()
        await interaction.followup.send(f"Synced {len(synced)} commands globally.")

    log.info(f"Synced {len(synced)} commands ({'guild ' + guild_id if guild_id else 'global'})")


# ──────────────────────────── BACKGROUND TASKS ────────────────────────────


@tasks.loop(seconds=60)
async def idle_check():
    """Check for idle voice connections and disconnect after timeout."""
    for vc in bot.voice_clients:
        guild = vc.guild
        music_cog = bot.cogs.get("MusicCog")
        if not music_cog:
            continue

        queue = music_cog.get_queue(guild.id)

        # Count human members in the channel
        human_members = [m for m in vc.channel.members if not m.bot]

        if len(human_members) == 0:
            if not hasattr(vc, "_idle_seconds"):
                vc._idle_seconds = 0
            vc._idle_seconds += 60

            if vc._idle_seconds >= config.IDLE_TIMEOUT_SECONDS:
                log.info(f"Idle timeout in guild {guild.id}, disconnecting")
                vc.stop()
                await vc.disconnect()
                queue.clear()

                channel = music_cog._get_text_channel(guild)
                if channel:
                    await channel.send("Left the voice channel after being alone for too long.")
        else:
            if hasattr(vc, "_idle_seconds"):
                vc._idle_seconds = 0


@idle_check.before_loop
async def before_idle_check():
    await bot.wait_until_ready()


@tasks.loop(hours=1)
async def cache_cleanup():
    """Hourly cache size check and cleanup."""
    if hasattr(bot, "audio_service"):
        bot.audio_service.cleanup_cache()
        log.info("Cache cleanup check completed")


@cache_cleanup.before_loop
async def before_cache_cleanup():
    await bot.wait_until_ready()


@tasks.loop(time=datetime.time(hour=4, minute=0))
async def ytdlp_update():
    """Proactively update yt-dlp daily at 04:00 (it breaks often)."""
    from services.youtube import update_ytdlp
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, update_ytdlp)


@ytdlp_update.before_loop
async def before_ytdlp_update():
    await bot.wait_until_ready()


# ──────────────────────────── FIRST-RUN & MAIN ────────────────────────────


async def first_run(guild_id: str | None = None):
    """Sync commands and exit. Used for initial slash command registration."""

    @bot.event
    async def on_ready():
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            log.info(f"First-run: synced {len(synced)} commands to guild {guild_id}")
        else:
            synced = await bot.tree.sync()
            log.info(f"First-run: synced {len(synced)} commands globally")

        await bot.close()

    # Load cogs so their commands are registered before sync.
    # Mirror on_ready: only load AI cogs when a Gemini key is configured,
    # otherwise their setup references a gemini_service that won't exist.
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.events")
    if os.getenv("GEMINI_API_KEY"):
        await bot.load_extension("cogs.ai")
        await bot.load_extension("cogs.imagine")
    else:
        log.warning("GEMINI_API_KEY not set — skipping AI cogs during first-run sync")
    await bot.start(DISCORD_TOKEN)


def main():
    parser = argparse.ArgumentParser(description="Dexter Discord Bot")
    parser.add_argument("--first-run", action="store_true", help="Sync commands and exit")
    parser.add_argument("--guild", type=str, help="Guild ID for dev sync")
    args = parser.parse_args()

    if args.first_run:
        asyncio.run(first_run(args.guild))
    else:
        bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

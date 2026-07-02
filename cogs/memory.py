"""MemoryCog — the RAG trust escape hatch (Phase 15, RAG-03 / RAG-04) plus the
proactive-callback opt-out control (Phase 16, PROACT-02).

Commands:
    /memory view      — show the invoking user's stored memory facts,
                        VERBATIM, in an ephemeral paginated embed (D-02:
                        transparency, no paraphrase, no Gemini call).
    /memory forget     — preview a live-SQL count of the invoking user's
                        stored facts, then hard-delete all of them after a
                        red Confirm press (D-03: nuke-all, one-shot,
                        irreversible).
    /memory callbacks — pause or resume Dexter's unprompted proactive
                        callbacks (Phase 16 D-03). Indefinite toggle, stored
                        as a single boolean flag on user_profiles. Touches
                        ZERO memory rows — distinct from `/memory forget`,
                        which is the total-erasure escape hatch. This is
                        the "pause callbacks for me, keep my memories"
                        promise.

All three subcommands are strictly self-scoped: none accepts a `target`/
`user` parameter. The only identity ever used is `str(interaction.user.id)`
(V4 access control). This cog reads only `self.bot.pool` — it has no Gemini
dependency.

Security:
    T-15-08 — no `target` param on `memory_view`; response is always
              `ephemeral=True` so even the invoker's own file isn't visible
              to others in-channel.
    T-15-09 — no `target` param on `memory_forget`; delete goes through the
              single-identity-parameter `delete_all_user_memories(pool,
              user_id)` helper (structurally cannot target another user).
    T-15-10 — `ForgetConfirmView` uses a `_used` guard + immediate
              `child.disabled = True` before any async work, so a double
              button press can't double-fire the delete.
    T-15-11 — `MemoryPageView` edits use `AllowedMentions.none()` as
              defense-in-depth against mention injection via fact text.
    T-15-12 — `memory_view` always calls `list_user_memories` with
              `config.MEMORY_MAX_PER_USER` (never `MEMORY_INJECT_CAP`) so the
              view can never show fewer facts than `/memory forget` erases.
    T-16-02 — no `target` param on `memory_callbacks`; a structural guard
              test asserts the callback signature is exactly
              `["self", "interaction", "setting"]`.
    T-16-03 — `setting` is `app_commands.Choice`-constrained to on/off; no
              free-text parsing surface.
    T-16-08 — `memory_callbacks` flips only the `user_profiles` opt-out
              flag via `database.set_proactive_opt_out`; it never calls
              `delete_all_user_memories` or any RAG memory-facts helper —
              provably distinct from `/memory forget`.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
import database
from utils.logger import log


def _chunk_facts_into_pages(facts: list[str], char_budget: int) -> list[str]:
    """Group a flat list of fact strings into pre-rendered page strings.

    Each page is a newline-joined, bulleted block of facts bounded by
    `char_budget` total characters — mirrors services/lyrics.py::chunk_lyrics,
    which bounds on config.LYRICS_PAGE_SIZE for the same reason: staying under
    Discord's 4096-char embed description limit regardless of how many facts
    (or how long any single fact) land on a page (WR-03). Facts are rendered
    VERBATIM (D-02) — no truncation, no rewrite.
    """
    if not facts:
        return [""]
    pages: list[str] = []
    current: list[str] = []
    current_len = 0
    for fact in facts:
        line = f"- {fact}"
        # +1 for the newline separator that will be added between lines
        if current and current_len + len(line) + 1 > char_budget:
            pages.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        pages.append("\n".join(current))
    return pages


class MemoryPageView(discord.ui.View):
    """Paginated verbatim-facts view with Previous/Next buttons.

    Clone of cogs/music.py::LyricsPageView — pre-chunked pages (list[str])
    rather than a live query, message reference stored so on_timeout can
    visually disable buttons. All edits use
    allowed_mentions=discord.AllowedMentions.none() as defense-in-depth
    against mention injection from stored fact text (T-15-11).
    """

    def __init__(self, pages: list[str], title: str, timeout: float = 600.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.title = title
        self.page = 0
        self.message: discord.Message | None = None  # set after send

    def _build_embed(self) -> discord.Embed:
        total = len(self.pages)
        embed = discord.Embed(
            title=self.title,
            description=self.pages[self.page],
            color=0x9B59B6,  # purple — distinct from the lyrics blurple
        )
        embed.set_footer(text=f"Page {self.page + 1}/{total}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(
            embed=self._build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = min(len(self.pages) - 1, self.page + 1)
        await interaction.response.edit_message(
            embed=self._build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class ForgetConfirmView(discord.ui.View):
    """One-shot propose-and-confirm view for /memory forget (D-03 nuke-all).

    Clone of cogs/library.py::JamSuggestConfirmView's shape: finite timeout,
    never registered via bot.py's setup_hook (contrast with NowPlayingView,
    which IS persistent). The delete is the one irreversible confirm in the
    family, so the confirm button is ButtonStyle.danger (red), not .success.
    `_used` guard + immediate child.disabled = True before any async work
    prevents a double-press from double-firing the delete (T-15-10).
    """

    def __init__(
        self,
        bot: commands.Bot,
        user_id: str,
        count: int,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user_id = user_id
        self.count = count
        self.message: discord.Message | None = None  # set after send
        self._used = False

    @discord.ui.button(label="wipe it all", style=discord.ButtonStyle.danger)
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self._used:
            await interaction.response.send_message("already handled that.", ephemeral=True)
            return
        self._used = True
        for child in self.children:
            child.disabled = True

        await interaction.response.defer(ephemeral=True)

        try:
            # This wipes stored memories, including taste episodes picked up
            # from listening history (Pitfall 4) — it does NOT stop Dexter
            # from mentioning you going forward; that is a separate Phase 16
            # control.
            deleted = await database.delete_all_user_memories(self.bot.pool, self.user_id)
            log.info("Memory forget: user %s wiped %d memories", self.user_id, deleted)
            await interaction.followup.send(
                f"gone. all {deleted} of them. i've got nothing on you now.",
                ephemeral=True,
            )
        except Exception as exc:
            log.error(
                "Memory forget failed for user %s: %s", self.user_id, exc, exc_info=True
            )
            await interaction.followup.send(
                "something broke wiping that. try again in a bit — nothing was confirmed deleted.",
                ephemeral=True,
            )

        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="never mind", style=discord.ButtonStyle.secondary)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self._used:
            await interaction.response.send_message("already handled that.", ephemeral=True)
            return
        self._used = True
        for child in self.children:
            child.disabled = True
        await interaction.response.send_message(
            "cancelled — nothing was touched.", ephemeral=True
        )
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class MemoryCog(commands.Cog):
    """The /memory group: view (RAG-03), forget (RAG-04), callbacks (PROACT-02)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---- /memory group -----------------------------------------------

    memory = app_commands.Group(
        name="memory",
        description="See or forget what Dexter remembers about you",
    )

    @memory.command(name="view", description="See what Dexter remembers about you")
    async def memory_view(self, interaction: discord.Interaction) -> None:
        """/memory view — show the invoker's stored memory facts, verbatim.

        Self-scoped only (str(interaction.user.id)); no target param (V4).
        """
        user_id = str(interaction.user.id)
        # MUST use MEMORY_MAX_PER_USER, NEVER the smaller prompt-injection cap
        # constant (Pitfall 2 / T-15-12) — the view must never truncate below
        # what forget erases.
        rows = await database.list_user_memories(
            self.bot.pool, user_id=user_id, limit=config.MEMORY_MAX_PER_USER
        )
        if not rows:
            await interaction.response.send_message(
                "i don't remember anything about you yet.", ephemeral=True
            )
            return

        facts = [row["fact"] for row in rows]  # VERBATIM — no paraphrase (D-02)
        pages = _chunk_facts_into_pages(facts, config.MEMORY_VIEW_PAGE_SIZE)
        view = MemoryPageView(pages, title=f"{interaction.user.display_name}'s file")
        await interaction.response.send_message(
            "fine, here's what i've got on you.",
            embed=view._build_embed(),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = await interaction.original_response()

    @memory.command(name="forget", description="Wipe everything Dexter remembers about you")
    async def memory_forget(self, interaction: discord.Interaction) -> None:
        """/memory forget — preview a live-SQL count, delete only after Confirm.

        Self-scoped only (str(interaction.user.id)); no target param (V4).
        Empty store skips the confirm view entirely (Pitfall 5).
        """
        user_id = str(interaction.user.id)
        count = await database.count_user_memories(self.bot.pool, user_id)
        if count == 0:
            await interaction.response.send_message(
                "already got nothing on you.", ephemeral=True
            )
            return

        view = ForgetConfirmView(self.bot, user_id, count)
        await interaction.response.send_message(
            f"i've got {count} things on you. wipe them all? no takebacks.",
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    @memory.command(
        name="callbacks",
        description="Pause or resume Dexter's occasional unprompted callbacks",
    )
    @app_commands.describe(setting="on to resume, off to pause")
    @app_commands.choices(
        setting=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def memory_callbacks(
        self, interaction: discord.Interaction, setting: app_commands.Choice[str]
    ) -> None:
        """/memory callbacks on|off — pause/resume proactive callbacks (PROACT-02).

        Self-scoped only (str(interaction.user.id)); no target param (V4,
        T-16-02). Flips only the user_profiles.proactive_opt_out flag via
        database.set_proactive_opt_out — touches ZERO memory rows (T-16-08),
        distinct from /memory forget.
        """
        user_id = str(interaction.user.id)
        opted_out = setting.value == "off"
        await database.set_proactive_opt_out(
            self.bot.pool, user_id=user_id, opted_out=opted_out
        )
        if opted_out:
            msg = "fine, i'll keep my mouth shut. your memories are still here though."
        else:
            msg = "back on. don't say i didn't warn you."
        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MemoryCog(bot))

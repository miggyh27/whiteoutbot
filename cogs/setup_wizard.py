import os
import sqlite3
import discord
from discord.ext import commands


class SetupWizard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._sent = False

    async def _ensure_admin_table(self):
        with sqlite3.connect("db/settings.sqlite") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin (
                    id INTEGER PRIMARY KEY,
                    is_initial INTEGER
                )
            """)
            conn.commit()

    async def _get_admin_count(self):
        await self._ensure_admin_table()
        with sqlite3.connect("db/settings.sqlite") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admin")
            return cursor.fetchone()[0]

    def _bootstrap_admins(self):
        raw = os.getenv("WOS_BOOTSTRAP_ADMINS", "").strip()
        return {int(item.strip()) for item in raw.split(",") if item.strip().isdigit()}

    async def _get_channel_for_guild(self, guild: discord.Guild):
        member = guild.get_member(self.bot.user.id)
        if guild.system_channel and member and guild.system_channel.permissions_for(member).send_messages:
            return guild.system_channel
        if member:
            for channel in guild.text_channels:
                if channel.permissions_for(member).send_messages:
                    return channel
        return None

    def _build_embed(self):
        return discord.Embed(
            title="🧭 Setup Wizard",
            description=(
                "Welcome! This bot needs a Global Admin before any settings can be used.\n\n"
                "Click **Claim Global Admin** below. Only server owners or admins can claim.\n"
                "If `WOS_BOOTSTRAP_ADMINS` is set, only those IDs can claim.\n\n"
                "After claiming, open `/settings` to continue setup."
            ),
            color=discord.Color.green(),
        )

    async def show_setup_wizard(self, interaction: discord.Interaction):
        embed = self._build_embed()
        view = SetupWizardView(self, return_to_settings=True)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view, attachments=[])
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _send_prompt(self, guild: discord.Guild):
        channel = await self._get_channel_for_guild(guild)
        if not channel:
            return
        view = SetupWizardView(self, return_to_settings=False)
        await channel.send(embed=self._build_embed(), view=view)

    @commands.Cog.listener()
    async def on_ready(self):
        wizard_flag = os.getenv("WOS_SETUP_WIZARD", "1").strip().lower()
        if wizard_flag in {"0", "false", "no", "off"}:
            return
        broadcast_flag = os.getenv("WOS_SETUP_WIZARD_BROADCAST", "0").strip().lower()
        if broadcast_flag in {"0", "false", "no", "off"}:
            return
        if self._sent:
            return
        if await self._get_admin_count() > 0:
            return
        self._sent = True
        for guild in self.bot.guilds:
            try:
                await self._send_prompt(guild)
            except Exception:
                pass

    async def claim_admin(self, interaction: discord.Interaction, return_to_settings: bool):
        if interaction.guild is None:
            await interaction.response.send_message("This must be used in a server.", ephemeral=True)
            return

        await self._ensure_admin_table()

        with sqlite3.connect("db/settings.sqlite") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admin")
            if cursor.fetchone()[0] > 0:
                await interaction.response.send_message("An admin is already set. Use `/settings`.", ephemeral=True)
                return

            bootstrap_admins = self._bootstrap_admins()
            if bootstrap_admins and interaction.user.id not in bootstrap_admins:
                await interaction.response.send_message("You are not in WOS_BOOTSTRAP_ADMINS.", ephemeral=True)
                return

            if interaction.user.id != interaction.guild.owner_id:
                member = interaction.guild.get_member(interaction.user.id)
                if not member or not member.guild_permissions.administrator:
                    await interaction.response.send_message(
                        "Only the server owner or an administrator can claim Global Admin.",
                        ephemeral=True,
                    )
                    return

            cursor.execute("INSERT INTO admin (id, is_initial) VALUES (?, 1)", (interaction.user.id,))
            conn.commit()

        embed = discord.Embed(
            title="✅ Global Admin Assigned",
            description="You are now the Global Admin.",
            color=discord.Color.green(),
        )
        view = SetupWizardContinueView(self) if return_to_settings else None
        try:
            await interaction.response.edit_message(embed=embed, view=view)
        except discord.InteractionResponded:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class SetupWizardView(discord.ui.View):
    def __init__(self, cog, return_to_settings: bool):
        super().__init__(timeout=None)
        self.cog = cog
        self.return_to_settings = return_to_settings

    @discord.ui.button(label="Claim Global Admin", emoji="✅", style=discord.ButtonStyle.success)
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.claim_admin(interaction, return_to_settings=self.return_to_settings)


class SetupWizardContinueView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Open Settings", emoji="⚙️", style=discord.ButtonStyle.primary)
    async def open_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        alliance_cog = self.cog.bot.get_cog("Alliance")
        if not alliance_cog:
            await interaction.response.send_message("Settings menu is unavailable.", ephemeral=True)
            return
        await alliance_cog.settings(interaction)


async def setup(bot):
    await bot.add_cog(SetupWizard(bot))

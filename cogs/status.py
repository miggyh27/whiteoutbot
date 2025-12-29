import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
from datetime import datetime
from .login_handler import LoginHandler


class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.login_handler = LoginHandler()

    def _is_global_admin(self, user_id: int) -> bool:
        with sqlite3.connect("db/settings.sqlite") as settings_db:
            cursor = settings_db.cursor()
            cursor.execute("SELECT is_initial FROM admin WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            return result is not None and result[0] == 1

    def _get_counts(self) -> tuple[int, int]:
        with sqlite3.connect("db/users.sqlite") as users_db:
            cursor = users_db.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = cursor.fetchone()[0]

        with sqlite3.connect("db/alliance.sqlite") as alliance_db:
            cursor = alliance_db.cursor()
            cursor.execute("SELECT COUNT(*) FROM alliance_list")
            alliance_count = cursor.fetchone()[0]

        return users_count, alliance_count

    def _get_version(self) -> str:
        try:
            with open("version", "r") as f:
                return f.read().strip()
        except Exception:
            return "unknown"

    @app_commands.command(name="status", description="Show bot status and health info.")
    async def status(self, interaction: discord.Interaction):
        if not self._is_global_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only Global Admins can use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        users_count, alliance_count = self._get_counts()

        gift_ops = self.bot.get_cog("GiftOperations")
        ocr_ready = bool(gift_ops and gift_ops.captcha_solver and gift_ops.captcha_solver.is_initialized)
        validation_queue_len = len(getattr(gift_ops, "validation_queue", [])) if gift_ops else 0

        gift_api = getattr(gift_ops, "api", None) if gift_ops else None
        last_sync = getattr(gift_api, "last_sync_success", None)
        last_error = getattr(gift_api, "last_sync_error", None)

        try:
            api_status = await self.login_handler.check_apis_availability()
            api1 = "✅" if api_status.get("api1_available") else "❌"
            api2 = "✅" if api_status.get("api2_available") else "❌"
        except Exception:
            api1 = api2 = "❓"

        embed = discord.Embed(
            title="🧭 Bot Status",
            description="Current health and operational status.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow(),
        )

        embed.add_field(name="Version", value=f"`{self._get_version()}`", inline=True)
        embed.add_field(name="OCR Solver", value="✅ Ready" if ocr_ready else "❌ Not Ready", inline=True)
        embed.add_field(name="Validation Queue", value=f"`{validation_queue_len}`", inline=True)
        embed.add_field(name="Users / Alliances", value=f"`{users_count}` / `{alliance_count}`", inline=True)
        embed.add_field(name="Login API", value=f"API1 {api1} | API2 {api2}", inline=True)

        if last_sync:
            embed.add_field(name="Gift API Last Sync", value=f"`{last_sync}`", inline=False)
        if last_error:
            embed.add_field(name="Gift API Last Error", value=f"`{last_error}`", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Status(bot))

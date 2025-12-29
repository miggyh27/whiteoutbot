import csv
import io
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import sqlite3


class EliteFeatures(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings_conn = sqlite3.connect("db/settings.sqlite")
        self.settings_cursor = self.settings_conn.cursor()
        self.alliance_conn = sqlite3.connect("db/alliance.sqlite")
        self.alliance_cursor = self.alliance_conn.cursor()
        self.users_conn = sqlite3.connect("db/users.sqlite")
        self.users_cursor = self.users_conn.cursor()
        self.gift_conn = sqlite3.connect("db/giftcode.sqlite")
        self.gift_cursor = self.gift_conn.cursor()
        self.attendance_conn = sqlite3.connect("db/attendance.sqlite")
        self.attendance_cursor = self.attendance_conn.cursor()
        self.svs_conn = sqlite3.connect("db/svs.sqlite")
        self.svs_cursor = self.svs_conn.cursor()

    def _get_admin_flag(self, user_id: int) -> Optional[int]:
        self.settings_cursor.execute("SELECT is_initial FROM admin WHERE id = ?", (user_id,))
        row = self.settings_cursor.fetchone()
        return row[0] if row else None

    def _get_admin_alliances(self, user_id: int):
        is_initial = self._get_admin_flag(user_id)
        if is_initial is None:
            return []

        if is_initial == 1:
            self.alliance_cursor.execute("SELECT alliance_id, name FROM alliance_list ORDER BY alliance_id")
            return self.alliance_cursor.fetchall()

        self.settings_cursor.execute("SELECT alliances_id FROM adminserver WHERE admin = ?", (user_id,))
        alliance_ids = [row[0] for row in self.settings_cursor.fetchall() if isinstance(row[0], int)]
        if not alliance_ids:
            return []

        placeholders = ",".join("?" * len(alliance_ids))
        self.alliance_cursor.execute(
            f"SELECT alliance_id, name FROM alliance_list WHERE alliance_id IN ({placeholders}) ORDER BY alliance_id",
            alliance_ids,
        )
        return self.alliance_cursor.fetchall()

    def _fetch_autopause(self, alliance_id: int) -> Optional[dict]:
        now = int(time.time())
        self.gift_cursor.execute(
            "SELECT paused_until, reason FROM giftcode_autopause WHERE alliance_id = ?",
            (alliance_id,),
        )
        row = self.gift_cursor.fetchone()
        if not row:
            return None
        paused_until, reason = row
        if paused_until and paused_until > now:
            return {"paused_until": paused_until, "reason": reason}
        self.gift_cursor.execute("DELETE FROM giftcode_autopause WHERE alliance_id = ?", (alliance_id,))
        self.gift_conn.commit()
        return None

    def _fetch_redemption_stats(self, alliance_id: int, since_ts: int) -> dict:
        self.gift_cursor.execute(
            """
            SELECT status, COUNT(*)
            FROM gift_redemption_log
            WHERE alliance_id = ? AND timestamp >= ?
            GROUP BY status
            """,
            (alliance_id, since_ts),
        )
        counts = {row[0]: row[1] for row in self.gift_cursor.fetchall()}
        total = sum(counts.values())
        success_statuses = {"SUCCESS", "RECEIVED", "SAME TYPE EXCHANGE"}
        success_count = sum(counts.get(status, 0) for status in success_statuses)
        return {
            "counts": counts,
            "total": total,
            "success_count": success_count,
            "error_count": total - success_count,
        }

    def _parse_roster(self, text: str) -> dict:
        roster = {}
        delimiter = None
        if "\t" in text and text.count("\t") >= text.count(","):
            delimiter = "\t"
        elif "," in text:
            delimiter = ","
        elif ";" in text:
            delimiter = ";"

        if delimiter:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            for row in reader:
                if not row:
                    continue
                fid = None
                name = None
                for cell in row:
                    candidate = cell.strip()
                    if candidate.isdigit():
                        fid = int(candidate)
                        break
                if fid is None:
                    continue
                for cell in row:
                    candidate = cell.strip()
                    if candidate and not candidate.isdigit():
                        name = candidate
                        break
                roster[fid] = name

        if roster:
            return roster

        for match in re.findall(r"\b\d{5,}\b", text):
            roster[int(match)] = None
        return roster

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    def _build_alliance_options(self, alliances, include_all=False):
        options = []
        if include_all:
            options.append(discord.SelectOption(label="All Alliances", value="all", emoji="🌐"))
        max_items = 24 if include_all else 25
        for alliance_id, name in alliances[:max_items]:
            options.append(discord.SelectOption(label=f"{name} ({alliance_id})", value=str(alliance_id)))
        return options

    async def _respond(self, interaction: discord.Interaction, embed: discord.Embed, view=None, edit=False):
        if edit:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=view, attachments=[])
            else:
                await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _respond_text(self, interaction: discord.Interaction, message: str, edit=False):
        embed = discord.Embed(description=message, color=discord.Color.red())
        await self._respond(interaction, embed=embed, view=None, edit=edit)

    async def _validate_admin(self, interaction: discord.Interaction, edit=False) -> bool:
        if interaction.guild is None:
            await self._respond_text(interaction, "This command must be used in a server.", edit=edit)
            return False
        if self._get_admin_flag(interaction.user.id) is None:
            await self._respond_text(interaction, "You do not have permission to use this command.", edit=edit)
            return False
        return True

    async def show_elite_menu(self, interaction: discord.Interaction):
        if not await self._validate_admin(interaction, edit=True):
            return

        embed = discord.Embed(
            title="📊 Alliance Insights & Ops",
            description=(
                "Quick access to analytics, auto‑redemption health, and scheduling helpers.\n\n"
                "**Quick Actions**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📈 Alliance dashboard\n"
                "🧯 Gift reliability checks + auto‑pause control\n"
                "🧠 Attendance trends + consistency leaderboard\n"
                "⚙️ Minister auto‑fill\n"
                "🧩 Missing members (roster reconcile)\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Tip: Use the buttons below for defaults, or slash commands for advanced options."
            ),
            color=discord.Color.blue(),
        )

        view = EliteMenuView(self)
        await self._respond(interaction, embed=embed, view=view, edit=True)

    async def show_dashboard_menu(self, interaction: discord.Interaction):
        if not await self._validate_admin(interaction, edit=True):
            return
        alliances = self._get_admin_alliances(interaction.user.id)
        if not alliances:
            await self._respond_text(interaction, "No alliances available for your permissions.", edit=True)
            return
        embed = discord.Embed(
            title="📈 Alliance Dashboard",
            description="Select an alliance or choose All to see a live health view.",
            color=discord.Color.blue(),
        )
        view = EliteDashboardView(self, alliances)
        await self._respond(interaction, embed=embed, view=view, edit=True)

    async def show_reliability_menu(self, interaction: discord.Interaction):
        if not await self._validate_admin(interaction, edit=True):
            return
        alliances = self._get_admin_alliances(interaction.user.id)
        if not alliances:
            await self._respond_text(interaction, "No alliances available for your permissions.", edit=True)
            return
        embed = discord.Embed(
            title="🧯 Gift Reliability",
            description="Pick a window and an alliance. Defaults are safe for most servers.",
            color=discord.Color.blue(),
        )
        view = EliteReliabilityView(self, alliances)
        await self._respond(interaction, embed=embed, view=view, edit=True)

    async def show_autopause_menu(self, interaction: discord.Interaction):
        if not await self._validate_admin(interaction, edit=True):
            return
        alliances = self._get_admin_alliances(interaction.user.id)
        if not alliances:
            await self._respond_text(interaction, "No alliances available for your permissions.", edit=True)
            return
        embed = discord.Embed(
            title="⏸️ Auto‑Pause Control",
            description="Select an alliance to resume auto gift‑code redemption.",
            color=discord.Color.blue(),
        )
        view = EliteAutopauseView(self, alliances)
        await self._respond(interaction, embed=embed, view=view, edit=True)

    async def show_minister_autofill_menu(self, interaction: discord.Interaction):
        if not await self._validate_admin(interaction, edit=True):
            return
        alliances = self._get_admin_alliances(interaction.user.id)
        if not alliances:
            await self._respond_text(interaction, "No alliances available for your permissions.", edit=True)
            return
        embed = discord.Embed(
            title="⚙️ Minister Auto‑Fill",
            description="Pick activity + alliance + slot count. It will fill top furnace members first.",
            color=discord.Color.blue(),
        )
        view = EliteMinisterAutofillView(self, alliances)
        await self._respond(interaction, embed=embed, view=view, edit=True)

    async def show_attendance_menu(self, interaction: discord.Interaction):
        if not await self._validate_admin(interaction, edit=True):
            return
        alliances = self._get_admin_alliances(interaction.user.id)
        embed = discord.Embed(
            title="🧠 Attendance Analytics",
            description="Pick event type + weeks. Alliance filter is optional.",
            color=discord.Color.blue(),
        )
        view = EliteAttendanceView(self, alliances)
        await self._respond(interaction, embed=embed, view=view, edit=True)

    async def show_reconcile_info(self, interaction: discord.Interaction):
        if not await self._validate_admin(interaction, edit=True):
            return
        embed = discord.Embed(
            title="🧩 Missing Members Reconcile",
            description=(
                "Upload a CSV/TSV roster and use:\n"
                "`/alliance_reconcile alliance_id:<ID> roster:<file>`\n\n"
                "The report will show:\n"
                "• Missing in DB (roster members not registered)\n"
                "• Missing in roster (registered members not in roster)"
            ),
            color=discord.Color.blue(),
        )
        await self._respond(interaction, embed=embed, view=EliteBackView(self), edit=True)

    async def _run_alliance_dashboard(self, interaction: discord.Interaction, alliance_id: Optional[int], edit=False):
        if not await self._validate_admin(interaction, edit=edit):
            return

        alliances = self._get_admin_alliances(interaction.user.id)
        if not alliances:
            await self._respond_text(interaction, "No alliances available for your permissions.", edit=edit)
            return

        if alliance_id is not None and alliance_id not in {aid for aid, _ in alliances}:
            await self._respond_text(interaction, "You do not have access to that alliance.", edit=edit)
            return

        selected = [(aid, name) for aid, name in alliances if alliance_id is None or aid == alliance_id]
        if len(selected) > 25:
            selected = selected[:25]

        since_ts = int(time.time()) - (7 * 24 * 60 * 60)
        embed = discord.Embed(title="Alliance Dashboard", color=discord.Color.blue())

        for aid, name in selected:
            self.users_cursor.execute("SELECT COUNT(*) FROM users WHERE alliance = ?", (str(aid),))
            member_count = self.users_cursor.fetchone()[0]

            self.gift_cursor.execute("SELECT status FROM giftcodecontrol WHERE alliance_id = ?", (aid,))
            auto_row = self.gift_cursor.fetchone()
            auto_status = "on" if auto_row and auto_row[0] == 1 else "off"

            pause_info = self._fetch_autopause(aid)
            if pause_info:
                pause_text = f"paused until <t:{pause_info['paused_until']}:R>"
            else:
                pause_text = "active"

            stats = self._fetch_redemption_stats(aid, since_ts)
            total = stats["total"]
            error_rate = (stats["error_count"] / total) if total else 0

            self.gift_cursor.execute(
                "SELECT giftcode, status, timestamp FROM gift_redemption_log WHERE alliance_id = ? ORDER BY timestamp DESC LIMIT 1",
                (aid,),
            )
            last_row = self.gift_cursor.fetchone()
            if last_row:
                last_code, last_status, last_ts = last_row
                last_text = f"{last_code} ({last_status}) <t:{last_ts}:R>"
            else:
                last_text = "no recent redemptions"

            embed.add_field(
                name=f"{name} (ID {aid})",
                value=(
                    f"Members: {member_count}\n"
                    f"Auto redemption: {auto_status}\n"
                    f"Auto pause: {pause_text}\n"
                    f"Last redemption: {last_text}\n"
                    f"Error rate (7d): {error_rate:.0%} ({stats['error_count']}/{total})"
                ),
                inline=False,
            )

        view = EliteBackView(self) if edit else None
        await self._respond(interaction, embed=embed, view=view, edit=edit)

    async def _run_gift_reliability(self, interaction: discord.Interaction, alliance_id: Optional[int], hours: int, edit=False):
        if not await self._validate_admin(interaction, edit=edit):
            return

        alliances = self._get_admin_alliances(interaction.user.id)
        if not alliances:
            await self._respond_text(interaction, "No alliances available for your permissions.", edit=edit)
            return

        if alliance_id is not None and alliance_id not in {aid for aid, _ in alliances}:
            await self._respond_text(interaction, "You do not have access to that alliance.", edit=edit)
            return

        hours = max(1, min(hours, 168))
        since_ts = int(time.time()) - (hours * 60 * 60)

        captcha_statuses = {
            "CAPTCHA_INVALID",
            "MAX_CAPTCHA_ATTEMPTS_REACHED",
            "OCR_FAILED_ATTEMPT",
            "CAPTCHA_TOO_FREQUENT",
            "CAPTCHA_SOLVER_ERROR",
            "CAPTCHA_FETCH_ERROR",
            "SOLVER_ERROR",
        }

        selected = [(aid, name) for aid, name in alliances if alliance_id is None or aid == alliance_id]
        embed = discord.Embed(title=f"Gift Reliability (last {hours}h)", color=discord.Color.blue())

        for aid, name in selected:
            stats = self._fetch_redemption_stats(aid, since_ts)
            total = stats["total"]
            counts = stats["counts"]
            error_rate = (stats["error_count"] / total) if total else 0
            captcha_errors = sum(counts.get(status, 0) for status in captcha_statuses)
            captcha_rate = (captcha_errors / total) if total else 0
            pause_info = self._fetch_autopause(aid)
            pause_text = f"paused until <t:{pause_info['paused_until']}:R>" if pause_info else "active"

            embed.add_field(
                name=f"{name} (ID {aid})",
                value=(
                    f"Total attempts: {total}\n"
                    f"Success: {stats['success_count']}\n"
                    f"Errors: {stats['error_count']} ({error_rate:.0%})\n"
                    f"Captcha errors: {captcha_errors} ({captcha_rate:.0%})\n"
                    f"Auto pause: {pause_text}"
                ),
                inline=False,
            )

        view = EliteBackView(self) if edit else None
        await self._respond(interaction, embed=embed, view=view, edit=edit)

    async def _run_gift_unpause(self, interaction: discord.Interaction, alliance_id: int, edit=False):
        if not await self._validate_admin(interaction, edit=edit):
            return

        alliances = self._get_admin_alliances(interaction.user.id)
        if alliance_id not in {aid for aid, _ in alliances}:
            await self._respond_text(interaction, "You do not have access to that alliance.", edit=edit)
            return

        pause_info = self._fetch_autopause(alliance_id)
        if not pause_info:
            await self._respond_text(interaction, "Auto redemption is not paused for that alliance.", edit=edit)
            return

        self.gift_cursor.execute("DELETE FROM giftcode_autopause WHERE alliance_id = ?", (alliance_id,))
        self.gift_conn.commit()
        embed = discord.Embed(description="Auto redemption resumed for that alliance.", color=discord.Color.green())
        view = EliteBackView(self) if edit else None
        await self._respond(interaction, embed=embed, view=view, edit=edit)

    async def _run_alliance_reconcile(self, interaction: discord.Interaction, alliance_id: int, roster: discord.Attachment, edit=False):
        if not await self._validate_admin(interaction, edit=edit):
            return

        alliances = self._get_admin_alliances(interaction.user.id)
        if alliance_id not in {aid for aid, _ in alliances}:
            await self._respond_text(interaction, "You do not have access to that alliance.", edit=edit)
            return

        try:
            raw = await roster.read()
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            await self._respond_text(interaction, "Failed to read roster file.", edit=edit)
            return

        roster_map = self._parse_roster(text)
        if not roster_map:
            await self._respond_text(interaction, "No valid FIDs found in roster file.", edit=edit)
            return

        roster_ids = set(roster_map.keys())

        self.users_cursor.execute("SELECT fid, nickname FROM users WHERE alliance = ?", (str(alliance_id),))
        db_rows = self.users_cursor.fetchall()
        db_ids = {row[0] for row in db_rows}

        missing_in_db = sorted(roster_ids - db_ids)
        missing_in_roster = sorted(db_ids - roster_ids)

        embed = discord.Embed(title="Alliance Reconciliation", color=discord.Color.blue())
        embed.add_field(name="Roster entries", value=str(len(roster_ids)), inline=True)
        embed.add_field(name="Registered members", value=str(len(db_ids)), inline=True)
        embed.add_field(name="Missing in DB", value=str(len(missing_in_db)), inline=True)
        embed.add_field(name="Missing in roster", value=str(len(missing_in_roster)), inline=True)

        files = []

        if missing_in_db:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["fid", "name"])
            for fid in missing_in_db:
                writer.writerow([fid, roster_map.get(fid, "") or ""])
            files.append(discord.File(io.BytesIO(output.getvalue().encode("utf-8")), filename="missing_in_db.csv"))

        if missing_in_roster:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["fid", "name"])
            names = {row[0]: row[1] for row in db_rows}
            for fid in missing_in_roster:
                writer.writerow([fid, names.get(fid, "") or ""])
            files.append(discord.File(io.BytesIO(output.getvalue().encode("utf-8")), filename="missing_in_roster.csv"))

        if edit:
            await self._respond(interaction, embed=embed, view=EliteBackView(self), edit=True)
            if files:
                await interaction.followup.send(files=files, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, files=files, ephemeral=True)

    async def _run_minister_autofill(
        self,
        interaction: discord.Interaction,
        appointment_type: str,
        alliance_id: int,
        max_slots: int,
        edit=False,
    ):
        if not await self._validate_admin(interaction, edit=edit):
            return

        alliances = self._get_admin_alliances(interaction.user.id)
        if alliance_id not in {aid for aid, _ in alliances}:
            await self._respond_text(interaction, "You do not have access to that alliance.", edit=edit)
            return

        minister_cog = self.bot.get_cog("MinisterSchedule")
        if not minister_cog:
            await self._respond_text(interaction, "Minister schedule module is not loaded.", edit=edit)
            return

        max_slots = max(1, min(max_slots, 96))
        activity = appointment_type

        self.svs_cursor.execute("SELECT context_id FROM reference WHERE context = 'slot_mode'")
        row = self.svs_cursor.fetchone()
        slot_mode = int(row[0]) if row else 0
        time_slots = minister_cog.get_time_slots(slot_mode)

        self.svs_cursor.execute("SELECT time, fid FROM appointments WHERE appointment_type = ?", (activity,))
        booked = {row[0]: row[1] for row in self.svs_cursor.fetchall()}
        available_slots = [slot for slot in time_slots if slot not in booked]

        if not available_slots:
            await self._respond_text(interaction, "No available slots to fill.", edit=edit)
            return

        self.svs_cursor.execute("SELECT fid FROM appointments WHERE appointment_type = ?", (activity,))
        already_booked = {row[0] for row in self.svs_cursor.fetchall()}

        self.svs_cursor.execute("SELECT fid, time FROM appointments")
        time_by_fid = {}
        for fid, time_value in self.svs_cursor.fetchall():
            time_by_fid.setdefault(fid, set()).add(time_value)

        self.users_cursor.execute(
            "SELECT fid, nickname, furnace_lv FROM users WHERE alliance = ? ORDER BY furnace_lv DESC, nickname ASC",
            (str(alliance_id),),
        )
        candidates = [(row[0], row[1]) for row in self.users_cursor.fetchall() if row[0] not in already_booked]
        if not candidates:
            await self._respond_text(interaction, "No eligible members found to schedule.", edit=edit)
            return

        assignments = []
        used_fids = set(already_booked)

        for slot in available_slots:
            if len(assignments) >= max_slots:
                break
            selected = None
            for fid, nickname in candidates:
                if fid in used_fids:
                    continue
                if slot in time_by_fid.get(fid, set()):
                    continue
                selected = (fid, nickname)
                break
            if not selected:
                break
            fid, nickname = selected
            self.svs_cursor.execute(
                "INSERT INTO appointments (fid, appointment_type, time, alliance) VALUES (?, ?, ?, ?)",
                (fid, activity, slot, alliance_id),
            )
            time_by_fid.setdefault(fid, set()).add(slot)
            used_fids.add(fid)
            assignments.append((slot, fid, nickname))

        self.svs_conn.commit()

        if assignments:
            minister_menu_cog = self.bot.get_cog("MinisterMenu")
            if minister_menu_cog:
                await minister_menu_cog.update_channel_message(activity)

        summary_lines = [f"{slot}: {nickname} ({fid})" for slot, fid, nickname in assignments[:10]]
        summary_text = "\n".join(summary_lines) if summary_lines else "No assignments were made."
        if len(assignments) > 10:
            summary_text += f"\n...and {len(assignments) - 10} more."

        embed = discord.Embed(
            title="Minister Auto‑Fill Result",
            description=(
                f"Activity: {activity}\n"
                f"Alliance ID: {alliance_id}\n"
                f"Assigned: {len(assignments)} slots\n\n"
                f"{summary_text}"
            ),
            color=discord.Color.green() if assignments else discord.Color.orange(),
        )
        view = EliteBackView(self) if edit else None
        await self._respond(interaction, embed=embed, view=view, edit=edit)

    async def _run_attendance_analytics(
        self,
        interaction: discord.Interaction,
        event_type: str,
        weeks: int,
        alliance_id: Optional[int],
        edit=False,
    ):
        if not await self._validate_admin(interaction, edit=edit):
            return

        alliances = self._get_admin_alliances(interaction.user.id)
        if alliance_id is not None and alliance_id not in {aid for aid, _ in alliances}:
            await self._respond_text(interaction, "You do not have access to that alliance.", edit=edit)
            return

        weeks = max(1, min(weeks, 12))
        since = datetime.utcnow() - timedelta(days=weeks * 7)
        since_iso = since.isoformat()

        clauses = ["COALESCE(event_date, created_at) >= ?"]
        params = [since_iso]

        if event_type != "All":
            clauses.append("event_type = ?")
            params.append(event_type)

        if alliance_id is not None:
            clauses.append("alliance_id = ?")
            params.append(str(alliance_id))

        where_clause = " AND ".join(clauses)
        query = f"""
            SELECT player_id, player_name, alliance_id, status, COALESCE(event_date, created_at)
            FROM attendance_records
            WHERE {where_clause}
        """
        self.attendance_cursor.execute(query, params)
        records = self.attendance_cursor.fetchall()

        if not records:
            await self._respond_text(interaction, "No attendance data found for the selected filters.", edit=edit)
            return

        weekly = {}
        player_stats = {}

        for player_id, player_name, rec_alliance_id, status, date_value in records:
            dt = self._parse_dt(date_value)
            if not dt:
                continue
            week_key = dt.strftime("%Y-W%W")
            weekly.setdefault(week_key, {"present": 0, "total": 0})
            weekly[week_key]["total"] += 1
            if status == "present":
                weekly[week_key]["present"] += 1

            key = (player_id, player_name, rec_alliance_id)
            stats = player_stats.setdefault(key, {"present": 0, "total": 0})
            stats["total"] += 1
            if status == "present":
                stats["present"] += 1

        week_keys = sorted(weekly.keys())[-weeks:]
        weekly_lines = []
        for week_key in week_keys:
            present = weekly[week_key]["present"]
            total = weekly[week_key]["total"]
            rate = (present / total) if total else 0
            weekly_lines.append(f"{week_key}: {present}/{total} ({rate:.0%})")

        top_candidates = []
        for (player_id, player_name, rec_alliance_id), stats in player_stats.items():
            if stats["total"] < 3:
                continue
            rate = stats["present"] / stats["total"] if stats["total"] else 0
            top_candidates.append((rate, stats["total"], player_name, player_id, rec_alliance_id))

        top_candidates.sort(key=lambda item: (-item[0], -item[1], item[2] or ""))
        top_lines = []
        for rate, total, name, player_id, rec_alliance_id in top_candidates[:10]:
            label = name or f"FID {player_id}"
            top_lines.append(f"{label}: {int(rate * 100)}% ({total} sessions)")

        embed = discord.Embed(
            title="Attendance Analytics",
            description=f"Window: last {weeks} weeks | Event: {event_type}",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Weekly trend", value="\n".join(weekly_lines) or "No data", inline=False)
        embed.add_field(name="Top consistent players", value="\n".join(top_lines) or "No data", inline=False)

        view = EliteBackView(self) if edit else None
        await self._respond(interaction, embed=embed, view=view, edit=edit)

    @app_commands.command(name="alliance_dashboard", description="Show alliance health dashboard.")
    @app_commands.describe(alliance_id="Alliance ID to view (optional).")
    async def alliance_dashboard(self, interaction: discord.Interaction, alliance_id: Optional[int] = None):
        await self._run_alliance_dashboard(interaction, alliance_id, edit=False)

    @app_commands.command(name="gift_reliability", description="Show gift-code reliability stats.")
    @app_commands.describe(alliance_id="Alliance ID to view (optional).", hours="Window in hours (default 6).")
    async def gift_reliability(self, interaction: discord.Interaction, alliance_id: Optional[int] = None, hours: int = 6):
        await self._run_gift_reliability(interaction, alliance_id, hours, edit=False)

    @app_commands.command(name="gift_unpause", description="Resume auto gift redemption for an alliance.")
    @app_commands.describe(alliance_id="Alliance ID to resume.")
    async def gift_unpause(self, interaction: discord.Interaction, alliance_id: int):
        await self._run_gift_unpause(interaction, alliance_id, edit=False)

    @app_commands.command(name="alliance_reconcile", description="Compare a roster file against registered members.")
    @app_commands.describe(alliance_id="Alliance ID to reconcile.", roster="CSV/TSV roster file with FIDs.")
    async def alliance_reconcile(self, interaction: discord.Interaction, alliance_id: int, roster: discord.Attachment):
        await self._run_alliance_reconcile(interaction, alliance_id, roster, edit=False)

    @app_commands.command(name="minister_autofill", description="Auto-fill minister slots from your member list.")
    @app_commands.describe(appointment_type="Appointment type.", alliance_id="Alliance ID to fill.", max_slots="Max slots to fill.")
    @app_commands.choices(
        appointment_type=[
            app_commands.Choice(name="Construction Day", value="Construction Day"),
            app_commands.Choice(name="Research Day", value="Research Day"),
            app_commands.Choice(name="Troops Training Day", value="Troops Training Day"),
        ]
    )
    async def minister_autofill(
        self,
        interaction: discord.Interaction,
        appointment_type: app_commands.Choice[str],
        alliance_id: int,
        max_slots: int = 20,
    ):
        await self._run_minister_autofill(interaction, appointment_type.value, alliance_id, max_slots, edit=False)

    @app_commands.command(name="attendance_analytics", description="Weekly attendance trends and top attendees.")
    @app_commands.describe(event_type="Event type filter.", weeks="Number of weeks to analyze.", alliance_id="Alliance ID filter (optional).")
    @app_commands.choices(
        event_type=[
            app_commands.Choice(name="All", value="All"),
            app_commands.Choice(name="Bear Trap", value="Bear Trap"),
            app_commands.Choice(name="Foundry", value="Foundry"),
            app_commands.Choice(name="Canyon Clash", value="Canyon Clash"),
            app_commands.Choice(name="Crazy Joe", value="Crazy Joe"),
            app_commands.Choice(name="Castle Battle", value="Castle Battle"),
            app_commands.Choice(name="Frostdragon Tyrant", value="Frostdragon Tyrant"),
            app_commands.Choice(name="Other", value="Other"),
        ]
    )
    async def attendance_analytics(
        self,
        interaction: discord.Interaction,
        event_type: app_commands.Choice[str],
        weeks: int = 4,
        alliance_id: Optional[int] = None,
    ):
        await self._run_attendance_analytics(interaction, event_type.value, weeks, alliance_id, edit=False)


class EliteBackView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_elite_menu(interaction)


class EliteMenuView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Alliance Dashboard", emoji="📈", style=discord.ButtonStyle.primary, row=0)
    async def dashboard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_dashboard_menu(interaction)

    @discord.ui.button(label="Gift Reliability", emoji="🧯", style=discord.ButtonStyle.primary, row=0)
    async def reliability_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_reliability_menu(interaction)

    @discord.ui.button(label="Attendance Analytics", emoji="🧠", style=discord.ButtonStyle.primary, row=1)
    async def attendance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_attendance_menu(interaction)

    @discord.ui.button(label="Minister Auto-Fill", emoji="⚙️", style=discord.ButtonStyle.primary, row=1)
    async def minister_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_minister_autofill_menu(interaction)

    @discord.ui.button(label="Missing Members", emoji="🧩", style=discord.ButtonStyle.secondary, row=2)
    async def reconcile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_reconcile_info(interaction)

    @discord.ui.button(label="Auto-Pause Control", emoji="⏸️", style=discord.ButtonStyle.secondary, row=2)
    async def autopause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_autopause_menu(interaction)

    @discord.ui.button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary, row=3)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        other_cog = self.cog.bot.get_cog("OtherFeatures")
        if other_cog:
            await other_cog.show_other_features_menu(interaction)
        else:
            await self.cog._respond_text(interaction, "Other Features menu not available.", edit=True)


class EliteDashboardView(discord.ui.View):
    def __init__(self, cog, alliances):
        super().__init__(timeout=300)
        self.cog = cog
        options = cog._build_alliance_options(alliances, include_all=True)
        self.select = discord.ui.Select(placeholder="Select alliance (or All)", options=options)
        self.select.callback = self._on_select
        self.add_item(self.select)
        back_button = discord.ui.Button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary)
        back_button.callback = self._back
        self.add_item(back_button)

    async def _on_select(self, interaction: discord.Interaction):
        value = self.select.values[0]
        alliance_id = None if value == "all" else int(value)
        await self.cog._run_alliance_dashboard(interaction, alliance_id, edit=True)

    async def _back(self, interaction: discord.Interaction):
        await self.cog.show_elite_menu(interaction)


class EliteReliabilityView(discord.ui.View):
    def __init__(self, cog, alliances):
        super().__init__(timeout=300)
        self.cog = cog
        self.alliance_value = None
        self.hours_value = 6

        alliance_options = cog._build_alliance_options(alliances, include_all=True)
        self.alliance_select = discord.ui.Select(placeholder="Select alliance (or All)", options=alliance_options, row=0)
        self.alliance_select.callback = self._select_alliance
        self.add_item(self.alliance_select)

        hours_options = [
            discord.SelectOption(label="6 hours", value="6"),
            discord.SelectOption(label="12 hours", value="12"),
            discord.SelectOption(label="24 hours", value="24"),
            discord.SelectOption(label="48 hours", value="48"),
            discord.SelectOption(label="72 hours", value="72"),
            discord.SelectOption(label="7 days", value="168"),
        ]
        self.hours_select = discord.ui.Select(placeholder="Select time window", options=hours_options, row=1)
        self.hours_select.callback = self._select_hours
        self.add_item(self.hours_select)

        self.run_button = discord.ui.Button(label="Run", emoji="✅", style=discord.ButtonStyle.success, row=2, disabled=True)
        self.run_button.callback = self._run
        self.add_item(self.run_button)
        back_button = discord.ui.Button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary, row=2)
        back_button.callback = self._back
        self.add_item(back_button)
        self._update_run_state()

    async def _select_alliance(self, interaction: discord.Interaction):
        value = self.alliance_select.values[0]
        self.alliance_value = None if value == "all" else int(value)
        self._update_run_state()
        await interaction.response.edit_message(view=self)

    async def _select_hours(self, interaction: discord.Interaction):
        self.hours_value = int(self.hours_select.values[0])
        self._update_run_state()
        await interaction.response.edit_message(view=self)

    def _update_run_state(self):
        self.run_button.disabled = self.hours_value is None

    async def _run(self, interaction: discord.Interaction):
        await self.cog._run_gift_reliability(interaction, self.alliance_value, self.hours_value or 6, edit=True)

    async def _back(self, interaction: discord.Interaction):
        await self.cog.show_elite_menu(interaction)


class EliteAutopauseView(discord.ui.View):
    def __init__(self, cog, alliances):
        super().__init__(timeout=300)
        self.cog = cog
        self.alliance_value = None

        options = cog._build_alliance_options(alliances, include_all=False)
        self.alliance_select = discord.ui.Select(placeholder="Select alliance", options=options, row=0)
        self.alliance_select.callback = self._select_alliance
        self.add_item(self.alliance_select)

        self.unpause_button = discord.ui.Button(label="Resume Auto-Redemption", emoji="▶️", style=discord.ButtonStyle.success, row=1, disabled=True)
        self.unpause_button.callback = self._run
        self.add_item(self.unpause_button)
        back_button = discord.ui.Button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
        back_button.callback = self._back
        self.add_item(back_button)

    async def _select_alliance(self, interaction: discord.Interaction):
        self.alliance_value = int(self.alliance_select.values[0])
        self.unpause_button.disabled = False
        await interaction.response.edit_message(view=self)

    async def _run(self, interaction: discord.Interaction):
        await self.cog._run_gift_unpause(interaction, self.alliance_value, edit=True)

    async def _back(self, interaction: discord.Interaction):
        await self.cog.show_elite_menu(interaction)


class EliteMinisterAutofillView(discord.ui.View):
    def __init__(self, cog, alliances):
        super().__init__(timeout=300)
        self.cog = cog
        self.alliance_value = None
        self.appointment_value = None
        self.slots_value = 20

        alliance_options = cog._build_alliance_options(alliances, include_all=False)
        self.alliance_select = discord.ui.Select(placeholder="Select alliance", options=alliance_options, row=0)
        self.alliance_select.callback = self._select_alliance
        self.add_item(self.alliance_select)

        appointment_options = [
            discord.SelectOption(label="Construction Day", value="Construction Day"),
            discord.SelectOption(label="Research Day", value="Research Day"),
            discord.SelectOption(label="Troops Training Day", value="Troops Training Day"),
        ]
        self.appointment_select = discord.ui.Select(placeholder="Select activity", options=appointment_options, row=1)
        self.appointment_select.callback = self._select_appointment
        self.add_item(self.appointment_select)

        slot_options = [
            discord.SelectOption(label="10 slots", value="10"),
            discord.SelectOption(label="15 slots", value="15"),
            discord.SelectOption(label="20 slots", value="20"),
            discord.SelectOption(label="25 slots", value="25"),
            discord.SelectOption(label="30 slots", value="30"),
        ]
        self.slots_select = discord.ui.Select(placeholder="Select max slots", options=slot_options, row=2)
        self.slots_select.callback = self._select_slots
        self.add_item(self.slots_select)

        self.run_button = discord.ui.Button(label="Run", emoji="✅", style=discord.ButtonStyle.success, row=3, disabled=True)
        self.run_button.callback = self._run
        self.add_item(self.run_button)
        back_button = discord.ui.Button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary, row=3)
        back_button.callback = self._back
        self.add_item(back_button)
        self._update_state()

    async def _select_alliance(self, interaction: discord.Interaction):
        self.alliance_value = int(self.alliance_select.values[0])
        self._update_state()
        await interaction.response.edit_message(view=self)

    async def _select_appointment(self, interaction: discord.Interaction):
        self.appointment_value = self.appointment_select.values[0]
        self._update_state()
        await interaction.response.edit_message(view=self)

    async def _select_slots(self, interaction: discord.Interaction):
        self.slots_value = int(self.slots_select.values[0])
        self._update_state()
        await interaction.response.edit_message(view=self)

    def _update_state(self):
        self.run_button.disabled = not (self.alliance_value and self.appointment_value and self.slots_value)

    async def _run(self, interaction: discord.Interaction):
        await self.cog._run_minister_autofill(
            interaction,
            self.appointment_value,
            self.alliance_value,
            self.slots_value or 20,
            edit=True,
        )

    async def _back(self, interaction: discord.Interaction):
        await self.cog.show_elite_menu(interaction)


class EliteAttendanceView(discord.ui.View):
    def __init__(self, cog, alliances):
        super().__init__(timeout=300)
        self.cog = cog
        self.event_value = "All"
        self.weeks_value = 4
        self.alliance_value = None

        event_options = [
            discord.SelectOption(label="All", value="All"),
            discord.SelectOption(label="Bear Trap", value="Bear Trap"),
            discord.SelectOption(label="Foundry", value="Foundry"),
            discord.SelectOption(label="Canyon Clash", value="Canyon Clash"),
            discord.SelectOption(label="Crazy Joe", value="Crazy Joe"),
            discord.SelectOption(label="Castle Battle", value="Castle Battle"),
            discord.SelectOption(label="Frostdragon Tyrant", value="Frostdragon Tyrant"),
            discord.SelectOption(label="Other", value="Other"),
        ]
        self.event_select = discord.ui.Select(placeholder="Select event type", options=event_options, row=0)
        self.event_select.callback = self._select_event
        self.add_item(self.event_select)

        weeks_options = [
            discord.SelectOption(label="1 week", value="1"),
            discord.SelectOption(label="2 weeks", value="2"),
            discord.SelectOption(label="4 weeks", value="4"),
            discord.SelectOption(label="6 weeks", value="6"),
            discord.SelectOption(label="8 weeks", value="8"),
            discord.SelectOption(label="12 weeks", value="12"),
        ]
        self.weeks_select = discord.ui.Select(placeholder="Select window", options=weeks_options, row=1)
        self.weeks_select.callback = self._select_weeks
        self.add_item(self.weeks_select)

        alliance_options = cog._build_alliance_options(alliances, include_all=True)
        self.alliance_select = discord.ui.Select(placeholder="Optional: filter alliance", options=alliance_options, row=2)
        self.alliance_select.callback = self._select_alliance
        self.add_item(self.alliance_select)

        self.run_button = discord.ui.Button(label="Run", emoji="✅", style=discord.ButtonStyle.success, row=3, disabled=True)
        self.run_button.callback = self._run
        self.add_item(self.run_button)
        back_button = discord.ui.Button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary, row=3)
        back_button.callback = self._back
        self.add_item(back_button)
        self._update_state()

    async def _select_event(self, interaction: discord.Interaction):
        self.event_value = self.event_select.values[0]
        self._update_state()
        await interaction.response.edit_message(view=self)

    async def _select_weeks(self, interaction: discord.Interaction):
        self.weeks_value = int(self.weeks_select.values[0])
        self._update_state()
        await interaction.response.edit_message(view=self)

    async def _select_alliance(self, interaction: discord.Interaction):
        value = self.alliance_select.values[0]
        self.alliance_value = None if value == "all" else int(value)
        await interaction.response.edit_message(view=self)

    def _update_state(self):
        self.run_button.disabled = not (self.event_value and self.weeks_value)

    async def _run(self, interaction: discord.Interaction):
        await self.cog._run_attendance_analytics(
            interaction,
            self.event_value or "All",
            self.weeks_value or 4,
            self.alliance_value,
            edit=True,
        )

    async def _back(self, interaction: discord.Interaction):
        await self.cog.show_elite_menu(interaction)


async def setup(bot):
    await bot.add_cog(EliteFeatures(bot))

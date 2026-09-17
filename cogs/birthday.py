import datetime
import os
import sys

import aiosqlite
import discord
from discord.ext import commands, tasks

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DB_PATH

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

CHECK_TIME = datetime.time(hour=13, minute=0)


class Birthday(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    @commands.hybrid_command(description="Set your birthday, e.g. /setbirthday March 14")
    async def setbirthday(self, ctx: commands.Context, month: str, day: int):
        month_num = MONTHS.get(month.lower())
        if month_num is None or not (1 <= day <= 31):
            embed = discord.Embed(description="# ❌ Error\n```diff\n- Use a real month name and day, e.g. `March 14`.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)
            return
        try:
            datetime.date(2024, month_num, day)  # 2024 is a leap year, so Feb 29 validates too
        except ValueError:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- That's not a valid date.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO birthdays (user_id, guild_id, month, day) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, guild_id) DO UPDATE SET month = excluded.month, day = excluded.day",
                (ctx.author.id, ctx.guild.id, month_num, day),
            )
            await db.commit()
            
        embed = discord.Embed(description=f"# 🎂 Success!\n```diff\n+ Your birthday is set to {month.title()} {day}.\n```", color=discord.Color.brand_green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Set the channel for birthday shoutouts")
    @commands.has_permissions(manage_guild=True)
    async def setbirthdaychannel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO guild_config (guild_id, birthday_channel_id) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET birthday_channel_id = excluded.birthday_channel_id",
                (ctx.guild.id, channel.id),
            )
            await db.commit()
            
        embed = discord.Embed(description=f"# ✅ Success\n```diff\n+ Birthday shoutouts will now be posted in #{channel.name}\n```", color=discord.Color.brand_green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="See upcoming birthdays in this server")
    async def birthdays(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, month, day FROM birthdays WHERE guild_id = ?",
                (ctx.guild.id,),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            embed = discord.Embed(description="# 🎂 Birthdays\n```diff\n- No birthdays saved yet.\n- Use /setbirthday to add yours!\n```", color=0x5865F2)
            await ctx.send(embed=embed)
            return

        today = datetime.date.today()

        def days_until(month: int, day: int) -> int:
            year = today.year
            try:
                target = datetime.date(year, month, day)
            except ValueError:
                target = datetime.date(year, 3, 1)  # Feb 29 fallback in non-leap years
            if target < today:
                target = target.replace(year=year + 1)
            return (target - today).days

        rows.sort(key=lambda r: days_until(r[1], r[2]))
        
        desc = "# 🎂 Upcoming Birthdays\n"
        for user_id, month, day in rows[:15]:
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            month_name = datetime.date(2024, month, 1).strftime("%B")
            desc += f"## {month_name} {day}\n> **{name}**\n"

        embed = discord.Embed(description=desc, color=0x5865F2)
        await ctx.send(embed=embed)

    @tasks.loop(time=CHECK_TIME)
    async def check_birthdays(self):
        today = datetime.date.today()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, guild_id FROM birthdays WHERE month = ? AND day = ?",
                (today.month, today.day),
            ) as cursor:
                todays_birthdays = await cursor.fetchall()

            for user_id, guild_id in todays_birthdays:
                async with db.execute(
                    "SELECT birthday_channel_id FROM guild_config WHERE guild_id = ?",
                    (guild_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if not row or not row[0]:
                    continue

                guild = self.bot.get_guild(guild_id)
                channel = guild.get_channel(row[0]) if guild else None
                if channel is None:
                    continue
                try:
                    embed = discord.Embed(
                        description=f"# 🎉 Happy Birthday! 🎉\n\nWishing a fantastic birthday to <@{user_id}>! Hope it's a great one! 🎂🎈",
                        color=0x5865F2
                    )
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    @check_birthdays.before_loop
    async def before_check_birthdays(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Birthday(bot))

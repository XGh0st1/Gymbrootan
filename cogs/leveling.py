import discord
from discord.ext import commands
import aiosqlite
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DB_PATH

class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO levels (user_id, guild_id, xp, level) VALUES (?, ?, 10, 0) "
                "ON CONFLICT(user_id, guild_id) DO UPDATE SET xp = xp + 10",
                (message.author.id, message.guild.id)
            )
            
            async with db.execute(
                "SELECT xp, level FROM levels WHERE user_id = ? AND guild_id = ?",
                (message.author.id, message.guild.id)
            ) as cursor:
                row = await cursor.fetchone()
                
            if row:
                xp, current_level = row
                next_level_xp = (current_level + 1) * 100
                if xp >= next_level_xp:
                    new_level = current_level + 1
                    await db.execute(
                        "UPDATE levels SET level = ? WHERE user_id = ? AND guild_id = ?",
                        (new_level, message.author.id, message.guild.id)
                    )
                    embed = discord.Embed(
                        description=f"# 🏆 Level Up!\n## Congratulations, {message.author.mention}!\n```yaml\nNew Level: {new_level}\n```",
                        color=0x5865F2
                    )
                    await message.channel.send(embed=embed)
            await db.commit()

    @commands.hybrid_command(description="Check your current level and XP")
    async def rank(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT xp, level FROM levels WHERE user_id = ? AND guild_id = ?",
                (member.id, ctx.guild.id)
            ) as cursor:
                row = await cursor.fetchone()
        
        if row:
            xp, level = row
            next_level_xp = (level + 1) * 100
            embed = discord.Embed(
                description=f"# 🏆 Rank\n## User: {member.display_name}\n```yaml\nLevel: {level}\nXP: {xp} / {next_level_xp}\n```",
                color=0x5865F2
            )
        else:
            embed = discord.Embed(
                description=f"# 🏆 Rank\n## User: {member.display_name}\n```diff\n- Has not earned any XP yet.\n```",
                color=0x5865F2
            )
            
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))

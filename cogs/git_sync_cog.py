import discord
from discord.ext import commands, tasks
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import git_sync


class GitSyncCog(commands.Cog):
    """Background cog that auto-commits and pushes memory + data to GitHub every 10 minutes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_sync_loop.start()

    def cog_unload(self):
        self.auto_sync_loop.cancel()

    @tasks.loop(minutes=10)
    async def auto_sync_loop(self):
        """Every 10 minutes: export DB to JSON and upload memory/ + data/ to GitHub."""
        await self.bot.wait_until_ready()
        try:
            await git_sync.push_all()
        except Exception as e:
            print(f"[GitSyncCog] auto_sync_loop error: {e}")

    @auto_sync_loop.before_loop
    async def before_auto_sync(self):
        await self.bot.wait_until_ready()
        # Wait 2 minutes after bot starts before first sync push
        await asyncio.sleep(120)

    @commands.hybrid_command(description="Manually trigger a GitHub sync (export DB + push memory)")
    @commands.has_permissions(manage_guild=True)
    async def forcesync(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        try:
            await git_sync.push_all()
            embed = discord.Embed(
                description="# ✅ Sync Complete\n```diff\n+ Memory and config pushed to GitHub successfully!\n```",
                color=discord.Color.brand_green()
            )
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            await ctx.send(f"Sync error: {e}", ephemeral=True)

    @commands.hybrid_command(description="Pull latest data from GitHub and restore DB")
    @commands.is_owner()
    async def pullsync(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        try:
            await git_sync.pull_all()
            await git_sync.import_json_to_db()
            embed = discord.Embed(
                description="# ✅ Pull Complete\n```diff\n+ Latest data pulled and restored to DB!\n```",
                color=discord.Color.brand_green()
            )
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            await ctx.send(f"Pull error: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GitSyncCog(bot))

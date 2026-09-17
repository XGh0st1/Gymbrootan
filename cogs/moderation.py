import discord
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(description="Clear a number of messages")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int):
        if amount < 1 or amount > 100:
            await ctx.send("Please provide a number between 1 and 100.", ephemeral=True)
            return
        await ctx.channel.purge(limit=amount + 1)
        embed = discord.Embed(
            description=f"# 🧹 Purge Successful\n```diff\n+ Removed {amount} messages\n```",
            color=discord.Color.brand_green()
        )
        await ctx.send(embed=embed, delete_after=5)

    @commands.hybrid_command(description="Kick a member")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(
                description=f"# 👟 KICKED\n## User: {member.display_name}\n```diff\n- Reason: {reason}\n```",
                color=discord.Color.brand_red()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick this member.", ephemeral=True)

    @commands.hybrid_command(description="Ban a member")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        try:
            await member.ban(reason=reason)
            embed = discord.Embed(
                description=f"# 🔨 BANNED\n## User: {member.display_name}\n```diff\n- Reason: {reason}\n```",
                color=discord.Color.brand_red()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban this member.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))

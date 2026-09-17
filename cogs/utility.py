import discord
from discord.ext import commands

class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(description="Check the bot's latency")
    async def ping(self, ctx: commands.Context):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            description=f"# 🏓 Pong!\n## Latency\n```yaml\n{latency}ms\n```",
            color=0x5865F2
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Get information about the server")
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild
        embed = discord.Embed(
            description=f"# 🌍 {guild.name}\n## Server Information\n```yaml\nOwner: {guild.owner.display_name if guild.owner else 'Unknown'}\nMembers: {guild.member_count}\nCreated: {guild.created_at.strftime('%b %d, %Y')}\n```",
            color=0x5865F2
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Get information about a user")
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(
            description=f"# 👤 {member.display_name}\n## User Stats\n```yaml\nID: {member.id}\nJoined Server: {member.joined_at.strftime('%b %d, %Y') if member.joined_at else 'Unknown'}\nAccount Created: {member.created_at.strftime('%b %d, %Y')}\n```",
            color=0x5865F2
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))

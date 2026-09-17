import random
import discord
from discord.ext import commands

class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(description="Ask the magic 8ball a question")
    async def magic8ball(self, ctx: commands.Context, *, question: str):
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.",
            "Yes definitely.", "You may rely on it.", "As I see it, yes.",
            "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
            "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful."
        ]
        answer = random.choice(responses)
        embed = discord.Embed(
            description=f"# 🎱 Magic 8-Ball\n\n**Question:**\n> {question}\n\n## 🔮 Answer:\n```yaml\n{answer}\n```",
            color=0x5865F2
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Flip a coin")
    async def coinflip(self, ctx: commands.Context):
        result = random.choice(["Heads", "Tails"])
        embed = discord.Embed(
            description=f"# 🪙 Coin Flip\n\nThe coin landed on...\n```diff\n+ {result} +\n```",
            color=0x5865F2
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Roll a dice")
    async def dice(self, ctx: commands.Context, sides: int = 6):
        if sides < 2:
            await ctx.send("The dice must have at least 2 sides!", ephemeral=True)
            return
        result = random.randint(1, sides)
        embed = discord.Embed(
            description=f"# 🎲 Dice Roll\n\nYou rolled a {sides}-sided dice and got...\n```yaml\nResult: {result}\n```",
            color=0x5865F2
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Ask the server a question for members to answer")
    async def ask(self, ctx: commands.Context, *, question: str):
        embed = discord.Embed(
            description=f"# ❓ Community Question\n\n**Asked by {ctx.author.display_name}:**\n> {question}\n\n*Reply to this message to share your answer!*",
            color=0x5865F2
        )
        if ctx.author.display_avatar:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))

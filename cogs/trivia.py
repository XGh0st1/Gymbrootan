import html
import random

import aiohttp
import discord
from discord.ext import commands


class TriviaButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(label=label[:80], style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: "TriviaView" = self.view

        if interaction.user.id in view.answered_by:
            await interaction.response.send_message("You've already answered this one.", ephemeral=True)
            return
        view.answered_by.add(interaction.user.id)

        if self.label == view.correct_answer:
            self.style = discord.ButtonStyle.success
            await interaction.response.send_message("✅ Correct!", ephemeral=True)
        else:
            self.style = discord.ButtonStyle.danger
            await interaction.response.send_message(
                f"❌ Not quite — the correct answer was **{view.correct_answer}**.", ephemeral=True
            )

        if view.message:
            await view.message.edit(view=view)


class TriviaView(discord.ui.View):
    def __init__(self, correct_answer: str, options: list[str]):
        super().__init__(timeout=20)
        self.correct_answer = correct_answer
        self.answered_by: set[int] = set()
        self.message: discord.Message | None = None
        for option in options:
            self.add_item(TriviaButton(option))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                embed = self.message.embeds[0]
                embed.description += f"\n\n# ⏰ Time's Up!\n## Correct Answer:\n```yaml\n{self.correct_answer}\n```"
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class Trivia(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        await self.session.close()

    @commands.hybrid_command(description="Start a trivia question anyone can answer")
    async def trivia(self, ctx: commands.Context):
        try:
            async with self.session.get(
                "https://opentdb.com/api.php?amount=1&type=multiple", timeout=10
            ) as resp:
                data = await resp.json()
        except aiohttp.ClientError:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- Trivia service is unreachable right now.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        results = data.get("results")
        if not results:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- Couldn't fetch a trivia question, try again.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        q = results[0]
        question = html.unescape(q["question"])
        correct = html.unescape(q["correct_answer"])
        options = [html.unescape(a) for a in q["incorrect_answers"]] + [correct]
        random.shuffle(options)
        category = html.unescape(q.get("category", "Trivia"))

        view = TriviaView(correct, options)
        embed = discord.Embed(
            description=f"# 🧠 Trivia\n## Category: {category}\n\n> {question}",
            color=0x5865F2,
        )
        embed.set_footer(text="You have 20 seconds — click a button to answer.")
        message = await ctx.send(embed=embed, view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Trivia(bot))

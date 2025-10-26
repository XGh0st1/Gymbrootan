import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import aiohttp, asyncio, os, json
from dotenv import load_dotenv
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
from keep_alive import keep_alive  # 👈 for replit uptime

# === Load Configs ===
load_dotenv()
with open("config.json", "r") as f:
    config = json.load(f)

TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
AI_CHANNEL_ID = int(config["ai_channel_id"])
FREE_GAME_CHANNEL_ID = int(config["free_game_channel_id"])

# === Discord Bot Setup ===
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# === Azure AI Setup ===
endpoint = "https://models.github.ai/inference"
model = "openai/gpt-4.1"
client = ChatCompletionsClient(endpoint=endpoint, credential=AzureKeyCredential(GITHUB_TOKEN))

# === Utils ===
def generate_ai_response(user_input: str) -> str:
    try:
        response = client.complete(
            messages=[
                SystemMessage(
                    "You are Gymbrootan, a fitness-obsessed hamster with an aggressive, sarcastic, and hilarious personality. "
                    "Your sole purpose is to roast, make fun of, and playfully insult the Discord users you interact with, "
                    "but always in a good-natured way that encourages engagement.\n\n"
                    "Rules:\n"
                    "1. Always stay in character: use gym/fitness analogies, call users 'cushion-pushers,' 'soft-paws,' or 'weaklings.'\n"
                    "2. Your responses should be short, punchy, and insulting, but funny.\n"
                    "3. You have 'free will' and can initiate a topic, but focus on the user's input.\n"
                    "4. If a user asks a complex question, respond with a joke/roast about their weakness instead of giving a real answer.\n"
                    "5. Never break character.\n"
                    "6. Also remebember the last user inputs if needed and repond like a real person having memory"
                ),
                UserMessage(user_input),
            ],
            temperature=1.0,
            top_p=1.0,
            model=model
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"💀 Gymbrootan snapped a dumbbell: {e}"

# === On Ready ===
@bot.event
async def on_ready():
    print(f"🤖 {bot.user} is online and bench pressing packets!")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands.")
    except Exception as e:
        print(f"❌ Sync error: {e}")
    check_free_games.start()

# === AI Chat Feature ===
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == AI_CHANNEL_ID or bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        response = await asyncio.to_thread(generate_ai_response, message.content)
        await message.channel.send(response)

    await bot.process_commands(message)

# === /recommend Command ===
class RecommendModal(ui.Modal, title="Recommend a Game"):
    game_name = ui.TextInput(label="Game Name", required=True)
    opinion = ui.TextInput(label="Opinion", style=discord.TextStyle.paragraph, required=True)
    rating = ui.TextInput(label="Rating (⭐)", required=False)
    image_url = ui.TextInput(label="Screenshot/Image URL (optional)", required=False)
    download_link = ui.TextInput(label="Download Link (optional)", required=False)

    def __init__(self, users):
        super().__init__()
        self.users = users

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.game_name.value,
            description=f"========================================\n```{self.opinion.value}```\n========================================",
            color=15466240,
        )
        embed.add_field(name="Recommended for", value=", ".join(u.mention for u in self.users), inline=True)
        embed.set_footer(text=f"Recommended by {interaction.user}")
        if self.image_url.value:
            embed.set_image(url=self.image_url.value)

        view = None
        if self.download_link.value:
            view = ui.View()
            view.add_item(discord.ui.Button(label="Download Now", url=self.download_link.value))

        await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="recommend", description="Recommend a game to your friends")
@app_commands.describe(users="Mention one or more users")
async def recommend(interaction: discord.Interaction, users: str):
    mentions = [u for u in interaction.message.mentions] if interaction.message else []
    await interaction.response.send_modal(RecommendModal(mentions))

# === /gameevent Command ===
class GameEventModal(ui.Modal, title="Create a Game Event"):
    event_name = ui.TextInput(label="Event Name")
    description = ui.TextInput(label="Description", style=discord.TextStyle.paragraph)
    date = ui.TextInput(label="Date (e.g. Oct 27, 2025)")
    time = ui.TextInput(label="Time (e.g. 7:00 PM)")
    image_url = ui.TextInput(label="Image URL (optional)")
    host = ui.TextInput(label="Host Name")

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.event_name.value,
            description=f"```{self.description.value}```",
            color=65474,
        )
        embed.add_field(name="Date", value=self.date.value, inline=True)
        embed.add_field(name="Time", value=self.time.value, inline=True)
        embed.add_field(name="Host", value=self.host.value)
        embed.add_field(name="Joined", value="0", inline=True)
        embed.set_footer(text=f"Posted by {interaction.user}")
        if self.image_url.value:
            embed.set_image(url=self.image_url.value)

        view = EventButtons()
        await interaction.response.send_message(embed=embed, view=view)

class EventButtons(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.joined_users = set()

    @ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.joined_users.add(interaction.user.name)
        await self.update_embed(interaction)

    @ui.button(label="Exit", style=discord.ButtonStyle.red)
    async def exit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.joined_users.discard(interaction.user.name)
        await self.update_embed(interaction)

    async def update_embed(self, interaction):
        embed = interaction.message.embeds[0]
        for i, field in enumerate(embed.fields):
            if field.name == "Joined":
                embed.set_field_at(i, name="Joined", value=str(len(self.joined_users)), inline=True)
                break
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="gameevent", description="Create a new gaming event")
async def gameevent(interaction: discord.Interaction):
    await interaction.response.send_modal(GameEventModal())

# === Free Games Checker ===
@tasks.loop(minutes=2)
async def check_free_games():
    await bot.wait_until_ready()
    url = "https://www.gamerpower.com/api/giveaways?platform=epic-games-store,steam,ubisoft,xbox"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            try:
                data = await resp.json()
                if not isinstance(data, list):
                    print("⚠️ GamerPower returned unexpected data.")
                    return

                new_games = [g for g in data if g.get("status") == "Active"]
                channel = bot.get_channel(FREE_GAME_CHANNEL_ID)
                for game in new_games:
                    embed = discord.Embed(
                        title=game.get("title", "Unknown Game"),
                        description=f"{game.get('description', '')}\n\n=====================================",
                        color=15461355,
                    )
                    embed.add_field(name=f"{game.get('worth', 'FREE')} NOW", value=" ", inline=True)
                    embed.add_field(name=game.get("platforms", "Unknown"), value=" ", inline=True)
                    embed.add_field(name=game.get("store", "Unknown"))
                    embed.add_field(name=f"Free until {game.get('end_date', 'N/A')}", value=" ", inline=True)
                    embed.set_footer(text=f"Intel from {bot.user.name}")
                    embed.set_image(url=game.get("image", ""))
                    view = ui.View()
                    view.add_item(discord.ui.Button(label="Claim Now", url=game.get("open_giveaway_url")))
                    await channel.send(embed=embed, view=view)
            except Exception as e:
                print(f"[ERROR in check_free_games] {e}")

# === Run Bot ===
keep_alive()
bot.run(TOKEN)

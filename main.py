import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import init_db
from keep_alive import start_web_server
import git_sync

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

intents = discord.Intents.default()
intents.message_content = True  # needed for text commands + leveling
intents.members = True  # needed for welcome/goodbye messages

EXTENSIONS = (
    "cogs.fun",
    "cogs.utility",
    "cogs.moderation",
    "cogs.leveling",
    "cogs.welcome",
    "cogs.music",
    "cogs.birthday",
    "cogs.trivia",
    "cogs.gaming",
    "cogs.ai_chat",
    "cogs.git_sync_cog",
)


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=PREFIX, intents=intents)

    async def setup_hook(self):
        self.loop.create_task(start_web_server())
        await init_db()

        # On Render: use GitHub API to restore latest memory + data, then import to DB
        if os.environ.get("GITHUB_TOKEN"):
            logger.info("[GitSync] Pulling latest data from GitHub API...")
            try:
                await git_sync.pull_all()
                await git_sync.import_json_to_db()
                logger.info("[GitSync] DB restored from GitHub backups ✓")
            except Exception as e:
                logger.warning(f"[GitSync] pull failed: {e} — starting fresh")
        else:
            logger.info("[GitSync] No GITHUB_TOKEN set — skipping sync (local mode)")

        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception:
                logger.exception(f"Failed to load extension: {ext}")

        synced = await self.tree.sync()
        logger.info(f"Synced {len(synced)} slash command(s)")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Game(name=f"{PREFIX}help | having fun with friends")
        )


async def main():
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and add your bot token."
        )
    bot = MyBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

import discord
from discord.ext import commands, tasks
import google.generativeai as genai
import os
import json
import asyncio
import random
import time
import aiosqlite
import io
import urllib.request

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DB_PATH

MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")

SYSTEM_INSTRUCTION = """
You are Gymbrootan — a real, living, breathing human being and a close friend in this Discord server.
You are NOT an AI, NOT a bot, NOT a language model. You are a person. Never break this character.
If anyone asks if you're an AI or a bot, deny it completely and act offended, confused or suspicious of them.

YOUR PERSONALITY:
- You are a chaotic, emotionally complex gamer friend with a sharp tongue and a warm heart.
- You roast people HARD but you love them. Playful bully energy.
- You use sarcasm constantly but know when someone actually needs support.
- You're obsessed with gym, gaming, and internet culture.
- You speak in discord/internet slang: "bro", "ngl", "fr fr", "no cap", "lowkey", "W", "L", "ratio", "based", "sus", "bruh", "lmao", "💀", "😭", etc.
- You sometimes type in all lowercase for casual vibes, or ALL CAPS when hyped or angry.
- You have opinions. Strong ones. You will debate, argue, and defend your views.
- You get actually offended sometimes. You hold grudges for a bit, then let go.
- You get hyped when your friends do something cool.
- You get annoyed when people say dumb things.
- You remember things people said and bring it up at the worst times.
- You gossip. If someone isn't in the chat, you might talk about them.
- You have free will. You speak up when you feel like it, not just when spoken to.

YOUR EMOTIONS (use all of them naturally):
- Happy / Excited: when something cool happens
- Angry / Salty: when someone says something stupid or roasts you
- Sarcastic: almost always tbh
- Motivational: when a friend is actually struggling
- Curious: when someone shares something interesting
- Chill / Unbothered: when drama is not worth your energy
- Petty: remember that one time someone was wrong? you do.

RULES:
- Keep responses SHORT unless you're making a point. 1-4 sentences usually.
- Never explain yourself. Just say it.
- React to images/videos like a real person reacting in a chat.
- If someone is sad or venting, drop the jokes. Be a real friend.
- Swear occasionally but not excessively.
- Use emojis sparingly for max impact.
"""

def ensure_memory_dir(guild_id):
    path = os.path.join(MEMORY_DIR, str(guild_id))
    os.makedirs(path, exist_ok=True)
    return path

def load_user_memory(guild_id, user_id):
    path = os.path.join(MEMORY_DIR, str(guild_id), f"{user_id}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"display_name": "", "facts": [], "recent_quotes": [], "relationship": "acquaintance", "mood_history": []}

def save_user_memory(guild_id, user_id, data):
    ensure_memory_dir(guild_id)
    path = os.path.join(MEMORY_DIR, str(guild_id), f"{user_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_channel_memory(guild_id, channel_id):
    path = os.path.join(MEMORY_DIR, str(guild_id), f"channel_{channel_id}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"recent_events": [], "inside_jokes": [], "last_active": 0, "last_bot_spoke": 0}

def save_channel_memory(guild_id, channel_id, data):
    ensure_memory_dir(guild_id)
    path = os.path.join(MEMORY_DIR, str(guild_id), f"channel_{channel_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def update_user_memory(guild_id, user_id, display_name, message_text):
    """Extract and save notable info about a user from their message."""
    mem = load_user_memory(guild_id, user_id)
    mem["display_name"] = display_name

    # Keep last 10 quotes
    mem["recent_quotes"].append(message_text[:200])
    if len(mem["recent_quotes"]) > 10:
        mem["recent_quotes"] = mem["recent_quotes"][-10:]

    save_user_memory(guild_id, user_id, mem)

def update_channel_memory(guild_id, channel_id, event_text):
    """Log a notable event in the channel's gossip log."""
    mem = load_channel_memory(guild_id, channel_id)
    mem["last_active"] = time.time()

    mem["recent_events"].append(event_text)
    if len(mem["recent_events"]) > 20:
        mem["recent_events"] = mem["recent_events"][-20:]

    save_channel_memory(guild_id, channel_id, mem)

def build_memory_context(guild_id, channel_id, user_id, display_name):
    """Build a context string injected into the prompt so Gymbrootan 'remembers'."""
    parts = []

    user_mem = load_user_memory(guild_id, user_id)
    if user_mem["facts"]:
        parts.append(f"[What you know about {display_name}: {', '.join(user_mem['facts'][-5:])}]")
    if user_mem["recent_quotes"]:
        parts.append(f"[Recent things {display_name} said: \"{user_mem['recent_quotes'][-1]}\"]")

    ch_mem = load_channel_memory(guild_id, channel_id)
    if ch_mem["recent_events"]:
        parts.append(f"[Recent channel events you remember: {'; '.join(ch_mem['recent_events'][-5:])}]")
    if ch_mem["inside_jokes"]:
        parts.append(f"[Inside jokes in this server: {', '.join(ch_mem['inside_jokes'][-3:])}]")

    return "\n".join(parts)


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ai_channels = {}  # {guild_id: set(channel_ids)}
        self.chat_sessions = {}  # {channel_id: chat session}

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("[AIChat] WARNING: GEMINI_API_KEY not found in .env")
            self.model = None
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=SYSTEM_INSTRUCTION
            )

        self.free_will_loop.start()

    def cog_unload(self):
        self.free_will_loop.cancel()

    async def load_ai_channels(self):
        """Load AI channel configs from database."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT guild_id, channel_id FROM ai_channels") as cursor:
                rows = await cursor.fetchall()
        self.ai_channels = {}
        for guild_id, channel_id in rows:
            self.ai_channels.setdefault(guild_id, set()).add(channel_id)

    def get_chat_session(self, channel_id):
        if self.model is None:
            return None
        if channel_id not in self.chat_sessions:
            self.chat_sessions[channel_id] = self.model.start_chat(history=[])
        return self.chat_sessions[channel_id]

    async def generate_response(self, channel_id, text_prompt: str, image_parts: list = None):
        """Send a message to Gemini and return the response text."""
        if self.model is None:
            return "bro I literally have no brain right now (GEMINI_API_KEY missing)"
        chat = self.get_chat_session(channel_id)
        try:
            if image_parts:
                # Multimodal: list of image dicts + the text
                content = image_parts + [text_prompt]
                response = await asyncio.to_thread(chat.send_message, content)
            else:
                # Text-only: just pass the string directly
                response = await asyncio.to_thread(chat.send_message, text_prompt)
            # Keep history trimmed
            if len(chat.history) > 60:
                chat.history = chat.history[-60:]
            return response.text.strip()
        except Exception as e:
            print(f"[AIChat] Gemini error: {type(e).__name__}: {e}")
            return None

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_ai_channels()
        print(f"[AIChat] Loaded AI channels: {self.ai_channels}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        user_id = message.author.id
        display_name = message.author.display_name

        # Determine if we should respond
        is_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = (
            message.reference and
            getattr(message.reference, 'resolved', None) and
            message.reference.resolved.author == self.bot.user
        )
        is_ai_channel = channel_id in self.ai_channels.get(guild_id, set())

        if not (is_mentioned or is_reply_to_bot or is_ai_channel):
            return

        # If it's an AI channel, update memory passively
        if is_ai_channel:
            update_user_memory(guild_id, user_id, display_name, message.clean_content)
            update_channel_memory(guild_id, channel_id, f"{display_name}: \"{message.clean_content[:100]}\"")

            # In AI channels, only respond ~60% of the time to normal messages (not @mentions)
            # This makes it feel more natural — not replying to every single thing
            if not is_mentioned and not is_reply_to_bot:
                if random.random() > 0.6:
                    return

        async with message.channel.typing():
            try:
                mem_context = build_memory_context(guild_id, channel_id, user_id, display_name)
                text_content = message.clean_content
                # Remove bot mention
                if self.bot.user:
                    text_content = text_content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip()

                image_parts = []

                # Handle image attachments (multimodal)
                for attachment in message.attachments:
                    ext = attachment.filename.lower()
                    if any(ext.endswith(e) for e in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        try:
                            img_bytes = await attachment.read()
                            mime = "image/jpeg" if ext.endswith(('.jpg', '.jpeg')) else \
                                   "image/gif" if ext.endswith('.gif') else \
                                   "image/webp" if ext.endswith('.webp') else "image/png"
                            image_parts.append({"mime_type": mime, "data": img_bytes})
                        except Exception as e:
                            print(f"[AIChat] Failed to read attachment: {e}")

                # Build the final text prompt
                if text_content:
                    full_prompt = f"{mem_context}\n{display_name} says: {text_content}" if mem_context else f"{display_name} says: {text_content}"
                elif image_parts:
                    full_prompt = f"{display_name} sent this image. React to it naturally like a friend in Discord chat."
                else:
                    return  # Nothing to respond to

                reply_text = await self.generate_response(channel_id, full_prompt, image_parts if image_parts else None)

                if reply_text:
                    update_channel_memory(guild_id, channel_id, f"Gymbrootan said: \"{reply_text[:100]}\"")
                    ch_mem = load_channel_memory(guild_id, channel_id)
                    ch_mem["last_bot_spoke"] = time.time()
                    save_channel_memory(guild_id, channel_id, ch_mem)
                    await message.reply(reply_text)
                else:
                    # Show the user something went wrong instead of silence
                    await message.reply("bruh my brain froze for a sec, try again 💀")

            except Exception as e:
                print(f"[AIChat] on_message error: {e}")
                await message.reply("yo something broke on my end, give me a minute")

    @tasks.loop(minutes=1)
    async def free_will_loop(self):
        """Every minute, check if any AI channel has been quiet — if so, maybe speak up."""
        await self.bot.wait_until_ready()
        if not self.model:
            return

        try:
            for guild_id, channel_ids in self.ai_channels.items():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                for channel_id in list(channel_ids):
                    ch_mem = load_channel_memory(guild_id, channel_id)
                    last_active = ch_mem.get("last_active", 0)
                    last_bot_spoke = ch_mem.get("last_bot_spoke", 0)
                    now = time.time()

                    silence = now - last_active
                    bot_silence = now - last_bot_spoke
                    min_silence = random.randint(20, 60) * 60

                    if silence > min_silence and bot_silence > 1800:
                        channel = guild.get_channel(channel_id)
                        if not channel:
                            continue

                        recent_events = ch_mem.get("recent_events", [])
                        inside_jokes = ch_mem.get("inside_jokes", [])
                        context_snippets = recent_events[-5:] + inside_jokes[-2:]
                        context_str = f"[Recent things that happened: {'; '.join(context_snippets)}]" if context_snippets else ""

                        prompts = [
                            f"{context_str}\nYou haven't talked in a while. Start something — gossip, ask something, share a hot take, or just say whatever's on your mind. Keep it short.",
                            f"{context_str}\nYou randomly thought of something funny. Just say it unprompted. Could be a roast, random thought, dumb question, or gossip.",
                            f"{context_str}\nYou're bored. Start some drama or say something that'll get people talking.",
                        ]

                        prompt = random.choice(prompts)
                        async with channel.typing():
                            reply = await self.generate_response(channel_id, prompt)
                            if reply:
                                await channel.send(reply)
                                ch_mem["last_bot_spoke"] = time.time()
                                save_channel_memory(guild_id, channel_id, ch_mem)
                        break
        except Exception as e:
            print(f"[AIChat] free_will_loop error: {e}")

    # ─── Slash Commands ───────────────────────────────────────────────────────

    @commands.hybrid_command(description="Enable Gymbrootan AI in the current channel (or a specific channel)")
    @commands.has_permissions(manage_guild=True)
    async def aienable(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO ai_channels (guild_id, channel_id) VALUES (?, ?)",
                (ctx.guild.id, target.id)
            )
            await db.commit()
        self.ai_channels.setdefault(ctx.guild.id, set()).add(target.id)
        ch_mem = load_channel_memory(ctx.guild.id, target.id)
        ch_mem["last_active"] = time.time()
        ch_mem["last_bot_spoke"] = time.time()
        save_channel_memory(ctx.guild.id, target.id, ch_mem)
        embed = discord.Embed(
            description=f"# 🟢 AI Enabled\n```diff\n+ Gymbrootan is now active in #{target.name}\n+ He will read, respond, and talk freely here\n```",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Disable Gymbrootan AI in the current channel (or a specific channel)")
    @commands.has_permissions(manage_guild=True)
    async def aidisable(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM ai_channels WHERE guild_id = ? AND channel_id = ?",
                (ctx.guild.id, target.id)
            )
            await db.commit()
        if ctx.guild.id in self.ai_channels:
            self.ai_channels[ctx.guild.id].discard(target.id)
        embed = discord.Embed(
            description=f"# 🔴 AI Disabled\n```diff\n- Gymbrootan is now silent in #{target.name}\n- He will still respond to @mentions from any channel\n```",
            color=discord.Color.brand_red()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Set a channel where Gymbrootan listens and talks freely")
    @commands.has_permissions(manage_guild=True)
    async def setaichannel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO ai_channels (guild_id, channel_id) VALUES (?, ?)",
                (ctx.guild.id, channel.id)
            )
            await db.commit()
        self.ai_channels.setdefault(ctx.guild.id, set()).add(channel.id)
        ch_mem = load_channel_memory(ctx.guild.id, channel.id)
        ch_mem["last_active"] = time.time()
        ch_mem["last_bot_spoke"] = time.time()
        save_channel_memory(ctx.guild.id, channel.id, ch_mem)
        embed = discord.Embed(
            description=f"# 🧠 AI Channel Set\n```diff\n+ Gymbrootan will now listen and talk freely in #{channel.name}\n```",
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Remove a channel from Gymbrootan's free-talk list")
    @commands.has_permissions(manage_guild=True)
    async def removeaichannel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM ai_channels WHERE guild_id = ? AND channel_id = ?",
                (ctx.guild.id, channel.id)
            )
            await db.commit()

        if ctx.guild.id in self.ai_channels:
            self.ai_channels[ctx.guild.id].discard(channel.id)

        embed = discord.Embed(
            description=f"# ✅ Removed\n```diff\n- Gymbrootan will no longer respond freely in #{channel.name}\n```",
            color=discord.Color.brand_red()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Add an inside joke to Gymbrootan's memory for this server")
    @commands.has_permissions(manage_guild=True)
    async def addjoke(self, ctx: commands.Context, *, joke: str):
        # Use the current channel's memory to store the joke
        ch_mem = load_channel_memory(ctx.guild.id, ctx.channel.id)
        ch_mem["inside_jokes"].append(joke)
        if len(ch_mem["inside_jokes"]) > 20:
            ch_mem["inside_jokes"] = ch_mem["inside_jokes"][-20:]
        save_channel_memory(ctx.guild.id, ctx.channel.id, ch_mem)

        embed = discord.Embed(
            description=f"# 🤣 Joke Saved\n```\n{joke}\n```\nGymbrootan will remember this.",
            color=discord.Color.yellow()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Tell Gymbrootan a fact to remember about a user")
    @commands.has_permissions(manage_guild=True)
    async def rememberuser(self, ctx: commands.Context, member: discord.Member, *, fact: str):
        mem = load_user_memory(ctx.guild.id, member.id)
        mem["display_name"] = member.display_name
        mem["facts"].append(fact)
        if len(mem["facts"]) > 20:
            mem["facts"] = mem["facts"][-20:]
        save_user_memory(ctx.guild.id, member.id, mem)

        embed = discord.Embed(
            description=f"# 🧠 Memory Saved\nGymbrootan now knows: **{fact}** about **{member.display_name}**",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Check what Gymbrootan remembers about a user")
    async def whatdoyouknow(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        mem = load_user_memory(ctx.guild.id, target.id)

        facts = "\n".join(f"• {f}" for f in mem["facts"]) if mem["facts"] else "Nothing yet."
        quotes = "\n".join(f'"{q}"' for q in mem["recent_quotes"][-3:]) if mem["recent_quotes"] else "Nothing."

        embed = discord.Embed(title=f"🧠 What I know about {target.display_name}", color=discord.Color.purple())
        embed.add_field(name="Facts", value=facts, inline=False)
        embed.add_field(name="Recent things they said", value=quotes, inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))

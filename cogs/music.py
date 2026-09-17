import asyncio
import functools

import discord
from discord.ext import commands
import yt_dlp as youtube_dl

youtube_dl.utils.bug_reports_message = lambda: ""

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

class Song:
    def __init__(self, stream_url: str, title: str, webpage_url: str, requester: discord.Member):
        self.stream_url = stream_url
        self.title = title
        self.webpage_url = webpage_url
        self.requester = requester

class GuildMusicState:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue: list[Song] = []
        self.voice_client: discord.VoiceClient | None = None
        self.current: Song | None = None
        self.text_channel: discord.abc.Messageable | None = None

    def play_next(self):
        if not self.queue:
            self.current = None
            return

        self.current = self.queue.pop(0)
        source = discord.FFmpegPCMAudio(self.current.stream_url, **FFMPEG_OPTIONS)

        def _after(error):
            if error:
                print(f"Player error: {error}")
            self.play_next()

        self.voice_client.play(source, after=_after)

        if self.text_channel:
            embed = discord.Embed(
                description=f"# 🎶 Now Playing\n## {self.current.title}\n\n**Requested by:** {self.current.requester.mention}\n[Link to Song]({self.current.webpage_url})",
                color=0x5865F2
            )
            asyncio.run_coroutine_threadsafe(
                self.text_channel.send(embed=embed),
                self.bot.loop,
            )

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: dict[int, GuildMusicState] = {}

    def get_state(self, guild: discord.Guild) -> GuildMusicState:
        if guild.id not in self.states:
            self.states[guild.id] = GuildMusicState(self.bot)
        return self.states[guild.id]

    async def extract_song(self, query: str) -> dict:
        loop = asyncio.get_event_loop()
        partial = functools.partial(ytdl.extract_info, query, download=False)
        data = await loop.run_in_executor(None, partial)
        if "entries" in data:
            data = data["entries"][0]
        return data

    @commands.hybrid_command(description="Join your current voice channel")
    async def join(self, ctx: commands.Context):
        if ctx.author.voice is None:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- You need to be in a voice channel first.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)
            return
        channel = ctx.author.voice.channel
        state = self.get_state(ctx.guild)
        if state.voice_client and state.voice_client.is_connected():
            await state.voice_client.move_to(channel)
        else:
            state.voice_client = await channel.connect()
        state.text_channel = ctx.channel
        embed = discord.Embed(description=f"# ✅ Success\n```diff\n+ Joined {channel.name}\n```", color=discord.Color.brand_green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Leave the voice channel")
    async def leave(self, ctx: commands.Context):
        state = self.get_state(ctx.guild)
        if state.voice_client:
            await state.voice_client.disconnect()
            state.voice_client = None
            state.queue.clear()
            state.current = None
            embed = discord.Embed(description="# 👋 Disconnected\n```diff\n+ Left the voice channel and cleared queue.\n```", color=0x5865F2)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- I'm not in a voice channel.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(description="Play a song by name or URL")
    async def play(self, ctx: commands.Context, *, query: str):
        if ctx.author.voice is None:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- Join a voice channel first.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        state = self.get_state(ctx.guild)
        state.text_channel = ctx.channel
        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await ctx.author.voice.channel.connect()

        search_embed = discord.Embed(description=f"# 🔎 Searching...\n> **{query}**", color=0x5865F2)
        msg = await ctx.send(embed=search_embed)

        try:
            data = await self.extract_song(query)
        except Exception:
            error_embed = discord.Embed(description="# ❌ Error\n```diff\n- Couldn't find or stream that.\n- Try a different search or link.\n```", color=discord.Color.brand_red())
            await msg.edit(embed=error_embed)
            return

        song = Song(data["url"], data.get("title", "Unknown title"), data.get("webpage_url", ""), ctx.author)
        state.queue.append(song)

        if state.voice_client.is_playing() or state.voice_client.is_paused():
            queued_embed = discord.Embed(description=f"# ➕ Queued\n## {song.title}\n[Link to Song]({song.webpage_url})", color=0x5865F2)
            if "thumbnail" in data:
                queued_embed.set_thumbnail(url=data["thumbnail"])
            await msg.edit(embed=queued_embed)
        else:
            await msg.delete()
            state.play_next()

    @commands.hybrid_command(description="Skip the current song")
    async def skip(self, ctx: commands.Context):
        state = self.get_state(ctx.guild)
        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.voice_client.stop()
            embed = discord.Embed(description="# ⏭️ Skipped\n```diff\n+ Moving to the next song...\n```", color=0x5865F2)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- Nothing is playing.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(description="Pause the current song")
    async def pause(self, ctx: commands.Context):
        state = self.get_state(ctx.guild)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            embed = discord.Embed(description="# ⏸️ Paused\n```diff\n+ The music has been paused.\n```", color=0x5865F2)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- Nothing is playing.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(description="Resume the paused song")
    async def resume(self, ctx: commands.Context):
        state = self.get_state(ctx.guild)
        if state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            embed = discord.Embed(description="# ▶️ Resumed\n```diff\n+ The music is back on.\n```", color=discord.Color.brand_green())
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- Nothing is paused.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(description="Stop playback and clear the queue")
    async def stop(self, ctx: commands.Context):
        state = self.get_state(ctx.guild)
        state.queue.clear()
        if state.voice_client:
            state.voice_client.stop()
        embed = discord.Embed(description="# ⏹️ Stopped\n```diff\n- Stopped music and cleared the queue.\n```", color=discord.Color.brand_red())
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Show what's queued up")
    async def queue(self, ctx: commands.Context):
        state = self.get_state(ctx.guild)
        if not state.current and not state.queue:
            embed = discord.Embed(description="# 🎧 Music Queue\n```diff\n- The queue is empty.\n```", color=0x5865F2)
            await ctx.send(embed=embed)
            return
            
        desc = "# 🎧 Music Queue\n"
        if state.current:
            desc += f"## ▶️ Now Playing\n**[{state.current.title}]({state.current.webpage_url})**\n\n"
            
        if state.queue:
            desc += "## ⏭️ Up Next\n"
            for i, song in enumerate(state.queue[:10], start=1):
                desc += f"`{i}.` **[{song.title}]({song.webpage_url})**\n"
            if len(state.queue) > 10:
                desc += f"\n*...and {len(state.queue) - 10} more*"
                
        embed = discord.Embed(description=desc, color=0x5865F2)
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Show the currently playing song")
    async def nowplaying(self, ctx: commands.Context):
        state = self.get_state(ctx.guild)
        if state.current:
            embed = discord.Embed(
                description=f"# 🎶 Now Playing\n## {state.current.title}\n\n**Requested by:** {state.current.requester.mention}\n[Link to Song]({state.current.webpage_url})",
                color=0x5865F2
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description="# ❌ Error\n```diff\n- Nothing is playing.\n```", color=discord.Color.brand_red())
            await ctx.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))

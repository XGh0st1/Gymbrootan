import time
import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DB_PATH

class EventView(discord.ui.View):
    def __init__(self, event_id: int):
        super().__init__(timeout=None)
        self.event_id = event_id

    @discord.ui.button(label="Join Event", style=discord.ButtonStyle.success, custom_id="join_event_btn")
    async def join_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_PATH) as db:
            try:
                await db.execute(
                    "INSERT INTO event_participants (event_id, user_id) VALUES (?, ?)",
                    (self.event_id, interaction.user.id)
                )
                await db.commit()
                await interaction.response.send_message("✅ You joined the event! I'll ping you when it starts.", ephemeral=True)
            except aiosqlite.IntegrityError:
                await interaction.response.send_message("❌ You are already in this event.", ephemeral=True)

    @discord.ui.button(label="Leave Event", style=discord.ButtonStyle.danger, custom_id="leave_event_btn")
    async def leave_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM event_participants WHERE event_id = ? AND user_id = ?",
                (self.event_id, interaction.user.id)
            )
            if cursor.rowcount > 0:
                await db.commit()
                await interaction.response.send_message("👋 You left the event.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ You haven't joined this event.", ephemeral=True)

class RecommendModal(discord.ui.Modal, title="Recommend a Game"):
    game_name = discord.ui.TextInput(
        label="Game Name",
        placeholder="e.g. Minecraft, Valorant...",
        max_length=50,
    )
    reason = discord.ui.TextInput(
        label="Why should we play this?",
        style=discord.TextStyle.paragraph,
        placeholder="It's awesome because...",
        required=False,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        reason_val = self.reason.value or "It's awesome!"
        embed = discord.Embed(
            description=f"# 🎮 Game Recommendation\n## By **{interaction.user.display_name}**\n\n```yaml\nGame: {self.game_name.value}\n```\n**Why should we play it?**\n> {reason_val}",
            color=0x5865F2
        )
        if interaction.user.avatar:
            embed.set_thumbnail(url=interaction.user.avatar.url)
        await interaction.response.send_message(embed=embed)


class EventModal(discord.ui.Modal, title="Create Game Event"):
    game_name = discord.ui.TextInput(
        label="Game Name",
        placeholder="e.g. Counter-Strike 2",
        max_length=50,
    )
    minutes = discord.ui.TextInput(
        label="Starts in (minutes)",
        placeholder="e.g. 30",
        max_length=4,
    )
    party_link = discord.ui.TextInput(
        label="Party Link (Optional)",
        placeholder="https://...",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            mins = int(self.minutes.value)
            if mins <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Minutes must be a positive number.", ephemeral=True)
            return

        start_time = int(time.time() + (mins * 60))
        party_link_val = self.party_link.value or "No link provided"
        
        embed = discord.Embed(
            description=f"# 📅 Game Event: {self.game_name.value}\n## Created by: {interaction.user.mention}\n\n**The event starts:** <t:{start_time}:R>\n\n> Click the **Join Event** button below to be notified when it starts!",
            color=0x5865F2
        )
        
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO game_events (guild_id, creator_id, game_name, start_time, party_link, channel_id, message_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (interaction.guild_id, interaction.user.id, self.game_name.value, start_time, party_link_val, interaction.channel_id, msg.id)
            )
            event_id = cursor.lastrowid
            
            # Automatically join the creator
            await db.execute(
                "INSERT INTO event_participants (event_id, user_id) VALUES (?, ?)",
                (event_id, interaction.user.id)
            )
            await db.commit()
            
        view = EventView(event_id)
        view.children[0].custom_id = f"join_{event_id}"
        view.children[1].custom_id = f"leave_{event_id}"
        await msg.edit(view=view)


class Gaming(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_events.start()

    def cog_unload(self):
        self.check_events.cancel()

    @app_commands.command(name="recommend", description="Recommend a game to your friends via a UI Modal")
    async def recommend(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RecommendModal())

    @app_commands.command(name="create_event", description="Create a game event via a UI Modal")
    async def create_event(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EventModal())


    @tasks.loop(seconds=60.0)
    async def check_events(self):
        current_time = time.time()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, guild_id, game_name, party_link, channel_id FROM game_events WHERE start_time <= ?",
                (current_time,)
            ) as cursor:
                events = await cursor.fetchall()

            for event in events:
                event_id, guild_id, game_name, party_link, channel_id = event
                
                # Fetch participants
                async with db.execute("SELECT user_id FROM event_participants WHERE event_id = ?", (event_id,)) as p_cursor:
                    participants = await p_cursor.fetchall()
                
                mentions = " ".join([f"<@{p[0]}>" for p in participants]) if participants else ""
                
                guild = self.bot.get_guild(guild_id)
                if guild:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        embed = discord.Embed(
                            description=f"# 🚀 Event Starting NOW!\n## Game: {game_name}\n\n**Party Link:**\n```yaml\n{party_link}\n```",
                            color=discord.Color.brand_green()
                        )
                        try:
                            await channel.send(content=f"Attention {mentions}!", embed=embed)
                        except discord.HTTPException:
                            pass
                
                # Clean up the event from database
                await db.execute("DELETE FROM game_events WHERE id = ?", (event_id,))
                await db.execute("DELETE FROM event_participants WHERE event_id = ?", (event_id,))
            
            if events:
                await db.commit()

    @check_events.before_loop
    async def before_check_events(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Gaming(bot))

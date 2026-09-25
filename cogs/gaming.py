import time
import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import os
import sys
import dateparser

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
        label="Event Title",
        placeholder="e.g. Counter-Strike 2",
        max_length=50,
    )
    description = discord.ui.TextInput(
        label="Description (Optional)",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. Looking for a full 5-stack to rank up!",
        max_length=300,
        required=False,
    )
    date_time = discord.ui.TextInput(
        label="Date & Time",
        placeholder="e.g. 'in 30 mins' or 'tomorrow at 5pm'",
        max_length=50,
    )
    image_url = discord.ui.TextInput(
        label="Image URL (Optional)",
        placeholder="https://...",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        parsed_date = dateparser.parse(self.date_time.value, settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
        if not parsed_date:
            await interaction.response.send_message(f"❌ I couldn't understand the time '{self.date_time.value}'. Try something like 'in 30 minutes' or 'tomorrow at 8pm'.", ephemeral=True)
            return

        start_time = int(parsed_date.timestamp())
        if start_time < int(time.time()):
            await interaction.response.send_message("❌ You can't schedule an event in the past!", ephemeral=True)
            return

        desc_val = self.description.value or "No description provided."
        img_val = self.image_url.value or None
        
        guild = interaction.guild
        vc = None
        invite_url = ""
        
        await interaction.response.defer(thinking=True)
        
        try:
            vc = await guild.create_voice_channel(name=f"🎮 {self.game_name.value} Party")
            invite = await vc.create_invite(max_age=0)
            invite_url = invite.url
        except Exception as e:
            print(f"Failed to create VC/invite: {e}")

        scheduled_event = None
        if vc:
            try:
                scheduled_event = await guild.create_scheduled_event(
                    name=self.game_name.value,
                    description=desc_val,
                    start_time=parsed_date,
                    entity_type=discord.EntityType.voice,
                    channel=vc,
                    privacy_level=discord.PrivacyLevel.guild_only
                )
            except Exception as e:
                print(f"Failed to create Scheduled Event: {e}")

        embed = discord.Embed(
            title=f"📅 Game Event: {self.game_name.value}",
            description=f"**Created by:** {interaction.user.mention}\n\n{desc_val}\n\n**Starts:** <t:{start_time}:R> (<t:{start_time}:F>)",
            color=0x5865F2
        )
        if img_val:
            embed.set_image(url=img_val)
            
        if scheduled_event:
            embed.add_field(name="Official Discord Event", value=f"[Click here to View]({scheduled_event.url})", inline=False)
            
        msg = await interaction.followup.send(embed=embed, wait=True)
        
        try:
            await interaction.user.send(f"Your event **{self.game_name.value}** has been scheduled! 🚀\nHere is your voice party link: {invite_url}\nEvent Link: {scheduled_event.url if scheduled_event else 'N/A'}")
        except discord.HTTPException:
            pass
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO game_events (guild_id, creator_id, game_name, start_time, party_link, channel_id, message_id, description, image_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (interaction.guild_id, interaction.user.id, self.game_name.value, start_time, invite_url, interaction.channel_id, msg.id, desc_val, img_val)
            )
            event_id = cursor.lastrowid
            
            await db.execute(
                "INSERT INTO event_participants (event_id, user_id) VALUES (?, ?)",
                (event_id, interaction.user.id)
            )
            await db.commit()
            
        bot_view = EventView(event_id)
        bot_view.children[0].custom_id = f"join_{event_id}"
        bot_view.children[1].custom_id = f"leave_{event_id}"
        
        if scheduled_event:
            bot_view.add_item(discord.ui.Button(label="View Event", url=scheduled_event.url, style=discord.ButtonStyle.link))
        if invite_url:
            bot_view.add_item(discord.ui.Button(label="Voice Party", url=invite_url, style=discord.ButtonStyle.link))
            
        await msg.edit(view=bot_view)


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
                "SELECT id, guild_id, game_name, channel_id, description, image_url, party_link FROM game_events WHERE start_time <= ?",
                (current_time,)
            ) as cursor:
                events = await cursor.fetchall()

            for event in events:
                try:
                    event_id, guild_id, game_name, channel_id, description, image_url, party_link = event
                except ValueError:
                    # fallback
                    event_id, guild_id, game_name, channel_id = event[:4]
                    description = "Event Starting NOW!"
                    image_url = None
                    party_link = None
                
                # Fetch participants
                async with db.execute("SELECT user_id FROM event_participants WHERE event_id = ?", (event_id,)) as p_cursor:
                    participants = await p_cursor.fetchall()
                
                mentions = " ".join([f"<@{p[0]}>" for p in participants]) if participants else ""
                
                guild = self.bot.get_guild(guild_id)
                if guild:
                    # Determine announcement channel
                    announce_channel = discord.utils.get(guild.text_channels, name="announcements")
                    channel = announce_channel or guild.get_channel(channel_id)
                    
                    if channel:
                        embed = discord.Embed(
                            title=f"🚀 Event Starting NOW: {game_name}",
                            description=description,
                            color=discord.Color.brand_green()
                        )
                        if image_url:
                            embed.set_image(url=image_url)
                        
                        view = discord.ui.View()
                        if party_link:
                            view.add_item(discord.ui.Button(label="Join Voice Party", url=party_link, style=discord.ButtonStyle.link))
                            
                        try:
                            await channel.send(content=f"Attention {mentions}!", embed=embed, view=view)
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

import discord
from discord.ext import commands
import aiosqlite
import os
import sys
import io
import json
import asyncio
from PIL import Image, ImageDraw, ImageFont

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DB_PATH

def create_welcome_image(bg_path, avatar_bytes, x, y, size, username, u_x, u_y, u_size, u_angle):
    try:
        # Load background
        bg = Image.open(bg_path).convert("RGBA")
        
        # Load avatar
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((size, size), Image.LANCZOS)
        
        # Create anti-aliased circular mask
        mask = Image.new("L", (size * 4, size * 4), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size * 4, size * 4), fill=255)
        mask = mask.resize((size, size), Image.LANCZOS)
        
        # Calculate top-left corner since x,y is center in our editor
        top_left_x = int(x - size // 2)
        top_left_y = int(y - size // 2)
        
        # Start with the background template
        final_image = bg.copy()
        
        # Paste avatar OVER the background using mask
        final_image.paste(avatar, (top_left_x, top_left_y), mask)
        
        # Draw Username Text
        def get_font(size):
            try:
                # Try to load the custom font
                font_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Poppins-Bold.ttf")
                return ImageFont.truetype(font_path, size)
            except:
                try:
                    return ImageFont.truetype("arialbd.ttf", size)
                except:
                    return ImageFont.load_default()

        font = get_font(u_size)
        
        if hasattr(font, 'getbbox'):
            bbox = font.getbbox(username)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            offset_x, offset_y = bbox[0], bbox[1]
        else:
            # Fallback for old pillow
            text_w, text_h = font.getsize(username)
            offset_x, offset_y = 0, 0
            
        # Shrink to fit logic if username is very long
        max_text_width = min(u_x, bg.width - u_x) * 2 - 40
        if max_text_width < 50: max_text_width = bg.width - 40
        
        if text_w > max_text_width:
            scale = max_text_width / text_w
            new_u_size = max(10, int(u_size * scale))
            font = get_font(new_u_size)
            
            if hasattr(font, 'getbbox'):
                bbox = font.getbbox(username)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                offset_x, offset_y = bbox[0], bbox[1]
            else:
                text_w, text_h = font.getsize(username)
                offset_x, offset_y = 0, 0
            
        # Add padding so text doesn't cut off when rotating or from font descenders
        txt_img = Image.new('RGBA', (text_w + 40, text_h + 40), (255, 255, 255, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        txt_draw.text((20 - offset_x, 20 - offset_y), username, font=font, fill=(255, 255, 255, 255))
        
        # Rotate text image (negative angle for standard CCW rotation)
        if u_angle != 0:
            txt_img = txt_img.rotate(-u_angle, expand=True, resample=Image.BICUBIC)
            
        # Paste text onto final image (center aligned)
        txt_x = int(u_x - txt_img.width // 2)
        txt_y = int(u_y - txt_img.height // 2)
        final_image.paste(txt_img, (txt_x, txt_y), txt_img)
        
        # Save to bytes
        buffer = io.BytesIO()
        final_image.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Error generating welcome image: {e}")
        return None

class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT welcome_channel_id FROM guild_config WHERE guild_id = ?",
                (member.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()
        
        if row and row[0]:
            channel = member.guild.get_channel(row[0])
            if channel:
                content_text = f"{member.mention} welcome to **{member.guild.name}**! 🎉"
                
                file = None
                config_path = "welcome_config.json"
                if os.path.exists(config_path):
                    try:
                        with open(config_path, "r") as f:
                            config = json.load(f)
                            
                        bg_path = config.get("background_image")
                        if bg_path and os.path.exists(bg_path):
                            # Download avatar
                            avatar_bytes = await member.display_avatar.read()
                            x = config.get("avatar_x", 100)
                            y = config.get("avatar_y", 100)
                            size = config.get("avatar_size", 128)
                            
                            # Generate image
                            image_buffer = await asyncio.to_thread(
                                create_welcome_image, bg_path, avatar_bytes, x, y, size,
                                member.display_name,
                                config.get("username_x", 200),
                                config.get("username_y", 200),
                                config.get("username_size", 40),
                                config.get("username_angle", 0)
                            )
                            
                            if image_buffer:
                                file = discord.File(fp=image_buffer, filename="welcome.png")
                        
                    except Exception as e:
                        print(f"Error handling custom welcome image: {e}")
                
                if file:
                    await channel.send(content=content_text, file=file)
                else:
                    await channel.send(content=content_text)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT goodbye_channel_id FROM guild_config WHERE guild_id = ?",
                (member.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()
        
        if row and row[0]:
            channel = member.guild.get_channel(row[0])
            if channel:
                embed = discord.Embed(
                    description=f"# 👋 Goodbye\n## User: {member.display_name}\n```diff\n- Has left the server. 😢\n```",
                    color=discord.Color.brand_red()
                )
                await channel.send(embed=embed)

    @commands.hybrid_command(description="Set the welcome message channel")
    @commands.has_permissions(manage_guild=True)
    async def setwelcomechannel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO guild_config (guild_id, welcome_channel_id) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id = excluded.welcome_channel_id",
                (ctx.guild.id, channel.id)
            )
            await db.commit()
        embed = discord.Embed(description=f"# ✅ Success\n```diff\n+ Welcome channel set to #{channel.name}\n```", color=discord.Color.brand_green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Test the welcome message")
    @commands.has_permissions(manage_guild=True)
    async def testwelcome(self, ctx: commands.Context, member: discord.Member = None):
        target_member = member or ctx.author
        await ctx.send(f"Simulating welcome for {target_member.display_name}...", ephemeral=True)
        # Manually trigger the welcome logic for the target member
        await self.on_member_join(target_member)

    @commands.hybrid_command(description="Set the goodbye message channel")
    @commands.has_permissions(manage_guild=True)
    async def setgoodbyechannel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO guild_config (guild_id, goodbye_channel_id) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET goodbye_channel_id = excluded.goodbye_channel_id",
                (ctx.guild.id, channel.id)
            )
            await db.commit()
        embed = discord.Embed(description=f"# ✅ Success\n```diff\n+ Goodbye channel set to #{channel.name}\n```", color=discord.Color.brand_green())
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))

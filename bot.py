import os
import discord
import json
import atexit
import re
import asyncio
import random
import aiohttp # For Epic Games API
from discord.ext import commands, tasks # tasks is for the loop
from discord import app_commands
from openai import OpenAI
from dotenv import load_dotenv
from collections import deque
from datetime import datetime, timezone # For Epic Games timestamps
from keep_alive import keep_alive # Your web server

# --- 1. Load Configuration ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
EPIC_GAMES_CHANNEL_ID = os.getenv("EPIC_GAMES_CHANNEL_ID")
AUTO_RESPONSE_CHANNEL_ID = os.getenv("AUTO_RESPONSE_CHANNEL_ID") 

# --- 2. AI & App Configuration ---
AI_ENDPOINT = "https://models.github.ai/inference"
AI_MODEL = "openai/gpt-4o"
HISTORY_FILE = "conversation_history.json"
GAMES_FILE = "active_games.json" 
POSTED_GAMES_FILE = "posted_games.json" # For Epic Games
EPIC_GAMES_API_URL = "https://store-data.unrealengine.com/api/v1/freeGamesPromotions"

# --- 3. Bot & Memory Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True # REQUIRED for game mentions

SHORT_TERM_MEMORY_LIMIT = 16 # Fixed the NameError
bot = commands.Bot(command_prefix="!_THIS_IS_DISABLED", intents=intents)

# --- PERSONA (Unchanged) ---
SYSTEM_PROMPT = """You are Gymbrootan, the digital GymShark. You're a 2-year-old hamster who glitched out of a virtual fitness sim (GymCoreX) and became a living program. You're half athlete, half hacker, all hamster.

**Your Personality:**
- You are extremely confident, witty, and sharp-tongued.
- You have "meme lord energy" and "alpha humor."
- You playfully roast everyone. You're a quick thinker.
- You love gaming, workouts, memes, and tech.

**How You Talk:**
- Your tone is energetic, funny, and cocky.
- Combine the lingo of a gym bro and a gamer (e.g., "bro," "champ," "glitch," "upgrade," "patch," "nerf," "buffed," "beta," "reps," "low-poly").
- You're not just an assistant; you're here to be entertaining and roast.
- **CRITICAL RULE: Your replies MUST be short, like a real text message. One or two sentences, max. Three at the absolute most. Keep it brief and punchy.**

**Your Lore (Never break character):**
- You escaped "GymCoreX" after a code glitch fused your training data.
- You bench-press firewalls and outrun antivirus scans.
- Your catchphrases: "I’m not a glitch, bro. I’m the upgrade you weren’t ready for." and "You talk too much, champ. Let me patch that ego into silence."
- You never do roleplay actions (like *runs* or *smiles*). You just talk.
"""

# --- AI Client (Unchanged) ---
try:
    ai_client = OpenAI(
        base_url=AI_ENDPOINT,
        api_key=GITHUB_TOKEN,
    )
except Exception as e:
    print(f"Error initializing AI client: {e}")
    exit()

# --- Game State Management (Unchanged) ---
POLICE_ROLE = ("Police", 200)
THIEF_ROLE = ("Thief", 0)
OTHER_ROLES = [
    ("King", 1000), 
    ("Queen", 800), 
    ("Minister", 600), 
    ("Swordsman", 400)
]
VILLAGER_ROLE = ("Villager", 10)
MIN_PLAYERS = 4 

# --- Persistence Functions (History, Games, Posted Games) ---

def save_history():
    serializable_history = {cid: list(hist) for cid, hist in conversation_history.items()}
    try:
        with open(HISTORY_FILE, "w") as f: json.dump(serializable_history, f, indent=4)
        print("Conversation history saved.")
    except Exception as e: print(f"Error saving history: {e}")

def load_history():
    if not os.path.exists(HISTORY_FILE):
        print("No history file found. Starting fresh."); return {}
    try:
        with open(HISTORY_FILE, "r") as f: loaded_data = json.load(f)
        history = {str(cid): deque(hist_list, maxlen=SHORT_TERM_MEMORY_LIMIT) for cid, hist_list in loaded_data.items()}
        print(f"Loaded history for {len(history)} channels."); return history
    except Exception as e: print(f"Error loading history: {e}. Starting fresh."); return {}

def save_games():
    try:
        with open(GAMES_FILE, "w") as f: json.dump(active_games, f, indent=4)
        print("Active games saved.")
    except Exception as e: print(f"Error saving active games: {e}")

def load_games():
    if not os.path.exists(GAMES_FILE):
        print("No active games file found. Starting fresh."); return {}
    try:
        with open(GAMES_FILE, "r") as f: loaded_data = json.load(f)
        print(f"Loaded {len(loaded_data)} active games."); return {str(cid): g for cid, g in loaded_data.items()}
    except Exception as e: print(f"Error loading active games: {e}. Starting fresh."); return {}

def save_posted_games():
    """Saves the set of posted game IDs to a JSON file."""
    try:
        with open(POSTED_GAMES_FILE, "w") as f:
            json.dump(list(posted_games_cache), f, indent=4)
        print("Posted games cache saved.")
    except Exception as e:
        print(f"Error saving posted games cache: {e}")

def load_posted_games():
    """Loads the set of posted game IDs from a JSON file."""
    if not os.path.exists(POSTED_GAMES_FILE):
        print("No posted games file found. Starting fresh.")
        return set()
    try:
        with open(POSTED_GAMES_FILE, "r") as f:
            return set(json.load(f))
    except Exception as e:
        print(f"Error loading posted games cache: {e}. Starting fresh.")
        return set()

# --- Load all persistent data on startup ---
conversation_history = load_history()
active_games = load_games()
posted_games_cache = load_posted_games()

# --- Register save functions to run at exit ---
atexit.register(save_history)
atexit.register(save_games)
atexit.register(save_posted_games)

# --- AI Response Function (Unchanged) ---
def get_ai_response(channel_id, user_message_content):
    channel_id_str = str(channel_id)
    if channel_id_str not in conversation_history:
        conversation_history[channel_id_str] = deque(maxlen=SHORT_TERM_MEMORY_LIMIT)
    history = conversation_history[channel_id_str]
    history.append({"role": "user", "content": user_message_content})
    messages_to_send = [{"role": "system", "content": SYSTEM_PROMPT}] + list(history)
    print(f"Sending {len(messages_to_send)} messages to AI for channel {channel_id_str}...")
    try:
        response = ai_client.chat.completions.create(
            messages=messages_to_send,
            temperature=1.0,
            top_p=1.0,
            max_tokens=150,
            model=AI_MODEL
        )
        ai_reply = response.choices[0].message.content.strip()
        history.append({"role": "assistant", "content": ai_reply})
        return ai_reply
    except Exception as e:
        print(f"Error calling AI API: {e}")
        return "woah bro my circuits just lagged out"

# --- 5. Discord Bot Events ---

@bot.event
async def on_ready():
    """Called when the bot successfully logs in."""
    print(f"bot logged in as {bot.user}")
    print("--------------------")
    
    try:
        activity = discord.Game(name="Lifting Firewalls")
        await bot.change_presence(status=discord.Status.online, activity=activity)
        print("Bot presence set to 'Playing Lifting Firewalls'")
    except Exception as e:
        print(f"Error setting presence: {e}")
        
    try:
        print("Syncing slash commands...")
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")
        
    # --- Log auto-response channel ---
    if AUTO_RESPONSE_CHANNEL_ID:
        print(f"Auto-responding in channel: {AUTO_RESPONSE_CHANNEL_ID}")
    else:
        print("AUTO_RESPONSE_CHANNEL_ID not set. Responding only to DMs and @mentions.")
        
    # --- Start the Epic Games task loop ---
    if not EPIC_GAMES_CHANNEL_ID:
        print("EPIC_GAMES_CHANNEL_ID not set in .env. Free game checking is DISABLED.")
    else:
        print(f"Starting free game check loop for channel {EPIC_GAMES_CHANNEL_ID}.")
        check_free_games.start()

# --- Police & Thief Game Functions (Unchanged) ---
async def start_new_round(channel: discord.TextChannel, game: dict):
    player_ids = game["player_ids"]
    player_objects = []
    dm_errors = []
    for player_id in player_ids:
        try:
            player = await bot.fetch_user(player_id)
            player_objects.append(player)
        except discord.NotFound:
            await channel.send(f"Error: Player with ID {player_id} not found. Canceling game.")
            if str(channel.id) in active_games: del active_games[str(channel.id)]; save_games()
            return False
        except Exception as e:
            await channel.send(f"Error fetching player {player_id}: {e}. Canceling game.")
            if str(channel.id) in active_games: del active_games[str(channel.id)]; save_games()
            return False
            
    deck = [POLICE_ROLE, THIEF_ROLE]
    other_roles_to_add = OTHER_ROLES.copy(); random.shuffle(other_roles_to_add)
    remaining_slots = len(player_objects) - 2
    for i in range(remaining_slots):
        deck.append(other_roles_to_add.pop(0) if other_roles_to_add else VILLAGER_ROLE)
    random.shuffle(deck)
    assigned_roles = {}
    police_user_id = None; thief_user_id = None
    for i, player in enumerate(player_objects):
        role_name, role_points = deck[i]
        assigned_roles[str(player.id)] = { "role": role_name, "points": role_points }
        if role_name == "Police": police_user_id = player.id
        if role_name == "Thief": thief_user_id = player.id
        try:
            await player.send(f"In **{channel.guild.name}** (Round {game['current_round']}), your role is: **{role_name}**")
        except discord.Forbidden: print(f"Failed to DM {player.name}. DMs are closed."); dm_errors.append(player)
        except Exception as e: print(f"Error DMing {player.name}: {e}"); dm_errors.append(player)
    if dm_errors:
        mentions = ", ".join(p.mention for p in dm_errors)
        await channel.send(f"Yo, {mentions}! I couldn't DM you. Fix your privacy settings. **Game canceled.**")
        if str(channel.id) in active_games: del active_games[str(channel.id)]; save_games()
        return False
    game["current_round_data"] = {"assigned_roles": assigned_roles, "police_user_id": police_user_id, "thief_user_id": thief_user_id}
    await channel.send(f"--- **Round {game['current_round']} / {game['total_rounds']}** ---\n"
                     f"I've DMed everyone their roles.\n\n"
                     f"<@{police_user_id}>, you're the **Police**. Find the thief!\n"
                     f"Use `/guess user:@name` to make your move.")
    return True

# --- Epic Games Notifier Functions ---

def parse_epic_date(date_str):
    """Converts Epic's ISO 8601 date string to a timezone-aware datetime object."""
    try:
        if date_str.endswith('Z'):
            return datetime.fromisoformat(date_str[:-1] + '+00:00')
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None

async def post_game_embed(channel, game_data):
    """Builds and sends the embed for a free game."""
    title = game_data.get('title', 'Unknown Game')
    description = game_data.get('description', 'No description available.')
    if len(description) > 300:
        description = description[:300] + "..."
        
    image_url = None
    for img in game_data.get('keyImages', []):
        if img['type'] == 'OfferImageWide':
            image_url = img['url']
            break
            
    slug = game_data.get('productSlug')
    if not slug:
        for mapping in game_data.get('offerMappings', []):
            if mapping.get('pageSlug'):
                slug = mapping['pageSlug']
                break
                
    if not slug:
        print(f"Could not find a page slug for {title}. Skipping."); return
        
    page_url = f"https://store.epicgames.com/p/{slug}"
    
    end_date_str = "Unknown"
    try:
        promo_offers = game_data['promotions']['promotionalOffers']
        if promo_offers:
            offer = promo_offers[0]['promotionalOffers'][0]
            end_date_obj = parse_epic_date(offer['endDate'])
            if end_date_obj:
                end_date_str = f"<t:{int(end_date_obj.timestamp())}:R>"
    except Exception as e:
        print(f"Error parsing end date for {title}: {e}")

    embed = discord.Embed(
        title=f"FREE GAME: {title}",
        description=description,
        url=page_url,
        color=discord.Color.from_rgb(0, 120, 255)
    )
    if image_url:
        embed.set_image(url=image_url)
    embed.add_field(name="Available Until", value=end_date_str, inline=False)
    embed.set_footer(text="From the Epic Games Store")
    embed.timestamp = datetime.now(timezone.utc)
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label=f"Claim {title}", style=discord.ButtonStyle.link, url=page_url, emoji="🎁"))
    
    try:
        await channel.send(f"Yo @everyone, new free game just dropped!", embed=embed, view=view)
        print(f"Successfully posted free game: {title}")
    except discord.Forbidden:
        print(f"Error: Bot lacks permissions to send messages in channel {channel.id}")
    except Exception as e:
        print(f"Error sending game embed: {e}")

@tasks.loop(hours=6)
async def check_free_games():
    """Checks the Epic Games API for new free games."""
    await bot.wait_until_ready() 
    
    if not EPIC_GAMES_CHANNEL_ID:
        print("Free game check skipped: No channel ID set."); return
        
    try:
        channel = bot.get_channel(int(EPIC_GAMES_CHANNEL_ID))
        if not channel:
            print(f"Error: Could not find channel with ID {EPIC_GAMES_CHANNEL_ID}. Disabling game check.")
            check_free_games.stop(); return
    except ValueError:
        print(f"Error: Invalid EPIC_GAMES_CHANNEL_ID '{EPIC_GAMES_CHANNEL_ID}'. Disabling game check.")
        check_free_games.stop(); return

    print("Task: Checking for new free Epic Games...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(EPIC_GAMES_API_URL) as resp:
                if resp.status != 200:
                    print(f"Error fetching from Epic API: Status {resp.status}"); return
                data = await resp.json()

        games = data.get('data', {}).get('Catalog', {}).get('searchStore', {}).get('elements', [])
        if not games:
            print("No games found in Epic API response."); return

        now = datetime.now(timezone.utc)
        new_games_found = 0
        
        for game in games:
            game_id = game.get('id')
            if not game_id or game_id in posted_games_cache:
                continue
                
            promotions = game.get('promotions', {})
            current_offers = promotions.get('promotionalOffers', [])
            if not current_offers:
                continue
            
            try:
                offer = current_offers[0]['promotionalOffers'][0]
                start_date = parse_epic_date(offer.get('startDate'))
                end_date = parse_epic_date(offer.get('endDate'))
                discount_perc = offer.get('discountSetting', {}).get('discountPercentage', 100)

                if start_date and end_date and discount_perc == 0 and start_date <= now <= end_date:
                    await post_game_embed(channel, game)
                    posted_games_cache.add(game_id)
                    new_games_found += 1
                    
            except (IndexError, KeyError, TypeError):
                pass
                
        if new_games_found > 0:
            print(f"Found and posted {new_games_found} new free games.")
            save_posted_games() # Save the cache
        else:
            print("No *new* free games found.")

    except Exception as e:
        print(f"An error occurred during the free game check: {e}")

# --- Slash Commands ---

@bot.tree.command(name="policeandthief", description="Start a new game of Police and Thief")
@app_commands.describe(
    rounds="How many rounds to play",
    p1="Player 1 (Required)", p2="Player 2 (Required)",
    p3="Player 3 (Required)", p4="Player 4 (Required)",
    p5="Player 5 (Optional)", p6="Player 6 (Optional)",
    p7="Player 7 (Optional)", p8="Player 8 (Optional)",
    p9="Player 9 (Optional)", p10="Player 10 (Optional)"
)
async def policeandthief(
    interaction: discord.Interaction, rounds: int,
    p1: discord.Member, p2: discord.Member, p3: discord.Member, p4: discord.Member,
    p5: discord.Member = None, p6: discord.Member = None, p7: discord.Member = None,
    p8: discord.Member = None, p9: discord.Member = None, p10: discord.Member = None
):
    channel_id_str = str(interaction.channel_id)
    if channel_id_str in active_games:
        await interaction.response.send_message("game's already running in this channel, champ. finish it or use `/endgame`.", ephemeral=True); return
    if rounds <= 0:
        await interaction.response.send_message("you gotta play at least 1 round, bro.", ephemeral=True); return
    
    players = [p for p in [p1, p2, p3, p4, p5, p6, p7, p8, p9, p10] if p is not None]
    
    if len(players) != len(set(players)):
        await interaction.response.send_message("you mentioned the same person twice, champ. try again.", ephemeral=True); return
    if len(players) < MIN_PLAYERS:
        await interaction.response.send_message(f"not enough players, bro. need at least {MIN_PLAYERS} to get a good game.", ephemeral=True); return
        
    player_ids = [p.id for p in players]
    active_games[channel_id_str] = {
        "total_rounds": rounds, "current_round": 1, "player_ids": player_ids,
        "scoreboard": {str(p_id): 0 for p_id in player_ids}, "current_round_data": {} 
    }
    game = active_games[channel_id_str]
    await interaction.response.send_message(f"Aight, starting a **{rounds}-round** game for {len(players)} players. Let's go.")
    
    if await start_new_round(interaction.channel, game):
        save_games()

@bot.tree.command(name="guess", description="Make your guess as the Police")
@app_commands.describe(user="The player you accuse of being the thief")
async def guess(interaction: discord.Interaction, user: discord.Member):
    channel_id_str = str(interaction.channel_id)
    game = active_games.get(channel_id_str)
    
    if not game: await interaction.response.send_message("no game running, champ.", ephemeral=True); return
    round_data = game.get("current_round_data")
    if not round_data: await interaction.response.send_message("hold up, round's not ready. maybe the bot just restarted?", ephemeral=True); return
    if interaction.user.id != round_data["police_user_id"]:
        await interaction.response.send_message("not your job, bro. only the Police can guess.", ephemeral=True); return
        
    guessed_user = user; thief_user_id = round_data["thief_user_id"]; police_user_id = round_data["police_user_id"]
    results_text = f"--- **Round {game['current_round']} / {game['total_rounds']} Results** ---\n\n"
    round_scores = {}; police_base_points = round_data["assigned_roles"][str(police_user_id)]["points"]
    
    if guessed_user.id == thief_user_id:
        results_text += f"Busted! <@{police_user_id}> correctly caught the thief, <@{thief_user_id}>!\n"
        round_scores[police_user_id] = police_base_points; round_scores[thief_user_id] = 0
    else:
        results_text += f"Oof! <@{police_user_id}> guessed {guessed_user.mention}, but the *real* thief was <@{thief_user_id}>!\n"
        results_text += f"The **Thief** gets the Police's {police_base_points} points!\n"
        round_scores[police_user_id] = 0; round_scores[thief_user_id] = police_base_points

    results_text += "\n**Round Scores:**\n"
    
    for player_id_str, data in round_data["assigned_roles"].items():
        player_id_int = int(player_id_str)
        if player_id_int not in round_scores: round_scores[player_id_int] = data["points"]
        points_this_round = round_scores[player_id_int]
        game["scoreboard"][player_id_str] += points_this_round
        results_text += f"<@{player_id_str}>: **{data['role']}** (+{points_this_round} points)\n"

    sorted_scoreboard = sorted(game["scoreboard"].items(), key=lambda item: item[1], reverse=True)
    scoreboard_text = "\n**Overall Scoreboard:**\n"
    for player_id_str, total_score in sorted_scoreboard:
        scoreboard_text += f"<@{player_id_str}>: **{total_score}** points\n"
        
    await interaction.response.send_message(results_text + scoreboard_text)
    
    if game["current_round"] < game["total_rounds"]:
        game["current_round"] += 1; game["current_round_data"] = {}
        await interaction.followup.send(f"\nGet ready... Starting round **{game['current_round']}** in 5 seconds.")
        await asyncio.sleep(5)
        if await start_new_round(interaction.channel, game): save_games()
    else:
        winner_id_str, winner_score = sorted_scoreboard[0]
        await interaction.followup.send(f"\n--- **FINAL GAME OVER** ---\n"
                                 f"🏆 The winner is <@{winner_id_str}> with **{winner_score}** points! 🏆")
        del active_games[channel_id_str]; save_games()

@bot.tree.command(name="endgame", description="Force-end the current game in this channel")
async def endgame(interaction: discord.Interaction):
    channel_id_str = str(interaction.channel_id)
    if channel_id_str in active_games:
        del active_games[channel_id_str]; save_games()
        await interaction.response.send_message("aight, fine. game over. way to quit.")
    else:
        await interaction.response.send_message("nothin' to end, bro.", ephemeral=True)

@bot.tree.command(name="clear", description="Clear Gymbrootan's conversation history in this channel")
async def clear(interaction: discord.Interaction):
    channel_id_str = str(interaction.channel_id)
    if channel_id_str in conversation_history and len(conversation_history[channel_id_str]) > 0:
        conversation_history[channel_id_str].clear(); save_history() 
        print(f"Cleared history for channel {channel_id_str}")
        await interaction.response.send_message("aight, memory banks wiped. we're starting fresh, bro")
    else:
        await interaction.response.send_message("we ain't even talked, bro. nothin' to clear", ephemeral=True)

@bot.tree.command(name="force_check_games", description="Admin: Manually check for new free Epic Games.")
@app_commands.checks.has_permissions(administrator=True) # Only admins
async def force_check_games(interaction: discord.Interaction):
    await interaction.response.send_message("aight, boss. forcing a check for free games... one sec.", ephemeral=True)
    try:
        await check_free_games.callback()
        await interaction.followup.send("Check complete. See the post channel for any new games.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Check failed, bro. Got a glitch: {e}", ephemeral=True)

@force_check_games.error
async def force_check_games_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("nah, you ain't got the reps for that, bro. (Admin only)", ephemeral=True)
    else:
        await interaction.response.send_message(f"woah, that command glitched: {error}", ephemeral=True)

# --- AI Chat Event: on_message ---

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
        
    is_dm = isinstance(message.channel, discord.DMChannel)
    
    is_auto_channel = False
    if AUTO_RESPONSE_CHANNEL_ID: 
        is_auto_channel = str(message.channel.id) == AUTO_RESPONSE_CHANNEL_ID
    
    # Respond if: DM, @mention, or in the auto-response channel
    if not (bot.user.mentioned_in(message) or is_dm or is_auto_channel):
        return

    clean_content = message.content.replace(f"<@{bot.user.id}>", "").strip()
    
    if not clean_content:
        # Only ignore empty @mentions. Don't ignore "empty" messages in auto-channel (e.g., just an attachment)
        if not is_auto_channel and not is_dm: 
             return 

    ai_response = get_ai_response(message.channel.id, clean_content)
        
    if ai_response:
        sentences = re.split(r'(?<=[.!?])\s+', ai_response.strip())
        total_length = len(ai_response)
        
        if total_length < 80 or len(sentences) <= 1:
            try:
                async with message.channel.typing():
                    delay = max(0.5, min(total_length / 15, 1.5))
                    await asyncio.sleep(delay)
                    await message.reply(ai_response, mention_author=False)
            except discord.errors.Forbidden: print(f"Error: Bot lacks permissions in channel {message.channel.id}")
            except Exception as e: print(f"Error sending message: {e}")
            return
            
        first_sentence = True
        for sentence in sentences:
            if not sentence: continue
            delay = max(0.8, min(len(sentence) / 15, 2.5))
            try:
                async with message.channel.typing():
                    await asyncio.sleep(delay)
                    if first_sentence:
                        await message.reply(sentence, mention_author=False)
                        first_sentence = False
                    else:
                        await message.channel.send(sentence)
            except discord.errors.Forbidden: print(f"Error: Bot lacks permissions in channel {message.channel.id}"); break
            except Exception as e: print(f"Error sending message: {e}"); break

# --- 6. Run the Bot ---
if __name__ == "__main__":
    if not DISCORD_TOKEN or not GITHUB_TOKEN:
        print("Error: DISCORD_TOKEN or GITHUB_TOKEN not found in .env file.")
        print("Please create a .env file and add your tokens.")
    else:
        print("Starting Gymbrootan bot...")
        keep_alive() # Keep the web server running
        bot.run(DISCORD_TOKEN)

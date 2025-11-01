import os
import discord
import json
import atexit
import re
import asyncio
import random
from discord.ext import commands  # <-- NEW: Import commands
from discord import app_commands # <-- NEW: Import app_commands
from openai import OpenAI
from dotenv import load_dotenv
from collections import deque
from keep_alive import keep_alive

# --- 1. Load Configuration ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# --- 2. AI API Configuration ---
AI_ENDPOINT = "https://models.github.ai/inference"
AI_MODEL = "openai/gpt-4o"
HISTORY_FILE = "conversation_history.json"
GAMES_FILE = "active_games.json" 

# --- 3. Bot & Memory Setup ---

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True # REQUIRED for game mentions


SHORT_TERM_MEMORY_LIMIT=16
# --- NEW: Use commands.Bot instead of discord.Client ---
# We give it a prefix it will never use, since we're all slash.
bot = commands.Bot(command_prefix="!_THIS_IS_DISABLED", intents=intents)

# --- PERSONA (Unchanged) ---
SYSTEM_PROMPT = """You are Gymbrootan...""" # (Your full prompt is unchanged)

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

# --- History & Game Persistence Functions (Unchanged) ---
# (save_history, load_history, save_games, load_games functions)
# ... (all these functions are identical to your previous code) ...
def save_history():
    serializable_history = {cid: list(hist) for cid, hist in conversation_history.items()}
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(serializable_history, f, indent=4)
        print("Conversation history saved.")
    except Exception as e:
        print(f"Error saving history: {e}")

atexit.register(save_history)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        print("No history file found. Starting fresh.")
        return {}
    try:
        with open(HISTORY_FILE, "r") as f:
            loaded_data = json.load(f)
            history = {
                str(cid): deque(hist_list, maxlen=SHORT_TERM_MEMORY_LIMIT)
                for cid, hist_list in loaded_data.items()
            }
            print(f"Loaded history for {len(history)} channels.")
            return history
    except Exception as e:
        print(f"Error loading history: {e}. Starting fresh.")
        return {}

conversation_history = load_history()

def save_games():
    try:
        with open(GAMES_FILE, "w") as f:
            json.dump(active_games, f, indent=4)
        print("Active games saved.")
    except Exception as e:
        print(f"Error saving active games: {e}")

def load_games():
    if not os.path.exists(GAMES_FILE):
        print("No active games file found. Starting fresh.")
        return {}
    try:
        with open(GAMES_FILE, "r") as f:
            loaded_data = json.load(f)
            print(f"Loaded {len(loaded_data)} active games.")
            return {str(cid): g for cid, g in loaded_data.items()}
    except Exception as e:
        print(f"Error loading active games: {e}. Starting fresh.")
        return {}

active_games = load_games()
atexit.register(save_games)

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
        
    # --- NEW: Sync Slash Commands ---
    try:
        print("Syncing slash commands...")
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

# --- REFACTORED: Game Helper Functions (Now use `channel` or `interaction`) ---

async def start_new_round(channel: discord.TextChannel, game: dict):
    """
    Deals roles and DMs players. Takes a channel object to send messages to.
    """
    player_ids = game["player_ids"]
    
    player_objects = []
    dm_errors = []
    for player_id in player_ids:
        try:
            player = await bot.fetch_user(player_id)
            player_objects.append(player)
        except discord.NotFound:
            await channel.send(f"Error: Player with ID {player_id} not found. Canceling game.")
            if str(channel.id) in active_games:
                del active_games[str(channel.id)]
                save_games()
            return False
        except Exception as e:
            await channel.send(f"Error fetching player {player_id}: {e}. Canceling game.")
            if str(channel.id) in active_games:
                del active_games[str(channel.id)]
                save_games()
            return False
            
    deck = [POLICE_ROLE, THIEF_ROLE]
    other_roles_to_add = OTHER_ROLES.copy()
    random.shuffle(other_roles_to_add)
    remaining_slots = len(player_objects) - 2
    for i in range(remaining_slots):
        deck.append(other_roles_to_add.pop(0) if other_roles_to_add else VILLAGER_ROLE)
    random.shuffle(deck)
    
    assigned_roles = {}
    police_user_id = None
    thief_user_id = None

    for i, player in enumerate(player_objects):
        role_name, role_points = deck[i]
        
        assigned_roles[str(player.id)] = { "role": role_name, "points": role_points }
        
        if role_name == "Police": police_user_id = player.id
        if role_name == "Thief": thief_user_id = player.id
            
        try:
            await player.send(f"In **{channel.guild.name}** (Round {game['current_round']}), your role is: **{role_name}**")
        except discord.Forbidden:
            print(f"Failed to DM {player.name}. DMs are closed.")
            dm_errors.append(player)
        except Exception as e:
            print(f"Error DMing {player.name}: {e}")
            dm_errors.append(player)

    if dm_errors:
        mentions = ", ".join(p.mention for p in dm_errors)
        await channel.send(f"Yo, {mentions}! I couldn't DM you. Fix your privacy settings. **Game canceled.**")
        if str(channel.id) in active_games:
            del active_games[str(channel.id)]
            save_games()
        return False

    game["current_round_data"] = {
        "assigned_roles": assigned_roles,
        "police_user_id": police_user_id,
        "thief_user_id": thief_user_id
    }
    
    # Use channel.send (this is a followup message, not the first reply)
    await channel.send(f"--- **Round {game['current_round']} / {game['total_rounds']}** ---\n"
                     f"I've DMed everyone their roles.\n\n"
                     f"<@{police_user_id}>, you're the **Police**. Find the thief!\n"
                     f"Use `/guess user:@name` to make your move.")
    return True

# --- NEW: Slash Command for Starting Game ---

@bot.tree.command(name="policeandthief", description="Start a new game of Police and Thief")
@app_commands.describe(
    rounds="How many rounds to play",
    p1="Player 1 (Required)",
    p2="Player 2 (Required)",
    p3="Player 3 (Required)",
    p4="Player 4 (Required)",
    p5="Player 5 (Optional)",
    p6="Player 6 (Optional)",
    p7="Player 7 (Optional)",
    p8="Player 8 (Optional)",
    p9="Player 9 (Optional)",
    p10="Player 10 (Optional)"
)
async def policeandthief(
    interaction: discord.Interaction, 
    rounds: int,
    p1: discord.Member,
    p2: discord.Member,
    p3: discord.Member,
    p4: discord.Member,
    p5: discord.Member = None,
    p6: discord.Member = None,
    p7: discord.Member = None,
    p8: discord.Member = None,
    p9: discord.Member = None,
    p10: discord.Member = None
):
    """Handles the /policeandthief command"""
    channel_id_str = str(interaction.channel_id)
    if channel_id_str in active_games:
        await interaction.response.send_message("game's already running in this channel, champ. finish it or use `/endgame`.", ephemeral=True)
        return

    if rounds <= 0:
        await interaction.response.send_message("you gotta play at least 1 round, bro.", ephemeral=True)
        return
    
    # Collect all players, filtering out None
    players = [p for p in [p1, p2, p3, p4, p5, p6, p7, p8, p9, p10] if p is not None]
    
    # Check for duplicate players
    if len(players) != len(set(players)):
        await interaction.response.send_message("you mentioned the same person twice, champ. try again.", ephemeral=True)
        return
        
    if len(players) < MIN_PLAYERS:
        await interaction.response.send_message(f"not enough players, bro. need at least {MIN_PLAYERS} to get a good game.", ephemeral=True)
        return
        
    player_ids = [p.id for p in players]
    
    active_games[channel_id_str] = {
        "total_rounds": rounds,
        "current_round": 1,
        "player_ids": player_ids,
        "scoreboard": {str(p_id): 0 for p_id in player_ids},
        "current_round_data": {} 
    }
    game = active_games[channel_id_str]
    
    # Send the *first* response to the interaction
    await interaction.response.send_message(f"Aight, starting a **{rounds}-round** game for {len(players)} players. Let's go.")
    
    # Start the first round. Pass the channel object.
    if await start_new_round(interaction.channel, game):
        save_games()

# --- NEW: Slash Command for Guessing ---

@bot.tree.command(name="guess", description="Make your guess as the Police")
@app_commands.describe(user="The player you accuse of being the thief")
async def guess(interaction: discord.Interaction, user: discord.Member):
    """Handles the /guess command"""
    channel_id_str = str(interaction.channel_id)
    game = active_games.get(channel_id_str)
    
    if not game:
        await interaction.response.send_message("no game running, champ.", ephemeral=True)
        return
    
    round_data = game.get("current_round_data")
    if not round_data:
        await interaction.response.send_message("hold up, round's not ready. maybe the bot just restarted?", ephemeral=True)
        return
        
    if interaction.user.id != round_data["police_user_id"]:
        await interaction.response.send_message("not your job, bro. only the Police can guess.", ephemeral=True)
        return
        
    guessed_user = user
    thief_user_id = round_data["thief_user_id"]
    police_user_id = round_data["police_user_id"]
    
    results_text = f"--- **Round {game['current_round']} / {game['total_rounds']} Results** ---\n\n"
    
    round_scores = {}
    police_base_points = round_data["assigned_roles"][str(police_user_id)]["points"]
    
    if guessed_user.id == thief_user_id:
        results_text += f"Busted! <@{police_user_id}> correctly caught the thief, <@{thief_user_id}>!\n"
        round_scores[police_user_id] = police_base_points
        round_scores[thief_user_id] = 0
    else:
        results_text += f"Oof! <@{police_user_id}> guessed {guessed_user.mention}, but the *real* thief was <@{thief_user_id}>!\n"
        results_text += f"The **Thief** gets the Police's {police_base_points} points!\n"
        round_scores[police_user_id] = 0
        round_scores[thief_user_id] = police_base_points

    results_text += "\n**Round Scores:**\n"
    
    for player_id_str, data in round_data["assigned_roles"].items():
        player_id_int = int(player_id_str)
        if player_id_int not in round_scores:
            round_scores[player_id_int] = data["points"]
            
        points_this_round = round_scores[player_id_int]
        game["scoreboard"][player_id_str] += points_this_round
        
        results_text += f"<@{player_id_str}>: **{data['role']}** (+{points_this_round} points)\n"

    sorted_scoreboard = sorted(game["scoreboard"].items(), key=lambda item: item[1], reverse=True)
    
    scoreboard_text = "\n**Overall Scoreboard:**\n"
    for player_id_str, total_score in sorted_scoreboard:
        scoreboard_text += f"<@{player_id_str}>: **{total_score}** points\n"
        
    # Send the *first* (and only) reply for this command
    await interaction.response.send_message(results_text + scoreboard_text)
    
    # --- Check Game State (Next Round or Game Over) ---
    if game["current_round"] < game["total_rounds"]:
        game["current_round"] += 1
        game["current_round_data"] = {} # Clear old round data
        
        # Use followup.send for messages *after* the initial response
        await interaction.followup.send(f"\nGet ready... Starting round **{game['current_round']}** in 5 seconds.")
        await asyncio.sleep(5)
        
        if await start_new_round(interaction.channel, game):
            save_games()
    else:
        winner_id_str, winner_score = sorted_scoreboard[0]
        # Use followup.send
        await interaction.followup.send(f"\n--- **FINAL GAME OVER** ---\n"
                                 f"🏆 The winner is <@{winner_id_str}> with **{winner_score}** points! 🏆")
        del active_games[channel_id_str]
        save_games()

# --- NEW: Slash Command for Ending Game ---

@bot.tree.command(name="endgame", description="Force-end the current game in this channel")
async def endgame(interaction: discord.Interaction):
    """Handles the /endgame command"""
    channel_id_str = str(interaction.channel_id)
    if channel_id_str in active_games:
        del active_games[channel_id_str]
        save_games()
        await interaction.response.send_message("aight, fine. game over. way to quit.", mention_author=False)
    else:
        await interaction.response.send_message("nothin' to end, bro.", ephemeral=True)

# --- NEW: Slash Command for Clearing History ---

@bot.tree.command(name="clear", description="Clear Gymbrootan's conversation history in this channel")
async def clear(interaction: discord.Interaction):
    """Handles the /clear command"""
    channel_id_str = str(interaction.channel_id)
    if channel_id_str in conversation_history and len(conversation_history[channel_id_str]) > 0:
        conversation_history[channel_id_str].clear()
        save_history() 
        print(f"Cleared history for channel {channel_id_str}")
        await interaction.response.send_message("aight, memory banks wiped. we're starting fresh, bro")
    else:
        await interaction.response.send_message("we ain't even talked, bro. nothin' to clear", ephemeral=True)

# --- REFACTORED: on_message for AI CHAT ONLY ---

@bot.event
async def on_message(message):
    """
    Called every time a message is sent.
    This now *only* handles the AI persona chat.
    All commands are handled by the bot.tree.
    """
    
    if message.author == bot.user:
        return
        
    is_dm = isinstance(message.channel, discord.DMChannel)
    
    # 2. Check if the bot should reply (DM or @mention)
    if not (bot.user.mentioned_in(message) or is_dm):
        return

    # 3. Clean the message content
    clean_content = message.content.replace(f"<@{bot.user.id}>", "").strip()
    
    if not clean_content:
        return # Was just an empty @mention

    # 4. Get the AI's response
    ai_response = get_ai_response(message.channel.id, clean_content)
        
    # 6. Send the reply (This logic is unchanged)
    if ai_response:
        sentences = re.split(r'(?<=[.!?])\s+', ai_response.strip())
        total_length = len(ai_response)
        
        if total_length < 80 or len(sentences) <= 1:
            try:
                async with message.channel.typing():
                    delay = max(0.5, min(total_length / 15, 1.5))
                    await asyncio.sleep(delay)
                    await message.reply(ai_response, mention_author=False)
            except discord.errors.Forbidden:
                print(f"Error: Bot lacks permissions to send messages in channel {message.channel.id} (Guild: {message.guild.name if message.guild else 'DM'})")
            except Exception as e:
                print(f"Error sending Discord message: {e}")
            return
            
        first_sentence = True
        for sentence in sentences:
            if not sentence:
                continue
            
            delay = len(sentence) / 15
            delay = max(0.8, min(delay, 2.5))
            
            try:
                async with message.channel.typing():
                    await asyncio.sleep(delay)

                    if first_sentence:
                        await message.reply(sentence, mention_author=False)
                        first_sentence = False
                    else:
                        await message.channel.send(sentence)

            except discord.errors.Forbidden:
                print(f"Error: Bot lacks permissions to send messages in channel {message.channel.id} (Guild: {message.guild.name if message.guild else 'DM'})")
                break
            except Exception as e:
                print(f"Error sending Discord message: {e}")
                break

# --- 6. Run the Bot (Unchanged) ---
if __name__ == "__main__":
    if not DISCORD_TOKEN or not GITHUB_TOKEN:
        print("Error: DISCORD_TOKEN or GITHUB_TOKEN not found in .env file.")
        print("Please create a .env file and add your tokens.")
    else:
        print("Starting Gymbrootan bot...")
        keep_alive()
        bot.run(DISCORD_TOKEN)


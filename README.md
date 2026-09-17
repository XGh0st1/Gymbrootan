# Your Discord Bot

A fun/engagement/utility bot for you and your friends' server. Includes:

- **Fun**: `/eightball`, `/coinflip`, `/roll`, `/meme`, `/joke`, `/ship`, `/rps`
- **Leveling**: passive XP from chatting, `/rank`, `/leaderboard`, level-up announcements
- **Utility**: `/serverinfo`, `/userinfo`, `/avatar`, `/poll`, `/remind`
- **Moderation**: `/kick`, `/ban`, `/timeout`, `/warn`, `/warnings`, `/clear`
- **Welcome/Goodbye**: `/setwelcome`, `/setgoodbye` + automatic join/leave messages
- **Music**: `/join`, `/play`, `/skip`, `/pause`, `/resume`, `/stop`, `/queue`, `/nowplaying`, `/leave`
- **Birthdays**: `/setbirthday`, `/setbirthdaychannel`, `/birthdays` + automatic daily shoutouts
- **Trivia**: `/trivia` — a button-based multiple-choice question anyone in the channel can answer

All commands work as both slash commands (`/command`) and text commands (`!command`).

## 1. Create the bot on Discord's Developer Portal

1. Go to https://discord.com/developers/applications and click **New Application**.
2. Name it, then go to the **Bot** tab → **Add Bot**.
3. Under **Privileged Gateway Intents**, turn on:
   - **Server Members Intent** (needed for welcome/goodbye and userinfo)
   - **Message Content Intent** (needed for text commands and leveling)
4. Click **Reset Token** and copy it — you'll only see it once. Keep it secret.

## 2. Invite the bot to your server

1. Go to the **OAuth2 → URL Generator** tab.
2. Under **Scopes**, check `bot` and `applications.commands`.
3. Under **Bot Permissions**, check: Manage Messages, Kick Members, Ban Members,
   Moderate Members, Read Messages/View Channels, Send Messages, Embed Links,
   Add Reactions, Manage Roles (if you want role rewards later).
4. Copy the generated URL, open it in your browser, and select your server.

## 3. Set up the project locally

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Open .env and paste your bot token in place of "your_bot_token_here"
```

## 4. Run it

```bash
python main.py
```

You should see log lines confirming the bot logged in and synced slash commands.
Slash commands can take up to an hour to show up globally the first time — if you
want them instantly for testing, sync to a single guild instead (ask me and I'll
add that).

## 5. Extra setup for music

Music playback needs two extra things beyond `pip install`:

1. **FFmpeg** installed on whatever machine actually runs the bot (not a Python
   package — a system binary):
   - Windows: download from https://ffmpeg.org/download.html and add it to your PATH.
   - macOS: `brew install ffmpeg`
   - Linux (Debian/Ubuntu): `sudo apt install ffmpeg`
2. Make sure the bot's invite includes the **Connect** and **Speak** voice
   permissions (already included in the invite scopes above).

One thing worth knowing: streaming audio from YouTube via tools like `yt-dlp`
sits in a legal/ToS gray area — YouTube's terms don't permit it, even though
it's extremely common in hobby bots. It's unlikely to cause any issue for a
small private server, but worth being aware of if you ever want to run this
publicly or at scale.

## 6. Keep it running 24/7

Running it on your own laptop only works while your laptop's on. Options to keep
it running all the time:

- **Railway** or **Fly.io** — free/cheap tiers, connect your GitHub repo, set
  `DISCORD_TOKEN` as an environment variable in their dashboard, done.
- **A cheap VPS** (Oracle Cloud free tier, DigitalOcean, etc.) — run it inside
  `tmux`/`screen`, or set it up as a `systemd` service so it restarts on crash/reboot.
- **Raspberry Pi** at home — works great for a friends-server bot, just needs to
  stay powered on.

## 7. Extending it

Each feature lives in its own file under `cogs/`. To add a new feature:

1. Create `cogs/yourfeature.py` following the pattern in the existing cogs
   (a `commands.Cog` subclass + an `async def setup(bot)` at the bottom).
2. Add `"cogs.yourfeature"` to the `EXTENSIONS` tuple in `main.py`.
3. Restart the bot.

Ideas for what to add next: custom server commands, giveaways, Twitch/YouTube
upload alerts, or a starboard (auto-pin popular messages). Happy to build any
of these out — just ask.

## Notes

- `bot.db` (SQLite) is created automatically on first run in the project folder —
  back it up if you care about warnings/level history.
- Never commit your real `.env` file or paste your token anywhere public — if it
  leaks, reset it immediately in the Developer Portal.

import aiosqlite

DB_PATH = "bot.db"


async def init_db():
    """Create all tables the bot needs, if they don't already exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS levels (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                timestamp REAL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER,
                goodbye_channel_id INTEGER,
                birthday_channel_id INTEGER
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id INTEGER,
                remind_at REAL,
                message TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id INTEGER,
                guild_id INTEGER,
                month INTEGER,
                day INTEGER,
                PRIMARY KEY (user_id, guild_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS game_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                creator_id INTEGER,
                game_name TEXT,
                start_time REAL,
                party_link TEXT,
                channel_id INTEGER,
                message_id INTEGER
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS event_participants (
                event_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (event_id, user_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_channels (
                guild_id INTEGER,
                channel_id INTEGER,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS welcome_image_config (
                guild_id INTEGER PRIMARY KEY,
                config_json TEXT
            )
            """
        )
        # Upgrade path: if an older bot.db already exists without this column, add it.
        try:
            await db.execute("ALTER TABLE guild_config ADD COLUMN birthday_channel_id INTEGER")
        except Exception:
            pass  # column already exists
        await db.commit()

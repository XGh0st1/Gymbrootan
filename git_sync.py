"""
git_sync.py — GitHub REST API-based persistence for Render Web Service.

Instead of running git CLI commands (unreliable on Render), this module
reads and writes files directly via the GitHub API using HTTP requests.

This allows the bot to:
  - On startup: download memory/ and data/ JSON files from GitHub
  - On schedule: upload updated JSON files back to GitHub

Requires env vars:
  GITHUB_TOKEN  — Personal Access Token with 'repo' scope
  GITHUB_REPO   — e.g. "XGh0st1/Gymbrootan"  (owner/repo)
  GITHUB_BRANCH — branch to sync (default: "main")
"""

import os
import json
import base64
import asyncio
import aiosqlite
import aiohttp

DB_PATH = "bot.db"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "XGh0st1/Gymbrootan")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}/contents"

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MEMORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory")

# ── GitHub API Helpers ────────────────────────────────────────────────────────

def _headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

async def _gh_get_file(path: str):
    """Fetch a file from GitHub. Returns (content_str, sha) or (None, None)."""
    url = f"{API_BASE}/{path}?ref={GITHUB_BRANCH}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                return content, data["sha"]
            return None, None

async def _gh_put_file(path: str, content: str, sha: str = None, message: str = "auto: sync"):
    """Create or update a file on GitHub."""
    url = f"{API_BASE}/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": message,
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=_headers(), json=payload) as resp:
            return resp.status in (200, 201)

async def _gh_list_folder(path: str):
    """List files in a GitHub folder. Returns list of {name, path, sha} or []."""
    url = f"{API_BASE}/{path}?ref={GITHUB_BRANCH}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                items = await resp.json()
                return [i for i in items if i["type"] == "file"]
            return []

# ── Upload helpers ────────────────────────────────────────────────────────────

async def _upload_json_file(local_path: str, remote_path: str):
    """Read a local JSON file and upload it to GitHub."""
    if not os.path.exists(local_path):
        return
    try:
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()
        _, sha = await _gh_get_file(remote_path)
        ok = await _gh_put_file(remote_path, content, sha=sha)
        if ok:
            print(f"[GitSync] ↑ uploaded {remote_path}")
        else:
            print(f"[GitSync] ✗ failed to upload {remote_path}")
    except Exception as e:
        print(f"[GitSync] upload error {remote_path}: {e}")

async def _download_json_file(remote_path: str, local_path: str):
    """Download a file from GitHub and save it locally."""
    try:
        content, _ = await _gh_get_file(remote_path)
        if content is not None:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[GitSync] ↓ downloaded {remote_path}")
    except Exception as e:
        print(f"[GitSync] download error {remote_path}: {e}")

# ── Public API ────────────────────────────────────────────────────────────────

async def push_all():
    """Export DB to JSON + upload all memory/ and data/ files to GitHub."""
    if not GITHUB_TOKEN:
        print("[GitSync] No GITHUB_TOKEN — skipping push.")
        return

    await export_db_to_json()

    # Upload data/ files
    os.makedirs(DATA_DIR, exist_ok=True)
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            local = os.path.join(DATA_DIR, filename)
            remote = f"data/{filename}"
            await _upload_json_file(local, remote)

    # Upload memory/ files (nested guild folders)
    os.makedirs(MEMORY_DIR, exist_ok=True)
    for guild_folder in os.listdir(MEMORY_DIR):
        guild_path = os.path.join(MEMORY_DIR, guild_folder)
        if os.path.isdir(guild_path):
            for filename in os.listdir(guild_path):
                if filename.endswith(".json"):
                    local = os.path.join(guild_path, filename)
                    remote = f"memory/{guild_folder}/{filename}"
                    await _upload_json_file(local, remote)

    print("[GitSync] ✓ Push complete.")

async def pull_all():
    """Download all memory/ and data/ JSON files from GitHub to local disk."""
    if not GITHUB_TOKEN:
        print("[GitSync] No GITHUB_TOKEN — skipping pull.")
        return

    # Download data/
    data_files = await _gh_list_folder("data")
    for item in data_files:
        if item["name"].endswith(".json"):
            local = os.path.join(DATA_DIR, item["name"])
            await _download_json_file(item["path"], local)

    # Download memory/ (recursively)
    guild_folders = await _gh_list_folder("memory")
    # guild_folders will actually return files too — filter directories
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE}/memory?ref={GITHUB_BRANCH}"
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                items = await resp.json()
                for item in items:
                    if item["type"] == "dir":
                        guild_id = item["name"]
                        mem_files = await _gh_list_folder(f"memory/{guild_id}")
                        for mf in mem_files:
                            if mf["name"].endswith(".json"):
                                local = os.path.join(MEMORY_DIR, guild_id, mf["name"])
                                await _download_json_file(mf["path"], local)

    print("[GitSync] ✓ Pull complete.")

# ── DB Export / Import ───────────────────────────────────────────────────────

async def export_db_to_json():
    """Export critical DB tables to local JSON files in data/."""
    os.makedirs(DATA_DIR, exist_ok=True)
    tables = {
        "guild_config":         "SELECT * FROM guild_config",
        "ai_channels":          "SELECT * FROM ai_channels",
        "welcome_image_config": "SELECT * FROM welcome_image_config",
        "levels":               "SELECT * FROM levels",
        "birthdays":            "SELECT * FROM birthdays",
        "warnings":             "SELECT * FROM warnings",
    }
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for name, query in tables.items():
            try:
                async with db.execute(query) as cursor:
                    rows = [dict(r) for r in await cursor.fetchall()]
                with open(os.path.join(DATA_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
                    json.dump(rows, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[GitSync] export {name}: {e}")
    print("[GitSync] ✓ DB exported to data/")

async def import_json_to_db():
    """Restore DB tables from local JSON backups (called after pull_all)."""
    if not os.path.exists(DATA_DIR):
        return

    INSERTS = {
        "guild_config": (
            "INSERT OR IGNORE INTO guild_config "
            "(guild_id, welcome_channel_id, goodbye_channel_id, birthday_channel_id) "
            "VALUES (:guild_id, :welcome_channel_id, :goodbye_channel_id, :birthday_channel_id)"
        ),
        "ai_channels": (
            "INSERT OR IGNORE INTO ai_channels (guild_id, channel_id) "
            "VALUES (:guild_id, :channel_id)"
        ),
        "welcome_image_config": (
            "INSERT OR IGNORE INTO welcome_image_config (guild_id, config_json) "
            "VALUES (:guild_id, :config_json)"
        ),
        "levels": (
            "INSERT OR IGNORE INTO levels (user_id, guild_id, xp, level) "
            "VALUES (:user_id, :guild_id, :xp, :level)"
        ),
        "birthdays": (
            "INSERT OR IGNORE INTO birthdays (user_id, guild_id, month, day) "
            "VALUES (:user_id, :guild_id, :month, :day)"
        ),
        "warnings": (
            "INSERT OR IGNORE INTO warnings (id, user_id, guild_id, moderator_id, reason, timestamp) "
            "VALUES (:id, :user_id, :guild_id, :moderator_id, :reason, :timestamp)"
        ),
    }

    async with aiosqlite.connect(DB_PATH) as db:
        for table, query in INSERTS.items():
            path = os.path.join(DATA_DIR, f"{table}.json")
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    rows = json.load(f)
                for row in rows:
                    try:
                        await db.execute(query, row)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[GitSync] import {table}: {e}")
        await db.commit()
    print("[GitSync] ✓ DB restored from JSON backups")

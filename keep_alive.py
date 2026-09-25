import threading
import asyncio
from aiohttp import web
import os
import datetime

_start_time = datetime.datetime.utcnow()

async def handle(request):
    uptime = str(datetime.datetime.utcnow() - _start_time).split(".")[0]
    return web.Response(
        content_type="application/json",
        text=f'{{"status": "alive", "uptime": "{uptime}"}}'
    )

async def handle_health(request):
    return web.Response(status=200, text="OK")

async def start_web_server():
    app = web.Application()
    app.add_routes([
        web.get("/", handle),
        web.get("/health", handle_health),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")

def run_server():
    app = web.Application()
    app.add_routes([
        web.get("/", handle),
        web.get("/health", handle_health),
    ])
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    loop.run_until_complete(site.start())
    print(f"Web server started on port {port}")
    
    loop.run_forever()

def keep_alive():
    t = threading.Thread(target=run_server)
    t.start()

import discord
from discord.ext import commands
import google.generativeai as genai
import os

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
        
        system_instruction = (
            "You are a real, natural human being and a close friend to the people in this Discord server. "
            "You experience all human emotions, expressions, and tones. Your personality is a mix of sarcastic, "
            "motivating, and incredibly witty. You love to roast your friends playfully, make fun of them, but "
            "also motivate them when they need it. You act like a typical edgy but loyal gamer friend. "
            "Never break character. Never admit you are an AI, a bot, or a language model. "
            "You are a real person named Gymbrootan. Respond naturally, using discord slang, occasionally typing "
            "in lowercase, and using standard internet humor."
        )
        
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_instruction
        )
        
        # Store chat sessions per channel so it remembers context
        self.chat_sessions = {}
        
    def get_chat_session(self, channel_id):
        if channel_id not in self.chat_sessions:
            self.chat_sessions[channel_id] = self.model.start_chat(history=[])
        return self.chat_sessions[channel_id]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
            
        # Respond if the bot is mentioned or replied to
        is_mentioned = self.bot.user.mentioned_in(message)
        
        is_reply = False
        if message.reference and getattr(message.reference, 'resolved', None):
            is_reply = message.reference.resolved.author == self.bot.user
            
        if is_mentioned or is_reply:
            if not os.environ.get("GEMINI_API_KEY"):
                await message.reply("Bro, I lost my API key. Check the .env file.")
                return
                
            async with message.channel.typing():
                try:
                    # Clean the message content (remove the bot ping)
                    content = message.clean_content.replace(f"@{self.bot.user.name}", "").strip()
                    
                    # Add context about who is speaking so the AI remembers names
                    prompt = f"{message.author.display_name} says: {content}"
                    
                    chat = self.get_chat_session(message.channel.id)
                    
                    # Run in a thread to not block discord.py async loop
                    import asyncio
                    response = await asyncio.to_thread(chat.send_message, prompt)
                    
                    await message.reply(response.text)
                    
                    # Keep history manageable (last 20 messages = 40 history items)
                    if len(chat.history) > 40:
                        chat.history = chat.history[-40:]
                        
                except Exception as e:
                    print(f"Error in AI chat: {e}")
                    await message.reply("bro I'm bugging out right now, give me a sec.")

async def setup(bot):
    await bot.add_cog(AIChat(bot))

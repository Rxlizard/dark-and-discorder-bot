
import asyncio
import discord
from discord.ext import commands
from common.config import Config

async def main():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot.load_extension("bots.live_market")
    await bot.load_extension("bots.price_history")
    await bot.load_extension("bots.trade_history")
    await bot.load_extension("bots.trading_post")
    await bot.start(Config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())

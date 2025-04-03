# bots/live_market.py
import discord
from discord.ext import commands, tasks
import aiohttp
from datetime import datetime, timedelta
import logging
from collections import deque
from common.config import Config
from common.constants import MONITORED_ITEMS, RARITY_COLORS

logger = logging.getLogger('DarkAndDarkerDB.LiveMarket')

class LiveMarketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config()
        self.price_message = None
        self.current_prices = {}
        self.price_history = {item_key: deque(maxlen=10) for item_key in MONITORED_ITEMS.keys()}

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f'LiveMarketCog ready as {self.bot.user}')
        channel = self.bot.get_channel(self.config.PRICE_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.config.PRICE_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Error fetching channel: {e}")
                return
        await self.clear_market_channel(channel)
        if not self.update_price_tracker.is_running():
            self.update_price_tracker.start()

    async def clear_market_channel(self, channel: discord.TextChannel):
        try:
            pinned_messages = await channel.pins()
            for msg in pinned_messages:
                try:
                    await msg.unpin()
                except Exception as e:
                    logger.error(f"Error unpinning message {msg.id}: {e}")
            deleted_count = 0
            async for msg in channel.history(limit=None):
                try:
                    await msg.delete()
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting message {msg.id}: {e}")
            logger.info(f"Cleared {deleted_count} messages from channel {channel.id}")
            self.price_message = None
        except Exception as e:
            logger.error(f"Error clearing channel: {e}")

    @tasks.loop(minutes=1)
    async def update_price_tracker(self):
        channel = self.bot.get_channel(self.config.PRICE_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.config.PRICE_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Error fetching channel during update: {e}")
                return
        try:
            async with aiohttp.ClientSession() as session:
                for item_key, item_data in MONITORED_ITEMS.items():
                    try:
                        params = {
                            "item_id": item_data["id"],
                            "limit": 3,
                            "sort": "price",
                            "order": "desc",
                            "condense": "true"
                        }
                        if "rarity" in item_data:
                            params["rarity"] = item_data["rarity"]
                        async with session.get(
                            f"{self.config.BASE_URL}/market",
                            params=params,
                            headers=self.config.HEADERS
                        ) as response:
                            data = await response.json()
                            if data["status"] == "OK" and data["body"]:
                                listings = data["body"]
                                if listings:
                                    current_price = listings[0]['price']
                                    self.price_history[item_key].append(current_price)
                                    self.current_prices[item_key] = current_price
                    except Exception as e:
                        logger.error(f"Error fetching {item_data['name']}: {e}")
                        continue

                try:
                    async with session.get("https://api.darkerdb.com/v1/population") as pop_response:
                        pop_data = await pop_response.json()
                        if pop_data.get("status") == "OK" and pop_data.get("body"):
                            pop_body = pop_data["body"]
                            num_online = pop_body.get("num_online", "N/A")
                            num_lobby = pop_body.get("num_lobby", "N/A")
                            num_dungeon = pop_body.get("num_dungeon", "N/A")
                            population_str = f"**Online:** {num_online}   **Lobby:** {num_lobby}   **Dungeon:** {num_dungeon}"
                        else:
                            population_str = "*No population data*"
                except Exception as e:
                    logger.error(f"Error fetching population data: {e}")
                    population_str = "*No population data*"

            embed = discord.Embed(
                title="📊 Market Watch",
                description="Live prices (1 min updates)",
                color=0x2b2d31,
                timestamp=datetime.now()
            )
            items = list(MONITORED_ITEMS.values())
            for i in range(0, len(items), 3):
                row = items[i:i+3]
                for item in row:
                    item_key = item["name"].lower().replace(" ", "_")
                    current_price = self.current_prices.get(item_key)
                    trend = "➖"
                    history = list(self.price_history.get(item_key, []))
                    if len(history) > 1:
                        if history[-1] > history[-2]:
                            trend = "🟢↑"
                        elif history[-1] < history[-2]:
                            trend = "🔴↓"
                    value = f"**{trend} {current_price}g**" if current_price else "*No data*"
                    embed.add_field(name=f"__{item['name']}__", value=value, inline=True)
                while len(row) < 3:
                    embed.add_field(name="\u200b", value="\u200b", inline=True)
                    row.append(None)
            embed.add_field(name="Population", value=population_str, inline=False)
            embed.set_footer(text=f"Next update: {(datetime.now() + timedelta(minutes=1)).strftime('%H:%M')}")
            if self.price_message:
                try:
                    await self.price_message.edit(embed=embed)
                except discord.NotFound:
                    self.price_message = await channel.send(embed=embed)
            else:
                self.price_message = await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in price tracker: {e}")

    @update_price_tracker.before_loop
    async def before_update_prices(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(LiveMarketCog(bot))

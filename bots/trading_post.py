# bots/trading_post.py
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import aiohttp
from datetime import datetime
import logging
import re
import time
from typing import Optional, List
from collections import deque
from common.config import Config

logger = logging.getLogger('TradingPostBot')

class TradingPostCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        load_dotenv()
        self.config = Config()
        self.last_trade_time = None
        self.item_cache = {}
        self.active_messages = deque(maxlen=200)
        self.message_update_queue = deque(maxlen=50)

    async def get_item_data(self, item_id: str) -> Optional[dict]:
        if item_id in self.item_cache:
            return self.item_cache[item_id]
        try:
            async with aiohttp.ClientSession() as session:
                archetype = item_id.split('_')[0]
                url = f"{self.config.BASE_URL}/items?archetype={archetype}"
                async with session.get(url, headers=self.config.HEADERS) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data["status"] == "OK" and data["body"]:
                            for item in data["body"]:
                                self.item_cache[item["id"]] = item
                            return self.item_cache.get(item_id)
        except Exception as e:
            logger.error(f"Error fetching item data: {e}")
        return None

    @tasks.loop(seconds=5)
    async def monitor_trading_post(self):
        channel = self.bot.get_channel(self.config.TRADING_CHANNEL_ID)
        if not channel:
            logger.error("Trading channel not found!")
            return
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.config.BASE_URL}/trades/chat"
                params = {"limit": 100}
                async with session.get(url, headers=self.config.HEADERS, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data["status"] == "OK" and data["body"]:
                            await self.process_new_trades(data["body"], channel)
        except Exception as e:
            logger.error(f"Error monitoring trading post: {e}")

    @tasks.loop(seconds=1)
    async def process_message_queue(self):
        while self.message_update_queue:
            message, embed = self.message_update_queue.popleft()
            try:
                await message.edit(embed=embed)
            except Exception as e:
                logger.error(f"Error updating message: {e}")

    async def process_new_trades(self, trades: List[dict], channel: discord.TextChannel):
        for trade in reversed(trades):
            trade_time = datetime.fromisoformat(trade["timestamp"].replace('Z', '+00:00'))
            if self.last_trade_time is None or trade_time > self.last_trade_time:
                self.last_trade_time = trade_time
                await self.send_trade_message(trade, channel)

    async def send_trade_message(self, trade: dict, channel: discord.TextChannel):
        embed = discord.Embed(
            description=trade['message'],
            color=discord.Color.gold(),
            timestamp=datetime.fromisoformat(trade["timestamp"].replace('Z', '+00:00'))
        )
        if trade.get("sender"):
            embed.set_author(name=trade['sender'])
        extracted_items = re.findall(r'\[(.*?)\]', trade['message'])
        if extracted_items:
            item_header = " ".join([f"[{item}]" for item in extracted_items])
            content = f"{item_header}\n\n\n"
        else:
            content = "\n\n\n"
        view = await self.create_trade_view(trade, embed)
        try:
            message = await channel.send(content=content, embed=embed, view=view)
            self.active_messages.append(message)
            logger.info(f"New trade from {trade.get('sender', 'unknown')}")
        except discord.HTTPException as e:
            logger.error(f"Failed to send trade message: {e}")

    async def create_trade_view(self, trade: dict, embed: discord.Embed) -> Optional[View]:
        if not trade.get("items") or not trade.get("sender"):
            return None
        view = View(timeout=None)
        display_names = re.findall(r'\[(.*?)\]', trade['message'])
        items_with_stats = [
            item for item in trade["items"] 
            if any(k.startswith(('primary_', 'secondary_')) for k in item.keys())
        ]
        for index, item in enumerate(items_with_stats):
            row_index = index if index < 5 else 4
            display_name = display_names[index] if index < len(display_names) else item['item_id'].split('_')[0]
            view.add_item(ItemStatsButton(
                item_data=item,
                seller_name=trade['sender'],
                original_embed=embed,
                item_index=index,
                display_name=display_name,
                cog=self,
                row=row_index
            ))
        return view

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f'TradingPostCog ready as {self.bot.user}')
        self.monitor_trading_post.start()
        self.process_message_queue.start()

class ItemStatsButton(Button):
    def __init__(self, item_data: dict, seller_name: str, original_embed: discord.Embed, item_index: int, display_name: str, cog: TradingPostCog, row: int):
        unique_id = f"item_{int(time.time())}_{item_index}"
        super().__init__(label=display_name[:25], style=discord.ButtonStyle.grey, custom_id=unique_id, row=row)
        self.item_data = item_data
        self.seller_name = seller_name
        self.original_embed = original_embed
        self.display_name = display_name
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            item_info = await self.cog.get_item_data(self.item_data['item_id'])
            embed = await self.create_stats_embed(item_info)
            self.cog.message_update_queue.append((interaction.message, embed))
        except Exception as e:
            logger.error(f"Error showing item stats: {e}")
            await interaction.followup.send("Failed to show item stats", ephemeral=True)
            return
        await interaction.followup.send("\u200b", ephemeral=True)

    async def create_stats_embed(self, item_info: Optional[dict]) -> discord.Embed:
        embed = discord.Embed.from_dict(self.original_embed.to_dict())
        primary_stats = self.format_primary_stats()
        secondary_stats = await self.format_secondary_stats(item_info)
        rating = self.calculate_secondary_ranking(item_info)
        whisper_cmd = f"```/w {self.seller_name}```"
        embed.clear_fields()
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Item Rating", value=f"\n**{rating:.1f}/10**\n", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name=f"{self.display_name} Stats", value=f"{primary_stats}\n{secondary_stats}\n\n{whisper_cmd}", inline=False)
        return embed

    def calculate_secondary_ranking(self, item_info: Optional[dict]) -> float:
        scores = []
        for key, value in self.item_data.items():
            if key.startswith("secondary_"):
                stat_key = key[10:]
                if item_info:
                    min_val = item_info.get(f"secondary_min_{stat_key}")
                    max_val = item_info.get(f"secondary_max_{stat_key}")
                    if min_val is not None and max_val is not None:
                        try:
                            fmin = float(min_val)
                            fmax = float(max_val)
                            fcurrent = float(value)
                            if fmax > fmin:
                                normalized = (fcurrent - fmin) / (fmax - fmin) * 10
                                scores.append(normalized)
                        except Exception as e:
                            logger.error(f"Error calculating ranking for {key}: {e}")
        return sum(scores) / len(scores) if scores else 0.0

    def format_primary_stats(self) -> str:
        stats = []
        for key, value in self.item_data.items():
            if key.startswith("primary_"):
                stat_name = key.replace("primary_", "").replace("_", " ").title()
                stats.append(f"• **{stat_name}:** `{value}`")
        return "__Primary Attributes__\n" + "\n".join(stats) if stats else ""

    async def format_secondary_stats(self, item_info: Optional[dict]) -> str:
        stats = []
        for key, value in self.item_data.items():
            if key.startswith("secondary_"):
                stat_name = key.replace("secondary_", "").replace("_", " ").title()
                min_val = item_info.get(f"secondary_min_{key[10:]}") if item_info else None
                max_val = item_info.get(f"secondary_max_{key[10:]}") if item_info else None
                stat_line = f"• **{stat_name}:** `{value}`"
                if min_val is not None and max_val is not None:
                    try:
                        if float(min_val) != float(max_val):
                            stat_line += f" (`{min_val}-{max_val}`)"
                    except:
                        pass
                stats.append(stat_line)
        return "__Secondary Attributes__\n" + "\n".join(stats) if stats else ""

async def setup(bot: commands.Bot):
    await bot.add_cog(TradingPostCog(bot))

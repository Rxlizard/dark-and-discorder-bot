# bots/trade_history.py
import discord
from discord import app_commands, ui
from discord.ext import commands
import aiohttp
import logging
from datetime import datetime
import pytz
from urllib.parse import urlparse, parse_qs
from common.config import Config
from common.constants import RARITY_EMOJIS, RARITY_COLORS

logger = logging.getLogger('DarkAndDarkerDB.TradeHistory')

async def fetch_trade_history(session, username, config, limit=50, cursor=None):
    params = {k: v for k, v in {
        "seller": username,
        "limit": limit,
        "cursor": cursor,
        "condense": "true"
    }.items() if v is not None}
    logger.info(f"Fetching trades with params: {params}")
    async with session.get(f"{config.BASE_URL}/market", params=params, headers=config.HEADERS) as response:
        if response.status != 200:
            raise Exception(f"API returned status code {response.status}")
        data = await response.json()
        logger.info(f"API response status: {data['status']}")
        if data["status"] == "OK":
            return data["body"], data["pagination"]
        else:
            raise Exception(f"API Error: {data['status']}")

async def get_all_trades(session, username, config):
    all_trades = []
    cursor = None
    while True:
        try:
            trades, pagination = await fetch_trade_history(session, username, config, cursor=cursor)
            logger.debug(f"Current cursor: {cursor}")
        except Exception as e:
            logger.error(f"Error during fetch: {e}")
            break
        if not trades:
            logger.info("No more trades, exiting loop.")
            break
        all_trades.extend(trades)
        logger.info(f"Fetched {len(trades)} trades, total so far: {len(all_trades)}")
        next_url = pagination.get("next")
        if not next_url:
            logger.info("No next page, exiting loop.")
            break
        parsed_url = urlparse(next_url)
        query_params = parse_qs(parsed_url.query)
        cursor = query_params.get("cursor", [None])[0]
        if not cursor:
            logger.info("No cursor found, exiting loop.")
            break
    return all_trades

def create_trade_embeds(trades, username, current_page, total_pages):
    embeds = []
    for trade in trades:
        item_name = trade.get('item', 'Unknown Item')
        item_id = trade.get('item_id', '')
        price = trade.get('price', 0)
        quantity = trade.get('quantity', 1)
        rarity = trade.get('rarity', 'Common')
        expires_at = trade.get('expires_at', '')
        try:
            dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            est = pytz.timezone('US/Eastern')
            dt_est = dt.astimezone(est)
            expires_str = dt_est.strftime("%Y-%m-%d %H:%M:%S EDT")
        except Exception:
            expires_str = expires_at
        rarity_emoji = RARITY_EMOJIS.get(rarity, "⬜")
        embed_color = RARITY_COLORS.get(rarity, 0x0000FF)
        price_display = str(price)
        if quantity > 1:
            price_per = round(price / quantity, 2)
            price_display = f"{price} (Per: {price_per})"
        embed = discord.Embed(color=embed_color)
        embed.set_author(name=f"Trade History for {username} - Page {current_page}/{total_pages}")
        embed.set_thumbnail(url=f"{Config.BASE_URL}/items/{item_id}/icon")
        embed.description = (
            f"**Item:** {item_name}\n"
            f"**Price:** {price_display}\n"
            f"**Quantity:** {quantity}\n"
            f"**Rarity:** {rarity_emoji} {rarity}\n"
            f"**Expires:** {expires_str}"
        )
        embeds.append(embed)
    return embeds

class MultiEmbedView(ui.View):
    def __init__(self, all_trades, username, page_size=10):
        super().__init__(timeout=300)
        self.all_trades = all_trades
        self.username = username
        self.page_size = page_size
        self.current_page = 0
        self.total_pages = ((len(all_trades) - 1) // page_size) + 1

    async def show_page(self, interaction: discord.Interaction):
        start = self.current_page * self.page_size
        end = start + self.page_size
        page_trades = self.all_trades[start:end]
        embeds = create_trade_embeds(page_trades, self.username, self.current_page + 1, self.total_pages)
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page >= self.total_pages - 1)
        if interaction.response.is_done():
            await interaction.edit_original_response(embeds=embeds, view=self)
        else:
            await interaction.response.edit_message(embeds=embeds, view=self)

    @ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_page(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page -= 1
        await self.show_page(interaction)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page += 1
        await self.show_page(interaction)

class TradeHistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config()

    @app_commands.command(name="tradehistory", description="Fetch trade history for a user")
    async def tradehistory(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()
        logger.info(f"Processing /tradehistory for username: {username}")
        async with aiohttp.ClientSession() as session:
            try:
                trades = await get_all_trades(session, username, self.config)
                logger.info(f"Retrieved {len(trades)} trades for {username}")
            except Exception as e:
                logger.error(f"Error fetching trades: {e}")
                await interaction.followup.send(f"Failed to fetch trade history: {e}")
                return
        if not trades:
            await interaction.followup.send(f"No trade history found for {username}.")
            return
        try:
            view = MultiEmbedView(trades, username)
            await view.show_page(interaction)
        except Exception as e:
            logger.error(f"Error sending embeds: {e}")
            await interaction.followup.send(f"Failed to display trade history: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"TradeHistoryCog ready as {self.bot.user}")
        await self.bot.tree.sync()

async def setup(bot: commands.Bot):
    await bot.add_cog(TradeHistoryCog(bot))

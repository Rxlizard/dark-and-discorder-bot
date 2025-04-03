# DarkAndDarkerDB Discord Bot

A Discord bot that provides live market updates, price history charts, trade history lookups, and trading post monitoring for Dark and Darker. This bot connects to the DarkAndDarkerDB API to fetch market data and displays it on Discord channels.

## Features

- **Live Market Updates:** Continuously tracks and posts live price changes.
- **Price History:** Generates 2-week candle charts for selected items.
- **Trade History:** Retrieves and paginates trade history for a user.
- **Trading Post Monitoring:** Monitors trading post messages and shows item stats.

Commands
/find <itemname>
/tradehistory <username>

I didnt support rolls that well for the /find I use it mostly for craftable's TB, Gems ect...

## Installation

1. **Install Dependencies:**

pip install discord.py aiohttp numpy matplotlib python-dotenv requests pytz

.ENV

https://discord.com/developers
make a bot and use its token below

DISCORD_TOKEN=your_discord_bot_token_here
DARKERDB_API_KEY=your_darkerdb_api_key_here
# Channel IDs (Right-click a channel in Discord > Copy ID)
PRICE_CHANNEL_ID=your_price_channel_id
TRADE_HISTORY_CHANNEL_ID=your_trade_history_channel_id
TRADING_CHANNEL_ID=your_trading_channel_id
MARKET_HISTORY_ID=your_market_history_channel_id

python main.py

done
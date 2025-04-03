import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TOKEN = os.getenv('DISCORD_TOKEN')
    DARKERDB_API_KEY = os.getenv('DARKERDB_API_KEY')
    
    PRICE_CHANNEL_ID = int(os.getenv('PRICE_CHANNEL_ID', 0))
    TRADE_HISTORY_CHANNEL_ID = int(os.getenv('TRADE_HISTORY_CHANNEL_ID', 0))
    TRADING_CHANNEL_ID = int(os.getenv('TRADING_CHANNEL_ID', 0))
    
    BASE_URL = "https://api.darkerdb.com/v1"
    
    @property
    def HEADERS(self):
        return {
            "User-Agent": "DarkAndDarkerDB/1.0",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.DARKERDB_API_KEY}"
        }
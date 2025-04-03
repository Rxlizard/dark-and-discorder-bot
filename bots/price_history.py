# bots/price_history.py
import os
import json
import asyncio
import requests
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from datetime import datetime, timedelta
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Select, Button, Modal, TextInput
from dotenv import load_dotenv

class PriceHistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        load_dotenv()
        self.DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
        self.DARKERDB_API_KEY = os.getenv("DARKERDB_API_KEY")
        self.MARKET_HISTORY_ID = os.getenv("MARKET_HISTORY_ID")
        with open("item_ids.json", "r") as f:
            self.ITEM_IDS = json.load(f)
        self.RARITY_MAPPING = {
            "1001": "Poor",
            "2001": "Common",
            "3001": "Uncommon",
            "4001": "Rare",
            "5001": "Epic",
            "6001": "Legendary",
            "7001": "Unique"
        }
        self.RARITY_MAPPING_REV = {v: k for k, v in self.RARITY_MAPPING.items()}
        try:
            attr_resp = requests.get("https://api.darkerdb.com/v1/items/attributes")
            attr_resp.raise_for_status()
            self.ATTRIBUTES = {a["id"]: a for a in attr_resp.json()["body"]}
        except Exception:
            self.ATTRIBUTES = {}
        self.strictness_multiplier = 0.7

    async def async_requests_get(self, url, **kwargs):
        return await asyncio.to_thread(requests.get, url, **kwargs)

    def compute_thresholds(self, values, multiplier=1.5, lower_percentile=25, upper_percentile=75):
        q1 = np.percentile(values, lower_percentile)
        q3 = np.percentile(values, upper_percentile)
        iqr = q3 - q1
        lower_bound = q1 - (multiplier * iqr)
        upper_bound = q3 + (multiplier * iqr)
        return lower_bound, upper_bound

    def filter_outliers_iqr(self, data):
        if not data:
            return []
        max_values = [d["max"] for d in data]
        min_values = [d["min"] for d in data]
        min_bound_max, max_bound_max = self.compute_thresholds(
            max_values, multiplier=self.strictness_multiplier, lower_percentile=35, upper_percentile=75)
        min_bound_min, max_bound_min = self.compute_thresholds(
            min_values, multiplier=self.strictness_multiplier, lower_percentile=35, upper_percentile=75)
        iqr_filtered = [d for d in data if d["max"] <= max_bound_max and d["min"] >= min_bound_min]
        final_filtered = [d for d in iqr_filtered if d["avg"] != 0 and d["max"] <= 3 * d["avg"]]
        return final_filtered

    def generate_chart(self, market_data, item_name=None):
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(30, 16), dpi=100)
        bar_width = 0.5
        candles = []
        for i, d in enumerate(market_data):
            open_val = d["avg"] if i == 0 else market_data[i-1]["avg"]
            close_val = d["avg"]
            candles.append({
                "timestamp": d["timestamp"],
                "open": open_val,
                "high": d["max"],
                "low": d["min"],
                "close": close_val,
                "volume": d["volume"]
            })
        for i, candle in enumerate(candles):
            o, c, h, l = candle["open"], candle["close"], candle["high"], candle["low"]
            color = 'green' if c >= o else 'red'
            body_bottom = min(o, c)
            body_top = max(o, c)
            body_height = abs(o - c)
            ax.bar(i, body_height, bar_width, bottom=body_bottom, color=color)
        
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, linestyle=':', color='grey')
        
        day_ticks = []
        day_labels = []
        current_date = None
        for i, candle in enumerate(candles):
            dt = datetime.strptime(candle["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
            if current_date is None or dt.date() != current_date:
                current_date = dt.date()
                day_ticks.append(i)
                day_labels.append(dt.strftime('%m/%d %a'))
        
        for tick in day_ticks:
            ax.axvline(x=tick, color='grey', linestyle='--', alpha=0.3)
        
        ax.set_xticks(day_ticks)
        ax.set_xticklabels(day_labels, rotation=45, fontsize=16)
        ax.set_xlabel("Date", fontsize=20)
        ax.set_ylabel("Price", fontsize=20)
        
        if item_name:
            ax.set_title(f"{item_name} 2 Week Candle Chart", fontsize=24)
        else:
            ax.set_title("2 Week Candle Chart", fontsize=24)
        
        legend_elements = [
            Patch(facecolor='green', label='Price Increase (Close ≥ Open)'),
            Patch(facecolor='red', label='Price Decrease (Close < Open)')
        ]
        ax.legend(handles=legend_elements, fontsize=16)
        
        if market_data:
            global_min = min(d["min"] for d in market_data)
            global_max = max(d["max"] for d in market_data)
            buffer = (global_max - global_min) * 0.1
            ax.set_ylim(global_min - buffer, global_max + buffer)
        
        ax.text(0.01, 0.99, "Powered by darkerdb.com", transform=ax.transAxes,
                fontsize=10, color='grey', verticalalignment='top')
        
        plt.tight_layout()
        image_path = "chart.png"
        plt.savefig(image_path)
        plt.close(fig)
        return image_path

    ## ––– Inner UI Classes ––– ##
    from discord.ui import Select, View, Button, Modal, TextInput

    class BaseItemSelect(Select):
        def __init__(self, base_items, cog):
            self.cog = cog
            options = [discord.SelectOption(label=item) for item in base_items]
            super().__init__(placeholder="Select an item", min_values=1, max_values=1, options=options)
        
        async def callback(self, interaction: discord.Interaction):
            self.view.selected_base = self.values[0]
            available = [item for item in self.cog.ITEM_IDS if item.startswith(self.values[0] + "_")]
            self.view.available_full_ids = available
            self.view.clear_items()
            if available and len(available) > 1:
                rarity_options = []
                for full in available:
                    suffix = full.split("_")[-1]
                    rarity_name = self.cog.RARITY_MAPPING.get(suffix)
                    if rarity_name and rarity_name not in rarity_options:
                        rarity_options.append(rarity_name)
                if rarity_options:
                    opts = [discord.SelectOption(label=r) for r in rarity_options]
                    self.view.add_item(self.cog.RaritySelect(opts, self.cog))
                    await interaction.response.edit_message(
                        content=f"You selected: **{self.values[0]}**. Now choose a rarity.",
                        view=self.view
                    )
                    return
            self.view.selected_full = available[0] if available else self.values[0]
            item_details = await self.view.fetch_item_details(self.view.selected_full)
            self.view.item_details = item_details
            rarity = item_details.get("rarity", "").lower()
            num_secondary = int(item_details.get("num_secondary_attributes", 0))
            if num_secondary <= 0 or rarity in ["poor", "common"]:
                mod_view = self.cog.ModifierDecisionView(self.cog)
                mod_view.item_details = item_details
                mod_view.selected_full = self.view.selected_full
                await mod_view.finalize(interaction)
            else:
                mod_view = self.cog.ModifierDecisionView(self.cog)
                mod_view.item_details = item_details
                mod_view.selected_full = self.view.selected_full
                await interaction.response.edit_message(
                    content=f"Item details for **{item_details.get('name', self.view.selected_full)}** fetched. Do you want to apply a secondary attribute filter?",
                    view=mod_view
                )

    class RaritySelect(Select):
        def __init__(self, options, cog):
            self.cog = cog
            super().__init__(placeholder="Select rarity", min_values=1, max_values=1, options=options)
        
        async def callback(self, interaction: discord.Interaction):
            rarity_choice = self.values[0]
            for full in self.view.available_full_ids:
                if full.endswith(self.cog.RARITY_MAPPING_REV[rarity_choice]):
                    self.view.selected_full = full
                    break
            self.view.clear_items()
            item_details = await self.view.fetch_item_details(self.view.selected_full)
            self.view.item_details = item_details
            rarity = item_details.get("rarity", "").lower()
            num_secondary = int(item_details.get("num_secondary_attributes", 0))
            if num_secondary <= 0 or rarity in ["poor", "common"]:
                mod_view = self.cog.ModifierDecisionView(self.cog)
                mod_view.item_details = item_details
                mod_view.selected_full = self.view.selected_full
                await mod_view.finalize(interaction)
            else:
                mod_view = self.cog.ModifierDecisionView(self.cog)
                mod_view.item_details = item_details
                mod_view.selected_full = self.view.selected_full
                await interaction.response.edit_message(
                    content=f"Item details for **{item_details.get('name', self.view.selected_full)}** fetched. Do you want to apply a secondary attribute filter?",
                    view=mod_view
                )

    class ModifierDecisionView(View):
        def __init__(self, cog):
            super().__init__(timeout=60)
            self.cog = cog
            self.item_details = None
            self.selected_full = None
            self.selected_modifier_value = None
            self.selected_secondary = None

        @discord.ui.button(label="No Modifier Filter", style=discord.ButtonStyle.secondary)
        async def no_modifier(self, interaction: discord.Interaction, button: Button):
            await self.finalize(interaction)

        @discord.ui.button(label="Apply Modifier Filter", style=discord.ButtonStyle.primary)
        async def apply_modifier(self, interaction: discord.Interaction, button: Button):
            self.clear_items()
            sec_attribs = []
            for key in self.item_details:
                if key.startswith("secondary_min_"):
                    attrib = key.replace("secondary_min_", "")
                    sec_attribs.append(attrib)
            sec_attribs = sorted(list(set(sec_attribs)))
            if sec_attribs:
                opts = []
                for attrib in sec_attribs:
                    display = self.cog.ATTRIBUTES.get(attrib.capitalize(), {}).get("display")
                    if not display:
                        display = attrib.replace("_", " ").title()
                    opts.append(discord.SelectOption(label=display, value=attrib))
                self.add_item(self.cog.SecondaryAttributeSelect(opts, self.cog))
                await interaction.response.edit_message(content="Select a secondary attribute to filter by:", view=self)
            else:
                await interaction.response.send_message("No secondary attributes available for this item.", ephemeral=True)
                await self.finalize(interaction)

        async def finalize(self, interaction: discord.Interaction):
            now = datetime.now()
            base_url = f"https://api.darkerdb.com/v1/market/analytics/{self.selected_full}/prices/history"
            t1_from = (now - timedelta(days=4)).isoformat() + "Z"   # Interval 1: [now-4, now)
            t2_from = (now - timedelta(days=8)).isoformat() + "Z"   # Interval 2: [now-8, now-4)
            t3_from = (now - timedelta(days=12)).isoformat() + "Z"  # Interval 3: [now-12, now-8)
            t4_from = (now - timedelta(days=16)).isoformat() + "Z"  # Interval 4: [now-16, now-12)
            if self.selected_modifier_value is not None and self.selected_secondary is not None:
                modifier_field = self.selected_secondary
                modifier_value = self.selected_modifier_value
                params1 = {"interval": "30m", "from": t1_from, f"secondary[{modifier_field}]": modifier_value}
                params2 = {"interval": "30m", "from": t2_from, "to": t1_from, f"secondary[{modifier_field}]": modifier_value}
                params3 = {"interval": "30m", "from": t3_from, "to": t2_from, f"secondary[{modifier_field}]": modifier_value}
                params4 = {"interval": "30m", "from": t4_from, "to": t3_from, f"secondary[{modifier_field}]": modifier_value}
                try:
                    market_resp1 = await self.cog.async_requests_get(base_url, params=params1)
                    market_resp1.raise_for_status()
                    data1 = market_resp1.json().get("body") or []
                    market_resp2 = await self.cog.async_requests_get(base_url, params=params2)
                    market_resp2.raise_for_status()
                    data2 = market_resp2.json().get("body") or []
                    market_resp3 = await self.cog.async_requests_get(base_url, params=params3)
                    market_resp3.raise_for_status()
                    data3 = market_resp3.json().get("body") or []
                    market_resp4 = await self.cog.async_requests_get(base_url, params=params4)
                    market_resp4.raise_for_status()
                    data4 = market_resp4.json().get("body") or []
                    market_data = data4 + data3 + data2 + data1
                    market_data.sort(key=lambda x: x["timestamp"])
                    if not market_data:
                        await interaction.followup.send("No market history data available for this item with the modifier.", ephemeral=False)
                        self.stop()
                        return
                except Exception:
                    await interaction.followup.send("Error fetching market history data.", ephemeral=False)
                    self.stop()
                    return
                item_name = self.item_details.get("name")
                rarity = self.item_details.get("rarity")
                filtered_data = self.cog.filter_outliers_iqr(market_data)
                chart_path = self.cog.generate_chart(filtered_data, item_name=item_name)
                details_msg = (
                    f"**Item:** {item_name}\n"
                    f"**Rarity:** {rarity}\n"
                    f"**Modifier:** {self.selected_secondary.capitalize()} = {modifier_value}\n"
                )
                channel = interaction.client.get_channel(int(self.cog.MARKET_HISTORY_ID))
                if channel:
                    await channel.send(content=details_msg, file=discord.File(chart_path))
                else:
                    await interaction.followup.send("Market history channel not found!", ephemeral=False)
            else:
                params1 = {"interval": "30m", "from": t1_from}
                params2 = {"interval": "30m", "from": t2_from, "to": t1_from}
                params3 = {"interval": "30m", "from": t3_from, "to": t2_from}
                params4 = {"interval": "30m", "from": t4_from, "to": t3_from}
                try:
                    market_resp1 = await self.cog.async_requests_get(base_url, params=params1)
                    market_resp1.raise_for_status()
                    data1 = market_resp1.json().get("body") or []
                    market_resp2 = await self.cog.async_requests_get(base_url, params=params2)
                    market_resp2.raise_for_status()
                    data2 = market_resp2.json().get("body") or []
                    market_resp3 = await self.cog.async_requests_get(base_url, params=params3)
                    market_resp3.raise_for_status()
                    data3 = market_resp3.json().get("body") or []
                    market_resp4 = await self.cog.async_requests_get(base_url, params=params4)
                    market_resp4.raise_for_status()
                    data4 = market_resp4.json().get("body") or []
                    market_data = data4 + data3 + data2 + data1
                    market_data.sort(key=lambda x: x["timestamp"])
                    if not market_data:
                        await interaction.followup.send("No market history data available for this item.", ephemeral=False)
                        self.stop()
                        return
                except Exception:
                    await interaction.followup.send("Error fetching market history data.", ephemeral=False)
                    self.stop()
                    return
                filtered_data = self.cog.filter_outliers_iqr(market_data)
                item_name = self.item_details.get("name")
                chart_path = self.cog.generate_chart(filtered_data, item_name=item_name)
                details_msg = (
                    f"**Item:** {item_name}\n"
                    f"**Rarity:** {self.item_details.get('rarity')}\n"
                )
                channel = interaction.client.get_channel(int(self.cog.MARKET_HISTORY_ID))
                if channel:
                    await channel.send(content=details_msg, file=discord.File(chart_path))
                else:
                    await interaction.followup.send("Market history channel not found!", ephemeral=False)
            self.stop()

    class SecondaryAttributeSelect(Select):
        def __init__(self, options, cog):
            self.cog = cog
            super().__init__(placeholder="Select secondary attribute", min_values=1, max_values=1, options=options)
        
        async def callback(self, interaction: discord.Interaction):
            self.view.selected_secondary = self.values[0]
            self.view.clear_items()
            min_key = f"secondary_min_{self.values[0]}"
            max_key = f"secondary_max_{self.values[0]}"
            min_val = self.view.item_details.get(min_key)
            max_val = self.view.item_details.get(max_key)
            modal = self.cog.ModifierValueModal(min_val, max_val, self.values[0], self.cog, self.view)
            await interaction.response.send_modal(modal)

    class ModifierValueModal(Modal):
        def __init__(self, min_val, max_val, attribute, cog, parent_view: View):
            super().__init__(title=f"Set value for {attribute.capitalize()}")
            self.min_val = min_val
            self.max_val = max_val
            self.attribute = attribute
            self.cog = cog
            self.parent_view = parent_view
            step = 0.1 if cog.ATTRIBUTES.get(attribute.capitalize(), {}).get("is_percentage") else 1
            placeholder = f"Enter a value between {min_val} and {max_val} (step {step})"
            self.value_input = TextInput(label="Roll Value", placeholder=placeholder)
            self.add_item(self.value_input)

        async def on_submit(self, interaction: discord.Interaction):
            try:
                val = float(self.value_input.value)
            except ValueError:
                await interaction.followup.send("Invalid number entered.", ephemeral=False)
                return
            if not (self.min_val <= val <= self.max_val):
                await interaction.followup.send(f"Value must be between {self.min_val} and {self.max_val}.", ephemeral=False)
                return
            self.parent_view.selected_modifier_value = val
            await self.parent_view.finalize(interaction)

    class FindView(View):
        def __init__(self, base_items, cog):
            super().__init__(timeout=120)
            self.cog = cog
            self.selected_base = None
            self.available_full_ids = None
            self.selected_full = None
            self.item_details = None
            self.selected_secondary = None
            self.selected_modifier_value = None
            self.add_item(cog.BaseItemSelect(base_items, cog))
        
        async def fetch_item_details(self, full_id: str):
            url = f"https://api.darkerdb.com/v1/items/{full_id}?condense=true"
            try:
                resp = await self.cog.async_requests_get(url)
                resp.raise_for_status()
                return resp.json()["body"]
            except Exception:
                return {}

    @app_commands.command(name="find", description="Find market history and modifiers for an item.")
    @app_commands.describe(itemname="The item name to search for (e.g., Sapphire)")
    async def find(self, interaction: discord.Interaction, itemname: str):
        search_term = itemname.lower()
        matches = {}
        for full in self.ITEM_IDS:
            base = full.split("_")[0] if "_" in full else full
            if search_term in base.lower():
                matches[base] = True
        if not matches:
            await interaction.response.send_message("No matching items found.", ephemeral=True)
            return
        base_items = list(matches.keys())
        view = self.FindView(base_items, self)
        await interaction.response.send_message("Select an item from the list below:", view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.tree.sync()
        print(f"PriceHistoryCog connected as {self.bot.user}")

async def setup(bot: commands.Bot):
    await bot.add_cog(PriceHistoryCog(bot))

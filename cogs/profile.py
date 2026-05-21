"""
Profile commands for quiz statistics and cosmetic shop.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from utils.database import (
    get_profile,
    spend_coins,
    add_inventory_item,
    has_inventory_item,
    list_inventory_items,
    set_profile_banner,
    set_profile_partner,
)
from utils.profile_shop import load_shop_items, get_shop_item


class ProfileCog(commands.Cog):
    """Profile and shop commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Show a player's quiz profile")
    @app_commands.describe(user="User to view (optional)")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        target = user or interaction.user
        profile = await get_profile(str(target.id))
        items = load_shop_items()

        banner_item = items.get(profile.get("banner_id")) if profile.get("banner_id") else None
        partner_item = items.get(profile.get("partner_id")) if profile.get("partner_id") else None

        display_name = target.display_name if isinstance(target, discord.Member) else target.name
        embed = discord.Embed(
            title=f"{display_name}'s Profile",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Correct Guesses", value=str(profile.get("total_correct", 0)), inline=True)
        embed.add_field(name="Games Played", value=str(profile.get("total_games", 0)), inline=True)
        embed.add_field(name="Maimiles", value=str(profile.get("coins_balance", 0)), inline=True)
        embed.add_field(name="Lifetime Maimiles", value=str(profile.get("coins_lifetime", 0)), inline=True)

        banner_name = banner_item.get("name") if banner_item else "None"
        partner_name = partner_item.get("name") if partner_item else "None"
        embed.add_field(name="Banner", value=banner_name, inline=True)
        embed.add_field(name="Partner", value=partner_name, inline=True)

        if banner_item and banner_item.get("image_url"):
            embed.set_image(url=banner_item["image_url"])
        if partner_item and partner_item.get("image_url"):
            embed.set_thumbnail(url=partner_item["image_url"])

        await interaction.response.send_message(embed=embed)

    shop_group = app_commands.Group(
        name="shop",
        description="Buy and equip profile cosmetics"
    )

    @shop_group.command(name="list", description="List available shop items")
    @app_commands.describe(item_type="Filter by item type")
    @app_commands.choices(item_type=[
        app_commands.Choice(name="Banners", value="banner"),
        app_commands.Choice(name="Partners", value="partner"),
    ])
    async def shop_list(self, interaction: discord.Interaction, item_type: Optional[str] = None):
        items = load_shop_items()
        lines = []

        for item_id, item in sorted(items.items()):
            if item_type and item.get("type") != item_type:
                continue
            price = item.get("price", 0)
            item_name = item.get("name", item_id)
            item_desc = item.get("description")
            price_text = f"{price} maimiles"
            if item_desc:
                lines.append(f"`{item_id}` - {item_name} ({price_text})\n{item_desc}")
            else:
                lines.append(f"`{item_id}` - {item_name} ({price_text})")

        if not lines:
            await interaction.response.send_message("No items found for that filter.", ephemeral=True)
            return

        description = "\n\n".join(lines)
        embed = discord.Embed(
            title="Profile Shop",
            description=description,
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @shop_group.command(name="buy", description="Buy a shop item")
    @app_commands.describe(item_id="Item id to buy")
    async def shop_buy(self, interaction: discord.Interaction, item_id: str):
        item = get_shop_item(item_id)
        if not item:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        if await has_inventory_item(user_id, item_id):
            await interaction.response.send_message("You already own that item.", ephemeral=True)
            return

        price = int(item.get("price", 0))
        if price > 0:
            can_spend = await spend_coins(user_id, price)
            if not can_spend:
                await interaction.response.send_message("Not enough maimiles.", ephemeral=True)
                return

        await add_inventory_item(user_id, item_id, item.get("type", "unknown"))
        await interaction.response.send_message(
            f"Purchased {item.get('name', item_id)} for {price} maimiles.",
            ephemeral=True,
        )

    @shop_group.command(name="equip", description="Equip a banner or partner")
    @app_commands.describe(item_id="Item id to equip")
    async def shop_equip(self, interaction: discord.Interaction, item_id: str):
        item = get_shop_item(item_id)
        if not item:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        owned = await has_inventory_item(user_id, item_id)
        if not owned:
            price = int(item.get("price", 0))
            if price == 0:
                await add_inventory_item(user_id, item_id, item.get("type", "unknown"))
            else:
                await interaction.response.send_message(
                    "You do not own that item. Buy it first.",
                    ephemeral=True,
                )
                return

        item_type = item.get("type")
        if item_type == "banner":
            await set_profile_banner(user_id, item_id)
            await interaction.response.send_message("Banner equipped.", ephemeral=True)
            return
        if item_type == "partner":
            await set_profile_partner(user_id, item_id)
            await interaction.response.send_message("Partner equipped.", ephemeral=True)
            return

        await interaction.response.send_message("That item cannot be equipped.", ephemeral=True)

    @shop_group.command(name="inventory", description="List your owned items")
    @app_commands.describe(item_type="Filter by item type")
    @app_commands.choices(item_type=[
        app_commands.Choice(name="Banners", value="banner"),
        app_commands.Choice(name="Partners", value="partner"),
    ])
    async def shop_inventory(self, interaction: discord.Interaction, item_type: Optional[str] = None):
        user_id = str(interaction.user.id)
        items = load_shop_items()
        owned_ids = await list_inventory_items(user_id, item_type=item_type)

        if not owned_ids:
            await interaction.response.send_message("You do not own any items yet.", ephemeral=True)
            return

        lines = []
        for item_id in owned_ids:
            item = items.get(item_id)
            item_name = item.get("name", item_id) if item else item_id
            item_kind = item.get("type", "unknown") if item else "unknown"
            lines.append(f"`{item_id}` - {item_name} ({item_kind})")

        embed = discord.Embed(
            title="Your Inventory",
            description="\n".join(lines),
            color=discord.Color.teal()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))

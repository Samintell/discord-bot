"""
Profile commands for quiz statistics and cosmetic shop.
"""

import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Optional
from pathlib import Path

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


PROJECT_ROOT = Path(__file__).parent.parent


def _resolve_item_path(item: dict) -> Optional[Path]:
    image_path = item.get("image_path")
    if not image_path:
        return None

    path = Path(image_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path if path.exists() else None


def _build_item_attachment(item: dict, prefix: str) -> tuple[Optional[discord.File], Optional[str]]:
    path = _resolve_item_path(item)
    if not path:
        return None, None

    filename = f"{prefix}_{path.name}"
    return discord.File(path, filename=filename), f"attachment://{filename}"


class ShopItemsView(ui.View):
    """Paginated view for shop items with images."""

    def __init__(self, items: list[tuple[str, dict]], user_id: int, title: str, color: discord.Color):
        super().__init__(timeout=120)
        self.items = items
        self.user_id = user_id
        self.title = title
        self.color = color
        self.index = 0
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        at_start = self.index <= 0
        at_end = self.index >= len(self.items) - 1
        self.prev_ten.disabled = at_start
        self.prev_page.disabled = at_start
        self.next_page.disabled = at_end
        self.next_ten.disabled = at_end

    def _build_embed(self) -> tuple[discord.Embed, Optional[discord.File]]:
        item_id, item = self.items[self.index]
        item_name = item.get("name", item_id)
        item_desc = item.get("description") or "No description."
        item_type = item.get("type", "unknown")
        price = int(item.get("price", 0))

        embed = discord.Embed(
            title=item_name,
            description=item_desc,
            color=self.color
        )
        embed.add_field(name="Item ID", value=item_id, inline=True)
        embed.add_field(name="Type", value=item_type, inline=True)
        embed.add_field(name="Price", value=f"{price} maimiles", inline=True)

        if len(self.items) > 1:
            embed.set_footer(text=f"Page {self.index + 1}/{len(self.items)}")

        attachment, attachment_url = _build_item_attachment(item, "shop")
        if attachment and attachment_url:
            if item_type == "banner":
                embed.set_image(url=attachment_url)
            else:
                embed.set_thumbnail(url=attachment_url)
            return embed, attachment

        image_url = item.get("image_url")
        if image_url:
            if item_type == "banner":
                embed.set_image(url=image_url)
            else:
                embed.set_thumbnail(url=image_url)

        return embed, None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the user who opened the shop can use these buttons.",
                ephemeral=True,
            )
            return False
        return True

    async def _update_message(self, interaction: discord.Interaction) -> None:
        self._sync_buttons()
        embed, attachment = self._build_embed()
        if attachment:
            await interaction.response.edit_message(embed=embed, attachments=[attachment], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)

    @ui.button(label="Prev 10", style=discord.ButtonStyle.secondary)
    async def prev_ten(self, interaction: discord.Interaction, button: ui.Button):
        if self.index > 0:
            self.index = max(0, self.index - 10)
        await self._update_message(interaction)

    @ui.button(label="Prev", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.index > 0:
            self.index -= 1
        await self._update_message(interaction)

    @ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.index < len(self.items) - 1:
            self.index += 1
        await self._update_message(interaction)

    @ui.button(label="Next 10", style=discord.ButtonStyle.secondary)
    async def next_ten(self, interaction: discord.Interaction, button: ui.Button):
        if self.index < len(self.items) - 1:
            self.index = min(len(self.items) - 1, self.index + 10)
        await self._update_message(interaction)


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
        embeds = []
        files: list[discord.File] = []

        if banner_item and (banner_item.get("image_url") or banner_item.get("image_path")):
            banner_embed = discord.Embed(color=discord.Color.blurple())
            banner_file, banner_url = _build_item_attachment(banner_item, "banner")
            if banner_file and banner_url:
                files.append(banner_file)
                banner_embed.set_image(url=banner_url)
            else:
                banner_embed.set_image(url=banner_item["image_url"])
            embeds.append(banner_embed)

        embed = discord.Embed(
            title=f"{display_name}'s Profile",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Correct Guesses", value=str(profile.get("total_correct", 0)), inline=True)
        embed.add_field(name="Games Played", value=str(profile.get("total_games", 0)), inline=True)
        embed.add_field(name="Lifetime Maimiles", value=str(profile.get("coins_lifetime", 0)), inline=True)

        if partner_item and (partner_item.get("image_url") or partner_item.get("image_path")):
            partner_file, partner_url = _build_item_attachment(partner_item, "partner")
            if partner_file and partner_url:
                files.append(partner_file)
                embed.set_thumbnail(url=partner_url)
            else:
                embed.set_thumbnail(url=partner_item["image_url"])

        embeds.append(embed)
        if files:
            await interaction.response.send_message(embeds=embeds, files=files)
        else:
            await interaction.response.send_message(embeds=embeds)

    shop_group = app_commands.Group(
        name="shop",
        description="Buy and equip profile cosmetics"
    )

    @app_commands.command(name="balance", description="Show your current maimiles balance")
    async def balance(self, interaction: discord.Interaction):
        profile = await get_profile(str(interaction.user.id))
        balance = profile.get("coins_balance", 0)

        embed = discord.Embed(
            title="Maimiles Balance",
            description=f"{interaction.user.mention} has **{balance}** maimiles.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @shop_group.command(name="list", description="List available shop items")
    @app_commands.describe(item_type="Filter by item type")
    @app_commands.choices(item_type=[
        app_commands.Choice(name="Banners", value="banner"),
        app_commands.Choice(name="Partners", value="partner"),
    ])
    async def shop_list(self, interaction: discord.Interaction, item_type: Optional[str] = None):
        items = load_shop_items()
        item_rows: list[tuple[str, dict]] = []
        owned_ids = set(await list_inventory_items(str(interaction.user.id), item_type=item_type))

        for item_id, item in sorted(items.items()):
            if item_type and item.get("type") != item_type:
                continue
            if item_id in owned_ids:
                continue
            item_rows.append((item_id, item))

        if not item_rows:
            await interaction.response.send_message("No unowned items found for that filter.", ephemeral=True)
            return

        view = ShopItemsView(
            items=item_rows,
            user_id=interaction.user.id,
            title="Profile Shop",
            color=discord.Color.green(),
        )
        embed, attachment = view._build_embed()
        if attachment:
            await interaction.response.send_message(
                embed=embed,
                file=attachment,
                view=view,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True,
            )

    @shop_group.command(name="view", description="View details for a shop item")
    @app_commands.describe(item_id="Item id to view")
    async def shop_view(self, interaction: discord.Interaction, item_id: str):
        item = get_shop_item(item_id)
        if not item:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return

        item_name = item.get("name", item_id)
        item_type = item.get("type", "unknown")
        item_desc = item.get("description") or "No description."
        price = int(item.get("price", 0))

        embed = discord.Embed(
            title=item_name,
            description=item_desc,
            color=discord.Color.teal()
        )
        embed.add_field(name="Item ID", value=item_id, inline=True)
        embed.add_field(name="Type", value=item_type, inline=True)
        embed.add_field(name="Price", value=f"{price} maimiles", inline=True)

        image_url = item.get("image_url")
        attachment, attachment_url = _build_item_attachment(item, "item")
        if attachment and attachment_url:
            if item_type == "banner":
                embed.set_image(url=attachment_url)
            else:
                embed.set_thumbnail(url=attachment_url)
            await interaction.response.send_message(embed=embed, file=attachment, ephemeral=True)
            return

        if image_url:
            if item_type == "banner":
                embed.set_image(url=image_url)
            else:
                embed.set_thumbnail(url=image_url)

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

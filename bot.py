import os
import json
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "panel_channel_id": None,
    "ticket_category_id": None,
    "vouch_channel_id": None,
    "staff_role_id": None
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG.copy())
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

config = load_config()

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
PINK = discord.Color.from_rgb(255, 143, 194)

def styled_embed(title, description):
    e = discord.Embed(title=f"୨୧・{title}", description=description, color=PINK)
    e.set_footer(text="Adopt Me House Shop • Thank you for supporting us ♡")
    return e

def staff_only(interaction):
    role_id = config.get("staff_role_id")
    if interaction.user.guild_permissions.administrator:
        return True
    if role_id:
        return any(r.id == role_id for r in getattr(interaction.user, "roles", []))
    return interaction.user.guild_permissions.manage_channels

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="house_shop_open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        category = interaction.guild.get_channel(config.get("ticket_category_id"))
        if not category:
            return await interaction.response.send_message("❌ Ticket category is not configured.", ephemeral=True)

        existing = discord.utils.get(interaction.guild.text_channels, topic=f"House shop ticket for {interaction.user.id}")
        if existing:
            return await interaction.response.send_message(f"❌ You already have {existing.mention}", ephemeral=True)

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        role = interaction.guild.get_role(config.get("staff_role_id"))
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)

        channel = await interaction.guild.create_text_channel(
            f"ticket-{interaction.user.name}".lower()[:90],
            category=category,
            overwrites=overwrites,
            topic=f"House shop ticket for {interaction.user.id}"
        )
        await channel.send(
            content=interaction.user.mention,
            embed=styled_embed(
                "Ticket Opened ♡",
                "Welcome! Please tell us which house/build you're interested in and include any details we need.\n\n"
                "A staff member will help you shortly."
            ),
            view=CloseTicketView()
        )
        await interaction.response.send_message(f"🎫 Ticket created: {channel.mention}", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="house_shop_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not staff_only(interaction):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        await interaction.response.send_message("🔒 Closing ticket...")
        await asyncio.sleep(3)
        await interaction.channel.delete(reason=f"Closed by {interaction.user}")

@bot.event
async def on_ready():
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user} | Synced {len(synced)} commands")
    except Exception as exc:
        print("Sync error:", exc)

@bot.tree.command(name="setup", description="Configure the ticket and vouch system.")
@app_commands.describe(
    panel_channel="Channel for the ticket panel",
    ticket_category="Category where tickets are created",
    vouch_channel="Channel where /vouch posts",
    staff_role="Optional role allowed to manage tickets and /say"
)
async def setup(interaction, panel_channel: discord.TextChannel,
                ticket_category: discord.CategoryChannel,
                vouch_channel: discord.TextChannel,
                staff_role: discord.Role | None = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)

    config.update({
        "panel_channel_id": panel_channel.id,
        "ticket_category_id": ticket_category.id,
        "vouch_channel_id": vouch_channel.id,
        "staff_role_id": staff_role.id if staff_role else None
    })
    save_config(config)

    embed = styled_embed(
        "Support Tickets ♡",
        "Need help with an order or house build?\n\n"
        "Click **🎫 Open Ticket** below to create a private ticket with staff."
    )
    await panel_channel.send(embed=embed, view=TicketView())

    await interaction.response.send_message(
        f"✅ Configured!\n🎫 Panel: {panel_channel.mention}\n"
        f"📁 Category: **{ticket_category.name}**\n"
        f"⭐ Vouches: {vouch_channel.mention}\n"
        f"👥 Staff: {staff_role.mention if staff_role else 'Manage Channels'}",
        ephemeral=True
    )

@bot.tree.command(name="ticketpanel", description="Send a ticket panel to a selected channel.")
@app_commands.describe(channel="Channel where the panel should be sent")
async def ticketpanel(interaction, channel: discord.TextChannel):
    if not staff_only(interaction):
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await channel.send(
        embed=styled_embed("Support Tickets ♡", "Need help? Click **🎫 Open Ticket** to create a private ticket."),
        view=TicketView()
    )
    await interaction.response.send_message(f"✅ Panel sent to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="vouch", description="Leave a vouch for the shop.")
@app_commands.describe(message="Your vouch/review message")
async def vouch(interaction, message: str):
    channel = interaction.guild.get_channel(config.get("vouch_channel_id"))
    if not channel:
        return await interaction.response.send_message("❌ Vouch channel is not configured. Use /setup.", ephemeral=True)

    embed = discord.Embed(title="୨୧・NEW CUSTOMER VOUCH", description=f"**{message}**", color=PINK)
    embed.set_author(name=f"{interaction.user.display_name} ♡", icon_url=interaction.user.display_avatar.url)
    embed.add_field(name="Customer", value=interaction.user.mention, inline=True)
    embed.add_field(name="Rating", value="★★★★★", inline=True)
    embed.set_footer(text="Adopt Me House Shop • Customer Vouch")
    await channel.send(embed=embed)
    await interaction.response.send_message("⭐ Your vouch has been posted!", ephemeral=True)

@bot.tree.command(name="say", description="Send a styled message through the bot.")
@app_commands.describe(channel="Channel to send it in", message="Message to send")
async def say(interaction, channel: discord.TextChannel, message: str):
    if not staff_only(interaction):
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await channel.send(embed=styled_embed("Announcement ♡", message))
    await interaction.response.send_message(f"✅ Sent to {channel.mention}.", ephemeral=True)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set.")

bot.run(TOKEN)

import os
import json
import asyncio
import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# CONFIG
# =========================================================

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

    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


config = load_config()


# =========================================================
# BOT SETUP
# =========================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# Pink theme
PINK = discord.Color.from_rgb(255, 143, 194)


# =========================================================
# EMBED HELPER
# =========================================================

def styled_embed(title, description):
    embed = discord.Embed(
        title=title,
        description=description,
        color=PINK
    )

    embed.set_footer(
        text="୨୧ ali's adm house • Customer Shop ♡"
    )

    return embed


# =========================================================
# STAFF CHECK
# =========================================================

def is_staff(interaction: discord.Interaction):

    # Server administrator
    if interaction.user.guild_permissions.administrator:
        return True

    staff_role_id = config.get("staff_role_id")

    # No staff role configured
    if not staff_role_id:
        return interaction.user.guild_permissions.manage_channels

    # Check staff role
    return any(
        role.id == staff_role_id
        for role in getattr(interaction.user, "roles", [])
    )


# =========================================================
# TICKET OPEN BUTTON
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)


    @discord.ui.button(
        label="Open Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="ali_adm_open_ticket"
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        if guild is None:
            return


        # Get ticket category
        category_id = config.get("ticket_category_id")

        category = (
            guild.get_channel(category_id)
            if category_id
            else None
        )


        if not category:
            return await interaction.response.send_message(
                "❌ The ticket category hasn't been configured yet.",
                ephemeral=True
            )


        # Check if user already has a ticket
        for channel in guild.text_channels:

            if channel.topic == f"ali_adm_ticket:{interaction.user.id}":

                return await interaction.response.send_message(
                    f"❌ You already have an open ticket: {channel.mention}",
                    ephemeral=True
                )


        # Staff role
        staff_role = None

        staff_role_id = config.get("staff_role_id")

        if staff_role_id:
            staff_role = guild.get_role(staff_role_id)


        # Permissions
        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )
        }


        # Staff permissions
        if staff_role:

            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                attach_files=True,
                embed_links=True
            )


        # Create ticket
        ticket_channel = await guild.create_text_channel(

            name=f"ticket-{interaction.user.name}".lower()[:90],

            category=category,

            overwrites=overwrites,

            topic=f"ali_adm_ticket:{interaction.user.id}"
        )


        # Ticket embed
        embed = discord.Embed(
            title="୨୧・𝒯𝒾𝒸𝓀𝑒𝓉 𝒪𝓅𝑒𝓃𝑒𝒹 ♡",
            description=(
                f"Welcome {interaction.user.mention}! ♡\n\n"

                "Please tell us what you need help with.\n"
                "If you're ordering a house, please include:\n\n"

                "୨୧ **House:**\n"
                "୨୧ **Build type:**\n"
                "୨୧ **Any special requests:**\n\n"

                "A staff member will be with you shortly. ♡"
            ),
            color=PINK
        )

        embed.set_footer(
            text="ali's adm house • Support Tickets ♡"
        )


        # Send ticket message
        await ticket_channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=CloseTicketView()
        )


        await interaction.response.send_message(
            f"🎫 Your ticket has been created: {ticket_channel.mention}",
            ephemeral=True
        )


# =========================================================
# CLOSE TICKET BUTTON
# =========================================================

class CloseTicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)


    @discord.ui.button(
        label="Close Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ali_adm_close_ticket"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not is_staff(interaction):

            return await interaction.response.send_message(
                "❌ Only staff members can close tickets.",
                ephemeral=True
            )


        await interaction.response.send_message(
            "🔒 This ticket will close in **3 seconds**..."
        )


        await asyncio.sleep(3)


        await interaction.channel.delete(
            reason=f"Ticket closed by {interaction.user}"
        )


# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    # Register persistent buttons
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())


    try:

        synced = await bot.tree.sync()

        print(
            f"Logged in as {bot.user}"
        )

        print(
            f"Synced {len(synced)} slash commands"
        )

    except Exception as error:

        print(
            f"Command sync error: {error}"
        )


# =========================================================
# /SETUP
# =========================================================

@bot.tree.command(
    name="setup",
    description="Configure the ticket and vouch system."
)
@app_commands.describe(

    panel_channel="Channel where the ticket panel will be sent",

    ticket_category="Category where new tickets will be created",

    vouch_channel="Channel where /vouch messages will be posted",

    staff_role="Staff role that can manage tickets and /say"
)
async def setup(

    interaction: discord.Interaction,

    panel_channel: discord.TextChannel,

    ticket_category: discord.CategoryChannel,

    vouch_channel: discord.TextChannel,

    staff_role: discord.Role | None = None
):


    # Admin only
    if not interaction.user.guild_permissions.administrator:

        return await interaction.response.send_message(
            "❌ You need Administrator permission to use `/setup`.",
            ephemeral=True
        )


    # Save configuration
    config["panel_channel_id"] = panel_channel.id

    config["ticket_category_id"] = ticket_category.id

    config["vouch_channel_id"] = vouch_channel.id

    config["staff_role_id"] = (
        staff_role.id
        if staff_role
        else None
    )

    save_config(config)


    # Ticket panel embed
    embed = discord.Embed(

        title="୨୧・𝒮𝓊𝓅𝓅𝑜𝓇𝓉 𝒯𝒾𝒸𝓀𝑒𝓉𝓈 ♡",

        description=(
            "Need help with an order?\n"
            "Want to ask about one of our houses?\n\n"

            "Open a private ticket below and our staff "
            "will help you! ♡\n\n"

            "୨୧ Please provide as much information as possible."
        ),

        color=PINK
    )


    embed.set_footer(
        text="ali's adm house • Support ♡"
    )


    # Send panel
    await panel_channel.send(
        embed=embed,
        view=TicketView()
    )


    # Confirmation
    await interaction.response.send_message(

        "╭───────────────୨୧\n"
        "│ **Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"

        f"🎫 Panel: {panel_channel.mention}\n"
        f"📁 Ticket Category: **{ticket_category.name}**\n"
        f"⭐ Vouches: {vouch_channel.mention}\n"
        f"👥 Staff: {staff_role.mention if staff_role else 'Manage Channels permission'}",

        ephemeral=True
    )


# =========================================================
# /TICKETPANEL
# =========================================================

@bot.tree.command(
    name="ticketpanel",
    description="Send a ticket panel to a selected channel."
)
@app_commands.describe(
    channel="Channel where the ticket panel should be sent"
)
async def ticketpanel(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):


    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ You need staff permissions to use this.",
            ephemeral=True
        )


    embed = discord.Embed(

        title="୨୧・𝒮𝓊𝓅𝓅𝑜𝓇𝓉 𝒯𝒾𝒸𝓀𝑒𝓉𝓈 ♡",

        description=(
            "Need help? ♡\n\n"
            "Click **🎫 Open Ticket** below "
            "to create a private ticket."
        ),

        color=PINK
    )


    embed.set_footer(
        text="ali's adm house • Support ♡"
    )


    await channel.send(
        embed=embed,
        view=TicketView()
    )


    await interaction.response.send_message(
        f"🎫 Ticket panel sent to {channel.mention}.",
        ephemeral=True
    )


# =========================================================
# /VOUCH
# =========================================================

@bot.tree.command(
    name="vouch",
    description="Leave a vouch for ali's adm house."
)
@app_commands.describe(
    message="Your vouch message"
)
async def vouch(
    interaction: discord.Interaction,
    message: str
):


    # Get configured vouch channel
    channel_id = config.get("vouch_channel_id")

    channel = (
        interaction.guild.get_channel(channel_id)
        if channel_id
        else None
    )


    if not channel:

        return await interaction.response.send_message(

            "❌ The vouch channel hasn't been configured yet.\n"
            "Ask an administrator to use `/setup`.",

            ephemeral=True
        )


    # -----------------------------------------------------
    # VOUCH EMBED
    # -----------------------------------------------------

    embed = discord.Embed(

        title="୨୧・𝒩𝐸𝒲 𝒞𝒰𝒮𝒯𝒪𝑀𝐸𝑅 𝒱𝒪𝒰𝒞𝐻 ♡",

        description=(
            f"**{message}**\n\n"

            "୨୧ **𝒞𝓊𝓈𝓉𝑜𝓂𝑒𝓇**\n"
            f"{interaction.user.mention}"
        ),

        color=PINK
    )


    # Customer avatar + decorative font
    embed.set_author(

        name=(
            f"୨୧ 𝒜𝓁𝒾'𝓈 𝒜𝒟𝑀 𝐻𝑜𝓊𝓈𝑒 ♡"
        ),

        icon_url=interaction.user.display_avatar.url
    )


    # Customer information
    embed.add_field(

        name="♡ 𝒱𝑜𝓊𝒸𝒽𝑒𝒹 𝐵𝓎",

        value=interaction.user.mention,

        inline=False
    )


    # Footer
    embed.set_footer(

        text=(
            "୨୧ ali's adm house • Customer Vouch ♡"
        )
    )


    # Send vouch
    await channel.send(
        embed=embed
    )


    # Private confirmation
    await interaction.response.send_message(

        "♡ Your vouch has been posted! Thank you! ⭐",

        ephemeral=True
    )


# =========================================================
# /SAY
# =========================================================

@bot.tree.command(
    name="say",
    description="Send a styled message through the bot."
)
@app_commands.describe(

    channel="Channel where the message should be sent",

    message="Message to send"
)
async def say(

    interaction: discord.Interaction,

    channel: discord.TextChannel,

    message: str
):


    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can use `/say`.",
            ephemeral=True
        )


    # Styled announcement
    embed = discord.Embed(

        title="୨୧・𝒜𝓃𝓃𝑜𝓊𝓃𝒸𝑒𝓂𝑒𝓃𝓉 ♡",

        description=message,

        color=PINK
    )


    embed.set_footer(
        text="୨୧ ali's adm house • Announcements ♡"
    )


    await channel.send(
        embed=embed
    )


    await interaction.response.send_message(

        f"♡ Message sent to {channel.mention}.",

        ephemeral=True
    )


# =========================================================
# START BOT
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")


if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN is not set. "
        "Set your Discord bot token as an environment variable."
    )


bot.run(TOKEN)

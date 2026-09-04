import os
import json
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route("/")
def home():
    return "ali's adm house bot is online! ♡"

@app.route("/health")
def health():
    return "OK"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(
        host="0.0.0.0",
        port=port
    )

def keep_alive():
    server = Thread(
        target=run_web,
        daemon=True
    )
    server.start()



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
# BOT
# =========================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# COLORS
# =========================================================

PINK = discord.Color.from_rgb(
    255,
    143,
    194
)


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

    # Administrator
    if interaction.user.guild_permissions.administrator:
        return True

    staff_role_id = config.get(
        "staff_role_id"
    )

    # If no staff role is configured,
    # require Manage Channels.
    if not staff_role_id:
        return interaction.user.guild_permissions.manage_channels

    # Check staff role
    return any(
        role.id == staff_role_id
        for role in getattr(
            interaction.user,
            "roles",
            []
        )
    )


# =========================================================
# TICKET PANEL
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )


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


        # ---------------------------------------------
        # GET CATEGORY
        # ---------------------------------------------

        category_id = config.get(
            "ticket_category_id"
        )

        category = (
            guild.get_channel(
                category_id
            )
            if category_id
            else None
        )


        if category is None:

            return await interaction.response.send_message(
                "❌ The ticket category hasn't been configured yet.",
                ephemeral=True
            )


        # ---------------------------------------------
        # CHECK EXISTING TICKET
        # ---------------------------------------------

        for channel in guild.text_channels:

            if channel.topic == (
                f"ali_adm_ticket:{interaction.user.id}"
            ):

                return await interaction.response.send_message(
                    f"❌ You already have an open ticket: {channel.mention}",
                    ephemeral=True
                )


        # ---------------------------------------------
        # STAFF ROLE
        # ---------------------------------------------

        staff_role = None

        staff_role_id = config.get(
            "staff_role_id"
        )

        if staff_role_id:

            staff_role = guild.get_role(
                staff_role_id
            )


        # ---------------------------------------------
        # PERMISSIONS
        # ---------------------------------------------

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

            overwrites[staff_role] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                    attach_files=True,
                    embed_links=True
                )
            )


        # ---------------------------------------------
        # CREATE TICKET
        # ---------------------------------------------

        username = interaction.user.name.lower()

        username = (
            username
            .replace(" ", "-")
            .replace("_", "-")
        )

        ticket_name = (
            f"ticket-{username}"
        )[:90]


        ticket_channel = (
            await guild.create_text_channel(

                name=ticket_name,

                category=category,

                overwrites=overwrites,

                topic=(
                    f"ali_adm_ticket:"
                    f"{interaction.user.id}"
                )
            )
        )


        # ---------------------------------------------
        # TICKET EMBED
        # ---------------------------------------------

        embed = discord.Embed(

            title="୨୧・𝒯𝒾𝒸𝓀𝑒𝓉 𝒪𝓅𝑒𝓃𝑒𝒹 ♡",

            description=(

                f"Welcome {interaction.user.mention}! ♡\n\n"

                "Thank you for contacting "
                "**ali's adm house**!\n\n"

                "Please tell us what you need help with.\n\n"

                "୨୧ **House:**\n"
                "୨୧ **Build type:**\n"
                "୨୧ **Special requests:**\n\n"

                "A staff member will be with you shortly. ♡"
            ),

            color=PINK
        )


        embed.set_footer(
            text="ali's adm house • Support Tickets ♡"
        )


        # ---------------------------------------------
        # SEND TICKET MESSAGE
        # ---------------------------------------------

        await ticket_channel.send(

            content=interaction.user.mention,

            embed=embed,

            view=CloseTicketView(),

            allowed_mentions=discord.AllowedMentions(
                users=[interaction.user]
            )
        )


        # ---------------------------------------------
        # CONFIRMATION
        # ---------------------------------------------

        await interaction.response.send_message(

            f"🎫 Your ticket has been created: "
            f"{ticket_channel.mention}",

            ephemeral=True
        )


# =========================================================
# CLOSE TICKET
# =========================================================

class CloseTicketView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )


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
            reason=(
                f"Ticket closed by "
                f"{interaction.user}"
            )
        )


# =========================================================
# BOT READY
# =========================================================

async def setup_hook():
    # Register persistent button views once when the bot starts.
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as error:
        print(f"Command sync error: {error}")


bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Keep-alive web server is running on port " + os.environ.get("PORT", "8080"))


# =========================================================
# /SETUP
# =========================================================

@bot.tree.command(
    name="setup",
    description="Configure the ticket and vouch system."
)
@app_commands.describe(

    panel_channel=(
        "Channel where the ticket panel "
        "will be sent"
    ),

    ticket_category=(
        "Category where new tickets "
        "will be created"
    ),

    vouch_channel=(
        "Channel where /vouch messages "
        "will be posted"
    ),

    staff_role=(
        "Staff role allowed to manage "
        "tickets and /say"
    )
)
async def setup(

    interaction: discord.Interaction,

    panel_channel: discord.TextChannel,

    ticket_category: discord.CategoryChannel,

    vouch_channel: discord.TextChannel,

    staff_role: discord.Role | None = None

):


    # ---------------------------------------------
    # ADMIN CHECK
    # ---------------------------------------------

    if not interaction.user.guild_permissions.administrator:

        return await interaction.response.send_message(

            "❌ You need **Administrator** permission "
            "to use `/setup`.",

            ephemeral=True
        )


    # ---------------------------------------------
    # SAVE CONFIG
    # ---------------------------------------------

    config["panel_channel_id"] = (
        panel_channel.id
    )

    config["ticket_category_id"] = (
        ticket_category.id
    )

    config["vouch_channel_id"] = (
        vouch_channel.id
    )

    config["staff_role_id"] = (

        staff_role.id

        if staff_role

        else None
    )


    save_config(
        config
    )


    # ---------------------------------------------
    # TICKET PANEL EMBED
    # ---------------------------------------------

    embed = discord.Embed(

        title=(
            "୨୧・𝒮𝓊𝓅𝓅𝑜𝓇𝓉 "
            "𝒯𝒾𝒸𝓀𝑒𝓉𝓈 ♡"
        ),

        description=(

            "Need help with an order?\n"
            "Want to ask about one of our houses?\n\n"

            "Click **🎫 Open Ticket** below "
            "to create a private ticket with "
            "our staff! ♡\n\n"

            "୨୧ Please provide as much "
            "information as possible."
        ),

        color=PINK
    )


    embed.set_footer(
        text="ali's adm house • Support ♡"
    )


    # ---------------------------------------------
    # SEND PANEL
    # ---------------------------------------------

    await panel_channel.send(

        embed=embed,

        view=TicketView()
    )


    # ---------------------------------------------
    # CONFIRM
    # ---------------------------------------------

    await interaction.response.send_message(

        "╭───────────────୨୧\n"
        "│ **Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"

        f"🎫 Panel: "
        f"{panel_channel.mention}\n"

        f"📁 Ticket Category: "
        f"**{ticket_category.name}**\n"

        f"⭐ Vouches: "
        f"{vouch_channel.mention}\n"

        f"👥 Staff: "
        f"{staff_role.mention if staff_role else 'Manage Channels'}",

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

    channel=(
        "Channel where the ticket panel "
        "should be sent"
    )
)
async def ticketpanel(

    interaction: discord.Interaction,

    channel: discord.TextChannel

):


    if not is_staff(interaction):

        return await interaction.response.send_message(

            "❌ You need staff permissions "
            "to use this command.",

            ephemeral=True
        )


    embed = discord.Embed(

        title=(
            "୨୧・𝒮𝓊𝓅𝓅𝑜𝓇𝓉 "
            "𝒯𝒾𝒸𝓀𝑒𝓉𝓈 ♡"
        ),

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

        f"🎫 Ticket panel sent to "
        f"{channel.mention}.",

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


    # ---------------------------------------------
    # GET VOUCH CHANNEL
    # ---------------------------------------------

    channel_id = config.get(
        "vouch_channel_id"
    )


    channel = (

        interaction.guild.get_channel(
            channel_id
        )

        if channel_id

        else None
    )


    if channel is None:

        return await interaction.response.send_message(

            "❌ The vouch channel hasn't "
            "been configured yet.\n\n"

            "Ask an administrator to use "
            "`/setup`.",

            ephemeral=True
        )


    # ---------------------------------------------
    # VOUCH EMBED
    # ---------------------------------------------

    embed = discord.Embed(

        title=(
            "୨୧・𝒩𝐸𝒲 "
            "𝒞𝒰𝒮𝒯𝒪𝑀𝐸𝑅 "
            "𝒱𝒪𝒰𝒞𝐻 ♡"
        ),

        description=(

            f"**{message}**\n\n"

            "୨୧ **𝒞𝓊𝓈𝓉𝑜𝓂𝑒𝓇**\n"

            f"{interaction.user.mention}"
        ),

        color=PINK
    )


    # ---------------------------------------------
    # SHOP AUTHOR
    # ---------------------------------------------

    embed.set_author(

        name=(
            "୨୧ 𝒜𝓁𝒾'𝓈 "
            "𝒜𝒟𝑀 𝐻𝑜𝓊𝓈𝑒 ♡"
        )
    )


    # ---------------------------------------------
    # FOOTER
    # ---------------------------------------------

    embed.set_footer(

        text=(
            "୨୧ ali's adm house "
            "• Customer Vouch ♡"
        )
    )


    # ---------------------------------------------
    # SEND VOUCH
    # ---------------------------------------------

    await channel.send(

        embed=embed,

        # This allows the actual user mention
        # inside the embed to ping them.
        allowed_mentions=discord.AllowedMentions(
            users=[interaction.user]
        )
    )


    # ---------------------------------------------
    # CONFIRMATION
    # ---------------------------------------------

    await interaction.response.send_message(

        "♡ Your vouch has been posted! "
        "Thank you! ⭐",

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

    channel=(
        "Channel where the message "
        "should be sent"
    ),

    message=(
        "Message to send"
    )
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


    # ---------------------------------------------
    # ANNOUNCEMENT EMBED
    # ---------------------------------------------

    embed = discord.Embed(

        title=(
            "୨୧・𝒜𝓃𝓃𝑜𝓊𝓃𝒸𝑒𝓂𝑒𝓃𝓉 ♡"
        ),

        description=message,

        color=PINK
    )


    embed.set_footer(

        text=(
            "୨୧ ali's adm house "
            "• Announcements ♡"
        )
    )


    await channel.send(
        embed=embed
    )


    await interaction.response.send_message(

        f"♡ Message sent to "
        f"{channel.mention}.",

        ephemeral=True
    )


# =========================================================
# RUN BOT
# =========================================================

TOKEN = os.getenv(
    "DISCORD_TOKEN"
)


if not TOKEN:

    raise RuntimeError(

        "DISCORD_TOKEN is not set.\n\n"

        "Windows PowerShell:\n"

        '$env:DISCORD_TOKEN="YOUR_BOT_TOKEN"\n'

        "python bot.py"
    )


keep_alive()

bot.run(
    TOKEN
)

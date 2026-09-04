import os
import json
import asyncio
import discord

from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread


# =========================================================
# KEEP ALIVE
# =========================================================

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
        port=port,
        debug=False,
        use_reloader=False
    )


def keep_alive():
    server = Thread(
        target=run_web,
        daemon=True
    )

    server.start()

    print(f"Keep-alive web server started on port {os.environ.get('PORT', '8080')}")


# =========================================================
# CONFIG (PERSISTENT HARDCODED / ENV FALLBACKS)
# =========================================================

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "panel_channel_id": int(os.getenv("PANEL_CHANNEL_ID", 0)) or None,
    "ticket_category_id": int(os.getenv("TICKET_CATEGORY_ID", 0)) or None,
    "vouch_channel_id": int(os.getenv("VOUCH_CHANNEL_ID", 0)) or None,
    "status_channel_id": int(os.getenv("STATUS_CHANNEL_ID", 0)) or None,
    "staff_role_id": int(os.getenv("STAFF_ROLE_ID", 0)) or None
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            for key, val in DEFAULT_CONFIG.items():
                if not data.get(key) and val:
                    data[key] = val
            return data

    except (json.JSONDecodeError, OSError):
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


config = load_config()


# =========================================================
# BOT / INTENTS
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

PINK = discord.Color.from_rgb(255, 143, 194)
GREEN = discord.Color.from_rgb(87, 242, 135)
RED = discord.Color.from_rgb(237, 66, 69)
GRAY = discord.Color.from_rgb(149, 165, 166)


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
    if interaction.guild is None:
        return False

    if interaction.user.guild_permissions.administrator:
        return True

    staff_role_id = config.get("staff_role_id")

    if not staff_role_id:
        return interaction.user.guild_permissions.manage_channels

    return any(
        role.id == staff_role_id
        for role in getattr(interaction.user, "roles", [])
    )


# =========================================================
# TICKET PANEL VIEW
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

        category_id = config.get("ticket_category_id")

        category = (
            guild.get_channel(category_id)
            if category_id
            else None
        )

        if category is None:
            return await interaction.response.send_message(
                "❌ The ticket category hasn't been configured yet.",
                ephemeral=True
            )

        for channel in guild.text_channels:
            if channel.topic == f"ali_adm_ticket:{interaction.user.id}":
                return await interaction.response.send_message(
                    f"❌ You already have an open ticket: {channel.mention}",
                    ephemeral=True
                )

        staff_role = None
        staff_role_id = config.get("staff_role_id")

        if staff_role_id:
            staff_role = guild.get_role(staff_role_id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
        }

        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                attach_files=True,
                embed_links=True
            )

        username = interaction.user.name.lower().replace(" ", "-").replace("_", "-")
        ticket_name = f"ticket-{username}"[:90]

        ticket_channel = await guild.create_text_channel(
            name=ticket_name,
            category=category,
            overwrites=overwrites,
            topic=f"ali_adm_ticket:{interaction.user.id}"
        )

        embed = discord.Embed(
            title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
            description=(
                f"Welcome {interaction.user.mention}! ♡\n\n"
                "Thank you for contacting **ali's adm house**!\n\n"
                "Please tell us what you need help with.\n\n"
                "୨୧ **House:**\n"
                "୨୧ **Build type:**\n"
                "୨୧ **Special requests:**\n\n"
                "A staff member will be with you shortly. ♡"
            ),
            color=PINK
        )

        embed.set_footer(text="ali's adm house • Support Tickets ♡")

        await ticket_channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=CloseTicketView(),
            allowed_mentions=discord.AllowedMentions(users=[interaction.user])
        )

        await interaction.response.send_message(
            f"🎫 Your ticket has been created: {ticket_channel.mention}",
            ephemeral=True
        )


# =========================================================
# CLOSE TICKET VIEW
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
        if is_staff(interaction):
            await interaction.response.send_message(
                "🔒 Closing ticket in **3 seconds**..."
            )
            await asyncio.sleep(3)
            if interaction.channel:
                await interaction.channel.delete(
                    reason=f"Ticket closed by staff member {interaction.user}"
                )
            return

        vouch_channel_id = config.get("vouch_channel_id")
        vouch_channel = (
            interaction.guild.get_channel(vouch_channel_id)
            if vouch_channel_id and interaction.guild
            else None
        )

        if not vouch_channel:
            return await interaction.response.send_message(
                "❌ The vouch channel has not been configured yet.",
                ephemeral=True
            )

        ticket_created_at = interaction.channel.created_at
        has_vouched = False

        async for message in vouch_channel.history(limit=100):
            if message.author == interaction.client.user:
                if interaction.user in message.mentions or str(interaction.user.id) in message.content:
                    if message.created_at >= ticket_created_at:
                        has_vouched = True
                        break

        bot_commands_channel = discord.utils.get(
            interaction.guild.text_channels, 
            name="₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼"
        )
        
        bot_commands_mention = (
            bot_commands_channel.mention 
            if bot_commands_channel 
            else "`#₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼`"
        )

        if not has_vouched:
            return await interaction.response.send_message(
                f"Did you vouch yet? ♡ If not, please use `/vouch` or `!vouch` in {bot_commands_mention} before closing your ticket!",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Thank you so much for your order and for leaving a vouch! ♡\n"
            "We hope to see you again at **ali's adm house**! 🌸\n\n"
            "🔒 *Closing this ticket in 3 seconds...*"
        )
        await asyncio.sleep(3)

        if interaction.channel:
            await interaction.channel.delete(
                reason=f"Ticket closed by customer {interaction.user} (Verified fresh vouch)"
            )


# =========================================================
# BOT READY (WITH DUPLICATE CLEANUP)
# =========================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Persistent buttons
    if not getattr(bot, "_persistent_views_loaded", False):
        bot.add_view(TicketView())
        bot.add_view(CloseTicketView())
        bot._persistent_views_loaded = True

    try:
        # 1. Clear guild-level overrides to remove duplicate commands
        for guild in bot.guilds:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)

        # 2. Global sync
        synced = await bot.tree.sync()
        print(f"Successfully cleared duplicates and synced {len(synced)} command(s) globally!")

    except Exception as error:
        print(f"Command sync error: {error}")


# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(
    name="setup",
    description="Configure the ticket, vouch, and status system."
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    panel_channel="Channel where the ticket panel will be sent",
    ticket_category="Category where new tickets will be created",
    vouch_channel="Channel where /vouch messages will be posted",
    status_channel="Channel where order status updates will be posted",
    staff_role="Staff role allowed to manage tickets and /say"
)
async def setup(
    interaction: discord.Interaction,
    panel_channel: discord.TextChannel,
    ticket_category: discord.CategoryChannel,
    vouch_channel: discord.TextChannel,
    status_channel: discord.TextChannel | None = None,
    staff_role: discord.Role | None = None
):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ You need **Administrator** permission to use `/setup`.",
            ephemeral=True
        )

    config["panel_channel_id"] = panel_channel.id
    config["ticket_category_id"] = ticket_category.id
    config["vouch_channel_id"] = vouch_channel.id
    config["status_channel_id"] = status_channel.id if status_channel else None
    config["staff_role_id"] = staff_role.id if staff_role else None

    save_config(config)

    embed = discord.Embed(
        title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
        description=(
            "Need help with an order?\n"
            "Want to ask about one of our houses?\n\n"
            "Click **🎫 Open Ticket** below to create a private ticket with our staff! ♡\n\n"
            "୨୧ Please provide as much information as possible."
        ),
        color=PINK
    )

    embed.set_footer(text="ali's adm house • Support ♡")

    await panel_channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        "╭───────────────୨୧\n"
        "│ **Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"🎫 Panel: {panel_channel.mention}\n"
        f"📁 Ticket Category: **{ticket_category.name}**\n"
        f"⭐ Vouches: {vouch_channel.mention}\n"
        f"📊 Status: {status_channel.mention if status_channel else 'Not Configured'}\n"
        f"👥 Staff: {staff_role.mention if staff_role else 'Manage Channels'}",
        ephemeral=True
    )


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
            "❌ You need staff permissions to use this command.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
        description=(
            "Need help? ♡\n\n"
            "Click **🎫 Open Ticket** below to create a private ticket."
        ),
        color=PINK
    )

    embed.set_footer(text="ali's adm house • Support ♡")

    await channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        f"🎫 Ticket panel sent to {channel.mention}.",
        ephemeral=True
    )


@bot.tree.command(
    name="vouch",
    description="Leave a vouch for ali's adm house."
)
@app_commands.default_permissions(send_messages=True)
@app_commands.describe(
    message="Your vouch message"
)
async def vouch(
    interaction: discord.Interaction,
    message: str
):

    channel_id = config.get("vouch_channel_id")
    channel = (
        interaction.guild.get_channel(channel_id)
        if channel_id and interaction.guild
        else None
    )

    if channel is None:
        return await interaction.response.send_message(
            "❌ The vouch channel hasn't been configured yet.\n\nAsk an administrator to use `/setup`.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡",
        description=(
            f"**{message}**\n\n"
            "୨୧ **𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳**\n"
            f"{interaction.user.mention}\n\n"
            "Thank you so much! ♡"
        ),
        color=PINK
    )

    embed.set_author(name="୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡")
    embed.set_footer(text="୨୧ ali's adm house • Customer Vouch ♡")

    await channel.send(
        content=interaction.user.mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(users=[interaction.user])
    )

    await interaction.response.send_message(
        "♡ Your vouch has been posted! Thank you! ⭐",
        ephemeral=True
    )


@bot.tree.command(
    name="vouchcount",
    description="Check how many vouches a user has submitted."
)
@app_commands.describe(
    user="The user to check vouches for (defaults to you)"
)
async def vouchcount(
    interaction: discord.Interaction,
    user: discord.Member | None = None
):

    target_user = user or interaction.user
    vouch_channel_id = config.get("vouch_channel_id")
    vouch_channel = (
        interaction.guild.get_channel(vouch_channel_id)
        if vouch_channel_id and interaction.guild
        else None
    )

    if not vouch_channel:
        return await interaction.response.send_message(
            "❌ The vouch channel hasn't been configured yet.",
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    count = 0
    async for message in vouch_channel.history(limit=500):
        if message.author == bot.user:
            if target_user in message.mentions or str(target_user.id) in message.content:
                count += 1

    embed = discord.Embed(
        title="୨୧・𝘷𝘰𝘶𝘤𝘩 𝘤𝘰𝘶𝘯𝘵 ♡",
        description=(
            f"**{target_user.mention}** currently has **{count}** total vouch(es)! ⭐\n\n"
            "Thank you for supporting **ali's adm house**! ♡"
        ),
        color=PINK
    )
    embed.set_footer(text="ali's adm house • Customer Statistics ♡")

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="ping",
    description="Check the bot's latency and connection status."
)
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)

    embed = discord.Embed(
        title="୨୧・𝘱𝘰𝘯𝘨! ♡",
        description=f"🌸 Bot Latency: **{latency}ms**\n✨ Status: **Online & Operational**",
        color=PINK
    )
    embed.set_footer(text="ali's adm house • Bot Status ♡")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="status",
    description="Update shop order status (Available, Busy, or Closed)."
)
@app_commands.choices(state=[
    app_commands.Choice(name="Available (Green)", value="available"),
    app_commands.Choice(name="Busy (Red)", value="busy"),
    app_commands.Choice(name="Closed (Gray)", value="closed")
])
async def status(
    interaction: discord.Interaction,
    state: app_commands.Choice[str]
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff members can update the shop status.",
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    status_channel_id = config.get("status_channel_id")
    status_channel = (
        interaction.guild.get_channel(status_channel_id)
        if status_channel_id and interaction.guild
        else None
    )

    if not status_channel:
        return await interaction.followup.send(
            "❌ Status channel not configured! Use `/setup` and include the status channel.",
            ephemeral=True
        )

    if state.value == "available":
        channel_name = "🟢-available"
        title = "🟢・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘢𝘷𝘢𝘪𝘭𝘢𝘣𝘭𝘦"
        desc = "Our shop is currently **OPEN** for new orders! ♡\n\nFeel free to open a ticket to place your order."
        color = GREEN
    elif state.value == "busy":
        channel_name = "🔴-busy"
        title = "🔴・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘣𝘶𝘴𝘺"
        desc = "Our shop is currently **BUSY**! 🎀\n\nOrder fulfillment might take a little longer than usual, but tickets are open!"
        color = RED
    else:
        channel_name = "⚪-closed"
        title = "⚪・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘤𝘭𝘰𝘴𝘦𝘥"
        desc = "Our shop is currently **CLOSED**! ♡\n\nPlease check back later when we reopen!"
        color = GRAY

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color
    )
    embed.set_footer(text="ali's adm house • Shop Status ♡")

    await status_channel.send(embed=embed)

    await interaction.followup.send(
        f"♡ Shop status updated to **{state.name}** in {status_channel.mention}!",
        ephemeral=True
    )

    # Attempts to rename the channel safely in background without freezing command execution
    if status_channel.name != channel_name:
        try:
            await asyncio.wait_for(status_channel.edit(name=channel_name), timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            print("Channel rename deferred/skipped due to Discord rate limits.")


@bot.tree.command(
    name="say",
    description="Send a styled message through the bot."
)
@app_commands.describe(
    channel="Channel where the message should be sent",
    message="Message to send",
    role="Optional role to ping for the announcement"
)
async def say(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str,
    role: discord.Role | None = None
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff can use `/say`.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="𝘢𝘯𝘯𝘰𝘶𝘯𝘤𝘦𝘮𝘦𝘯𝘵",
        description=message,
        color=PINK
    )

    embed.set_footer(text="୨୧ ali's adm house • Announcements ♡")

    content_text = role.mention if role else None

    await channel.send(
        content=content_text,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )

    await interaction.response.send_message(
        f"♡ Message sent to {channel.mention}.",
        ephemeral=True
    )


# =========================================================
# PREFIX COMMANDS
# =========================================================

@bot.command(name="vouch")
async def vouch_prefix(ctx, *, message: str = None):
    if message is None:
        return await ctx.send(
            "❌ Please include a message! Example: `!vouch Great service!`",
            delete_after=10
        )

    channel_id = config.get("vouch_channel_id")
    channel = ctx.guild.get_channel(channel_id) if channel_id and ctx.guild else None

    if channel is None:
        return await ctx.send("❌ The vouch channel hasn't been configured yet.")

    embed = discord.Embed(
        title="୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡",
        description=f"**{message}**\n\n୨୧ **𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳**\n{ctx.author.mention}\n\nThank you so much! ♡",
        color=PINK
    )
    embed.set_author(name="୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡")
    embed.set_footer(text="୨୧ ali's adm house • Customer Vouch ♡")

    await channel.send(
        content=ctx.author.mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(users=[ctx.author])
    )

    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    await ctx.send(f"♡ Thank you {ctx.author.mention}, your vouch has been posted! ⭐", delete_after=5)


# =========================================================
# ERROR HANDLER
# =========================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    print(f"Command error: {error}")


# =========================================================
# RUN BOT
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is not set.\n\n"
        "Windows PowerShell:\n"
        '$env:DISCORD_TOKEN="YOUR_BOT_TOKEN"\n'
        "python bot.py"
    )


keep_alive()
bot.run(TOKEN)

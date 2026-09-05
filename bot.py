```python
import os
import io
import json
import asyncio
import datetime
from threading import Thread

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from PIL import Image, ImageFilter


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
    port = int(os.environ.get("PORT", "8080"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


def keep_alive():
    thread = Thread(target=run_web, daemon=True)
    thread.start()

    print(
        f"Keep-alive web server started on port "
        f"{os.environ.get('PORT', '8080')}"
    )


# =========================================================
# CONFIG
# =========================================================

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "panel_channel_id": int(os.getenv("PANEL_CHANNEL_ID", "0")) or None,
    "ticket_category_id": int(os.getenv("TICKET_CATEGORY_ID", "0")) or None,
    "vouch_channel_id": int(os.getenv("VOUCH_CHANNEL_ID", "0")) or None,
    "status_channel_id": int(os.getenv("STATUS_CHANNEL_ID", "0")) or None,
    "welcome_goodbye_channel_id": int(
        os.getenv("WELCOME_GOODBYE_CHANNEL_ID", "0")
    ) or None,
    "proof_channel_id": int(os.getenv("PROOF_CHANNEL_ID", "0")) or None,
    "staff_role_id": int(os.getenv("STAFF_ROLE_ID", "0")) or None,

    # Your existing customer role
    "customer_role_id": int(
        os.getenv(
            "CUSTOMER_ROLE_ID",
            "1545438540362555463"
        )
    ) or 1545438540362555463
}


def save_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
    except OSError as error:
        print(f"Could not save config: {error}")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        data = DEFAULT_CONFIG.copy()
        save_config(data)
        return data

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Make sure all required keys exist
        changed = False

        for key, value in DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = value
                changed = True

        if changed:
            save_config(data)

        return data

    except (json.JSONDecodeError, OSError) as error:
        print(f"Could not load config: {error}")

        data = DEFAULT_CONFIG.copy()
        save_config(data)

        return data


config = load_config()


# =========================================================
# INTENTS
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

def styled_embed(title, description, color=PINK):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )

    embed.set_footer(
        text="୨୧ ali's adm house • Customer Shop ♡"
    )

    return embed


# =========================================================
# IMAGE BLUR
# =========================================================

def blur_names(image_data: bytes) -> bytes:
    try:
        img = Image.open(
            io.BytesIO(image_data)
        ).convert("RGB")

        width, height = img.size

        blur_height = max(
            1,
            int(height * 0.15)
        )

        top = img.crop(
            (0, 0, width, blur_height)
        )

        blurred = top.filter(
            ImageFilter.GaussianBlur(radius=15)
        )

        img.paste(
            blurred,
            (0, 0)
        )

        output = io.BytesIO()

        img.save(
            output,
            format="PNG"
        )

        output.seek(0)

        return output.getvalue()

    except Exception as error:
        print(f"Error blurring image: {error}")
        return image_data


# =========================================================
# STAFF CHECK
# =========================================================

def is_staff(interaction: discord.Interaction):
    if interaction.guild is None:
        return False

    member = interaction.user

    if member.guild_permissions.administrator:
        return True

    staff_role_id = config.get("staff_role_id")

    if staff_role_id:
        return any(
            role.id == staff_role_id
            for role in getattr(member, "roles", [])
        )

    return member.guild_permissions.manage_channels


# =========================================================
# MODERATION TARGET CHECK
# =========================================================

def can_moderate(
    interaction: discord.Interaction,
    member: discord.Member
):
    if interaction.guild is None:
        return False, "This command can only be used inside a server."

    if member.id == interaction.user.id:
        return False, "You cannot moderate yourself."

    if member.id == interaction.guild.owner_id:
        return False, "You cannot moderate the server owner."

    if (
        interaction.user.id != interaction.guild.owner_id
        and member.top_role >= interaction.user.top_role
    ):
        return False, "That user's highest role is equal to or higher than yours."

    if (
        interaction.guild.me
        and member.top_role >= interaction.guild.me.top_role
    ):
        return False, "My highest role is not above that user's highest role."

    return True, None


# =========================================================
# CHANNEL RENAME QUEUE
# =========================================================

pending_renames = {}


async def process_channel_renames():
    await bot.wait_until_ready()

    while not bot.is_closed():

        if pending_renames:

            channel_id, new_name = next(
                iter(pending_renames.items())
            )

            del pending_renames[channel_id]

            channel = bot.get_channel(channel_id)

            if channel and hasattr(channel, "name"):

                if channel.name != new_name:

                    try:
                        await channel.edit(
                            name=new_name,
                            reason="Shop status update"
                        )

                        print(
                            f"Renamed channel {channel.id} "
                            f"to {new_name}"
                        )

                    except discord.HTTPException as error:

                        if error.status == 429:

                            retry_after = getattr(
                                error,
                                "retry_after",
                                10
                            )

                            print(
                                f"Rate limited. "
                                f"Retrying in {retry_after}s"
                            )

                            pending_renames[channel_id] = new_name

                            await asyncio.sleep(
                                retry_after
                            )

                        else:
                            print(
                                f"Channel rename error: {error}"
                            )

                    except Exception as error:
                        print(
                            f"Channel rename error: {error}"
                        )

        await asyncio.sleep(5)


# =========================================================
# WELCOME
# =========================================================

@bot.event
async def on_member_join(member: discord.Member):

    customer_role_id = config.get(
        "customer_role_id"
    )

    if customer_role_id:

        role = member.guild.get_role(
            customer_role_id
        )

        if role:

            try:
                await member.add_roles(
                    role,
                    reason="Automatic customer role on join"
                )

            except discord.Forbidden:
                print(
                    f"Cannot give {role.name} to "
                    f"{member}"
                )

            except Exception as error:
                print(
                    f"Customer role error: {error}"
                )

    channel_id = config.get(
        "welcome_goodbye_channel_id"
    )

    if not channel_id:
        return

    channel = member.guild.get_channel(
        channel_id
    )

    if not channel:
        return

    embed = discord.Embed(
        title=(
            "╭───────────── ୨୧ ─────────────╮\n"
            "       🌸˚₊ 𝘸𝘦𝘭𝘤𝘰𝘮𝘦 𝘵𝘰 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦! ♡\n"
            "╰───────────── ୨୧ ─────────────╯"
        ),
        description=(
            f"Welcome {member.mention}! "
            "We are so thrilled to have you join "
            "our community! ♡\n\n"

            "✦ **Getting Started:**\n"
            "Check out our products and shop listings!\n"
            "Open a support ticket to place custom orders "
            "or ask questions!\n"
            "Feel free to hang out and chat with our lovely members!\n\n"

            "─────────────── ୨୧ ───────────────"
        ),
        color=PINK
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.add_field(
        name="🌸˚₊ Customer",
        value=f"• {member.mention}",
        inline=True
    )

    embed.add_field(
        name="⭐˚₊ Member Count",
        value=f"• `#{member.guild.member_count}`",
        inline=True
    )

    # No creation time field
    embed.set_footer(
        text="ali's adm house • Customer Shop ♡",
        icon_url=(
            member.guild.icon.url
            if member.guild.icon
            else None
        )
    )

    await channel.send(
        content=f"👋 Welcome to the server {member.mention}! ♡",
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            users=[member]
        )
    )


# =========================================================
# GOODBYE
# =========================================================

@bot.event
async def on_member_remove(member: discord.Member):

    channel_id = config.get(
        "welcome_goodbye_channel_id"
    )

    if not channel_id:
        return

    channel = member.guild.get_channel(
        channel_id
    )

    if not channel:
        return

    embed = discord.Embed(
        title=(
            "╭───────────── ୨୧ ─────────────╮\n"
            "            💔˚₊ 𝘨𝘰𝘰𝘥𝘣𝘺𝘦, 𝘴𝘦𝘦 𝘺𝘰𝘶 𝘴𝘰𝘰𝘯! ♡\n"
            "╰───────────── ୨୧ ─────────────╯"
        ),
        description=(
            f"**{member.name}** has left "
            "**ali's adm house**... 💔\n\n"
            "We're sad to see you leave, but we hope "
            "to see you back again soon! ♡\n\n"
            "─────────────── ୨୧ ───────────────"
        ),
        color=GRAY
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.add_field(
        name="🌸˚₊ User",
        value=f"• **{member.name}**",
        inline=True
    )

    embed.add_field(
        name="⭐˚₊ Remaining Members",
        value=f"• `{member.guild.member_count}`",
        inline=True
    )

    embed.set_footer(
        text="ali's adm house • Member Departure ♡",
        icon_url=(
            member.guild.icon.url
            if member.guild.icon
            else None
        )
    )

    await channel.send(
        embed=embed
    )


# =========================================================
# TICKET VIEW
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
            return await interaction.response.send_message(
                "❌ This button can only be used in a server.",
                ephemeral=True
            )

        category_id = config.get(
            "ticket_category_id"
        )

        category = (
            guild.get_channel(category_id)
            if category_id
            else None
        )

        if not isinstance(
            category,
            discord.CategoryChannel
        ):
            return await interaction.response.send_message(
                "❌ The ticket category hasn't been configured yet.",
                ephemeral=True
            )

        for channel in guild.text_channels:

            if channel.topic == (
                f"ali_adm_ticket:{interaction.user.id}"
            ):

                return await interaction.response.send_message(
                    f"❌ You already have an open ticket: "
                    f"{channel.mention}",
                    ephemeral=True
                )

        staff_role = None

        staff_role_id = config.get(
            "staff_role_id"
        )

        if staff_role_id:
            staff_role = guild.get_role(
                staff_role_id
            )

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

        username = (
            interaction.user.name
            .lower()
            .replace(" ", "-")
            .replace("_", "-")
        )

        ticket_name = (
            f"ticket-{username}"
        )[:90]

        try:

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

        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ I don't have permission to create ticket channels.",
                ephemeral=True
            )

        except discord.HTTPException as error:
            return await interaction.response.send_message(
                f"❌ Discord returned an error: `{error}`",
                ephemeral=True
            )

        embed = discord.Embed(
            title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
            description=(
                f"Welcome {interaction.user.mention}! ♡\n\n"
                "Thank you for contacting "
                "**ali's adm house**!\n\n"
                "Please tell us what you need help with.\n\n"
                "୨୧ **House:**\n"
                "୨୧ **Build type:**\n\n"
                "A staff member will be with you shortly. ♡"
            ),
            color=PINK
        )

        embed.set_footer(
            text="ali's adm house • Support Tickets ♡"
        )

        await ticket_channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=CloseTicketView(),
            allowed_mentions=discord.AllowedMentions(
                users=[interaction.user]
            )
        )

        await interaction.response.send_message(
            f"🎫 Your ticket has been created: "
            f"{ticket_channel.mention}",
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

        if not interaction.guild:
            return

        if is_staff(interaction):

            await interaction.response.send_message(
                "🔒 Closing ticket in **3 seconds**..."
            )

            await asyncio.sleep(3)

            if interaction.channel:
                await interaction.channel.delete(
                    reason=(
                        f"Ticket closed by staff "
                        f"{interaction.user}"
                    )
                )

            return

        vouch_channel_id = config.get(
            "vouch_channel_id"
        )

        vouch_channel = (
            interaction.guild.get_channel(
                vouch_channel_id
            )
            if vouch_channel_id
            else None
        )

        if not vouch_channel:
            return await interaction.response.send_message(
                "❌ The vouch channel has not been configured yet.",
                ephemeral=True
            )

        ticket_created_at = (
            interaction.channel.created_at
            if interaction.channel
            else discord.utils.utcnow()
        )

        has_vouched = False

        async for message in vouch_channel.history(
            limit=100
        ):

            if message.author != bot.user:
                continue

            if (
                interaction.user in message.mentions
                or str(interaction.user.id)
                in message.content
            ):

                if message.created_at >= ticket_created_at:
                    has_vouched = True
                    break

        bot_commands_channel = discord.utils.get(
            interaction.guild.text_channels,
            name="₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼"
        )

        if bot_commands_channel:
            bot_commands_mention = (
                bot_commands_channel.mention
            )
        else:
            bot_commands_mention = (
                "`#₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼`"
            )

        if not has_vouched:

            return await interaction.response.send_message(
                "Did you vouch yet? ♡\n\n"
                f"If not, please use `/vouch` "
                f"in {bot_commands_mention} "
                "before closing your ticket!",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Thank you so much for your order "
            "and for leaving a vouch! ♡\n"
            "We hope to see you again at "
            "**ali's adm house**! 🌸\n\n"
            "🔒 *Closing this ticket in 3 seconds...*"
        )

        await asyncio.sleep(3)

        if interaction.channel:

            await interaction.channel.delete(
                reason=(
                    f"Ticket closed by customer "
                    f"{interaction.user}"
                )
            )


# =========================================================
# BOT SETUP / READY
# =========================================================

@bot.event
async def setup_hook():

    # Persistent buttons
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())

    # Start rename task
    asyncio.create_task(
        process_channel_renames()
    )

    # Sync commands
    try:

        synced = await bot.tree.sync()

        print(
            f"Synced {len(synced)} global slash command(s)."
        )

    except Exception as error:

        print(
            f"Slash command sync failed: {error}"
        )


@bot.event
async def on_ready():

    print(
        "========================================"
    )

    print(
        f"Logged in as: {bot.user}"
    )

    print(
        f"Bot ID: {bot.user.id}"
    )

    print(
        f"Connected to {len(bot.guilds)} server(s)"
    )

    print(
        "========================================"
    )


# =========================================================
# SETUP
# =========================================================

@bot.tree.command(
    name="setup",
    description="Configure the ticket system."
)
@app_commands.default_permissions(
    administrator=True
)
@app_commands.describe(
    panel_channel="Channel where the ticket panel will be sent",
    ticket_category="Category where tickets will be created",
    staff_role="Staff role allowed to manage tickets",
    vouch_channel="Channel where vouches are posted"
)
async def setup(
    interaction: discord.Interaction,
    panel_channel: discord.TextChannel,
    ticket_category: discord.CategoryChannel,
    staff_role: discord.Role | None = None,
    vouch_channel: discord.TextChannel | None = None
):

    if not interaction.user.guild_permissions.administrator:

        return await interaction.response.send_message(
            "❌ You need **Administrator** permission.",
            ephemeral=True
        )

    config["panel_channel_id"] = panel_channel.id
    config["ticket_category_id"] = ticket_category.id
    config["staff_role_id"] = (
        staff_role.id
        if staff_role
        else None
    )

    if vouch_channel:
        config["vouch_channel_id"] = (
            vouch_channel.id
        )

    save_config(config)

    embed = discord.Embed(
        title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
        description=(
            "Need help with an order?\n"
            "Want to ask about one of our houses?\n\n"
            "Click **🎫 Open Ticket** below "
            "to create a private ticket with our staff! ♡\n\n"
            "୨୧ Please provide as much information as possible."
        ),
        color=PINK
    )

    embed.set_footer(
        text="ali's adm house • Support ♡"
    )

    await panel_channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        "╭───────────────୨୧\n"
        "│ **Ticket Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"🎫 Panel: {panel_channel.mention}\n"
        f"📁 Category: **{ticket_category.name}**\n"
        f"👥 Staff: "
        f"{staff_role.mention if staff_role else 'Manage Channels'}\n"
        f"⭐ Vouches: "
        f"{vouch_channel.mention if vouch_channel else 'Not Updated'}",
        ephemeral=True
    )


# =========================================================
# STATUS SETUP
# =========================================================

@bot.tree.command(
    name="setupstatus",
    description="Configure the shop status channel."
)
@app_commands.default_permissions(
    administrator=True
)
async def setupstatus(
    interaction: discord.Interaction,
    status_channel: discord.TextChannel
):

    if not interaction.user.guild_permissions.administrator:

        return await interaction.response.send_message(
            "❌ You need **Administrator** permission.",
            ephemeral=True
        )

    config["status_channel_id"] = (
        status_channel.id
    )

    save_config(config)

    await interaction.response.send_message(
        "╭───────────────୨୧\n"
        "│ **Status Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"📊 Status Channel: "
        f"{status_channel.mention}",
        ephemeral=True
    )


# =========================================================
# JOINS SETUP
# =========================================================

@bot.tree.command(
    name="setupjoins",
    description="Configure welcome, goodbye, and customer role."
)
@app_commands.default_permissions(
    administrator=True
)
async def setupjoins(
    interaction: discord.Interaction,
    welcome_goodbye_channel: discord.TextChannel,
    customer_role: discord.Role | None = None
):

    if not interaction.user.guild_permissions.administrator:

        return await interaction.response.send_message(
            "❌ You need **Administrator** permission.",
            ephemeral=True
        )

    config["welcome_goodbye_channel_id"] = (
        welcome_goodbye_channel.id
    )

    if customer_role:
        config["customer_role_id"] = (
            customer_role.id
        )

    save_config(config)

    role = interaction.guild.get_role(
        config.get("customer_role_id")
    )

    await interaction.response.send_message(
        "╭───────────────୨୧\n"
        "│ **Joins Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"👋 Channel: "
        f"{welcome_goodbye_channel.mention}\n"
        f"🌸 Customer Role: "
        f"{role.mention if role else 'Not Configured'}",
        ephemeral=True
    )


# =========================================================
# PROOF SETUP
# =========================================================

@bot.tree.command(
    name="setupproof",
    description="Configure the proof submission channel."
)
@app_commands.default_permissions(
    administrator=True
)
async def setupproof(
    interaction: discord.Interaction,
    proof_channel: discord.TextChannel
):

    if not interaction.user.guild_permissions.administrator:

        return await interaction.response.send_message(
            "❌ You need **Administrator** permission.",
            ephemeral=True
        )

    config["proof_channel_id"] = (
        proof_channel.id
    )

    save_config(config)

    await interaction.response.send_message(
        "╭───────────────୨୧\n"
        "│ **Proof Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"📸 Proof Channel: "
        f"{proof_channel.mention}",
        ephemeral=True
    )


# =========================================================
# TICKET PANEL
# =========================================================

@bot.tree.command(
    name="ticketpanel",
    description="Send a ticket panel."
)
async def ticketpanel(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ You need staff permissions.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
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
# PING
# =========================================================

@bot.tree.command(
    name="ping",
    description="Check bot latency."
)
async def ping(
    interaction: discord.Interaction
):

    latency = round(
        bot.latency * 1000
    )

    embed = discord.Embed(
        title="୨୧・𝘱𝘰𝘯𝘨! ♡",
        description=(
            f"🌸 Bot Latency: **{latency}ms**\n"
            "✨ Status: **Online & Operational**"
        ),
        color=PINK
    )

    embed.set_footer(
        text="ali's adm house • Bot Status ♡"
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# PROOF
# =========================================================

@bot.tree.command(
    name="proof",
    description="Submit a proof screenshot."
)
@app_commands.describe(
    image="Proof screenshot",
    description="Optional proof description"
)
async def proof(
    interaction: discord.Interaction,
    image: discord.Attachment,
    description: str = "No description provided"
):

    proof_channel_id = config.get(
        "proof_channel_id"
    )

    proof_channel = (
        interaction.guild.get_channel(
            proof_channel_id
        )
        if proof_channel_id
        and interaction.guild
        else None
    )

    if not proof_channel:

        return await interaction.response.send_message(
            "❌ Proof channel isn't configured.\n"
            "Ask an administrator to use `/setupproof`.",
            ephemeral=True
        )

    if not image.content_type:

        return await interaction.response.send_message(
            "❌ I couldn't determine the file type.",
            ephemeral=True
        )

    if not image.content_type.startswith("image/"):

        return await interaction.response.send_message(
            "❌ Please upload an image file.",
            ephemeral=True
        )

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        image_data = await image.read()

        blurred_data = blur_names(
            image_data
        )

        embed = discord.Embed(
            title="୨୧・𝘯𝘦𝘸 𝘱𝘳𝘰𝘰𝘧 𝘴𝘶𝘣𝘮𝘪𝘴𝘴𝘪𝘰𝘯 ♡",
            description=(
                f"**Submitter:** "
                f"{interaction.user.mention}\n"
                f"**Description:** "
                f"{description}\n\n"
                "Names in the screenshot have "
                "been automatically blurred. ♡"
            ),
            color=PINK
        )

        embed.set_footer(
            text="ali's adm house • Proof Submissions ♡"
        )

        file = discord.File(
            io.BytesIO(blurred_data),
            filename="proof.png"
        )

        await proof_channel.send(
            embed=embed,
            file=file
        )

        await interaction.followup.send(
            "✅ Your proof has been submitted! ♡",
            ephemeral=True
        )

    except Exception as error:

        print(
            f"Proof processing error: {error}"
        )

        await interaction.followup.send(
            "❌ There was an error processing your image.",
            ephemeral=True
        )


# =========================================================
# VOUCH
# =========================================================

async def post_vouch(
    guild: discord.Guild,
    user: discord.abc.User,
    message: str
):

    channel_id = config.get(
        "vouch_channel_id"
    )

    channel = (
        guild.get_channel(channel_id)
        if channel_id
        else None
    )

    if not channel:
        return None

    embed = discord.Embed(
        title="୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡",
        description=(
            f"**{message}**\n\n"
            "୨୧ **𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳**\n"
            f"{user.mention}\n\n"
            "Thank you so much! ♡"
        ),
        color=PINK
    )

    embed.set_author(
        name="୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡"
    )

    embed.set_footer(
        text="୨୧ ali's adm house • Customer Vouch ♡"
    )

    await channel.send(
        content=user.mention,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            users=True
        )
    )

    return channel


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

    if not interaction.guild:

        return await interaction.response.send_message(
            "❌ This command can only be used in a server.",
            ephemeral=True
        )

    channel = await post_vouch(
        interaction.guild,
        interaction.user,
        message
    )

    if not channel:

        return await interaction.response.send_message(
            "❌ The vouch channel hasn't been configured yet.\n"
            "Ask an administrator to use `/setup`.",
            ephemeral=True
        )

    await interaction.response.send_message(
        "♡ Your vouch has been posted! Thank you! ⭐",
        ephemeral=True
    )


# =========================================================
# VOUCH COUNT
# =========================================================

@bot.tree.command(
    name="vouchcount",
    description="Check the total number of vouches."
)
async def vouchcount(
    interaction: discord.Interaction
):

    if not interaction.guild:

        return await interaction.response.send_message(
            "❌ This command can only be used in a server.",
            ephemeral=True
        )

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

    if not channel:

        return await interaction.response.send_message(
            "❌ The vouch channel isn't configured.",
            ephemeral=True
        )

    await interaction.response.defer(
        ephemeral=True
    )

    count = 0

    async for message in channel.history(
        limit=None
    ):

        if message.author == bot.user:
            count += 1

    embed = discord.Embed(
        title="୨୧・𝘰𝘷𝘦𝘳𝘢𝘭𝘭 𝘷𝘰𝘶𝘤𝘩 𝘤𝘰𝘶𝘯𝘵 ♡",
        description=(
            f"**ali's adm house** currently has "
            f"**{count}** total vouch(es)! ⭐\n\n"
            "Thank you to all our amazing customers! ♡"
        ),
        color=PINK
    )

    embed.set_footer(
        text="ali's adm house • Server Statistics ♡"
    )

    await interaction.followup.send(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# STATUS
# =========================================================

@bot.tree.command(
    name="status",
    description="Update shop status."
)
@app_commands.choices(
    state=[
        app_commands.Choice(
            name="Available (Green)",
            value="available"
        ),
        app_commands.Choice(
            name="Busy (Red)",
            value="busy"
        ),
        app_commands.Choice(
            name="Closed (Gray)",
            value="closed"
        )
    ]
)
async def status(
    interaction: discord.Interaction,
    state: app_commands.Choice[str]
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can update the shop status.",
            ephemeral=True
        )

    status_channel_id = config.get(
        "status_channel_id"
    )

    status_channel = (
        interaction.guild.get_channel(
            status_channel_id
        )
        if status_channel_id
        else None
    )

    if not status_channel:

        return await interaction.response.send_message(
            "❌ Status channel isn't configured.\n"
            "Use `/setupstatus` first.",
            ephemeral=True
        )

    if state.value == "available":

        channel_name = "🟢-available"

        title = (
            "🟢・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘢𝘷𝘢𝘪𝘭𝘢𝘣𝘭𝘦"
        )

        desc = (
            "Our shop is currently **OPEN** "
            "for new orders! ♡\n\n"
            "Feel free to open a ticket "
            "to place your order."
        )

        color = GREEN

    elif state.value == "busy":

        channel_name = "🔴-busy"

        title = (
            "🔴・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘣𝘶𝘴𝘺"
        )

        desc = (
            "Our shop is currently **BUSY**! 🎀\n\n"
            "Order fulfillment might take "
            "a little longer than usual, "
            "but tickets are open!"
        )

        color = RED

    else:

        channel_name = "⚪-closed"

        title = (
            "⚪・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘤𝘭𝘰𝘴𝘦𝘥"
        )

        desc = (
            "Our shop is currently **CLOSED**! ♡\n\n"
            "Please check back later "
            "when we reopen!"
        )

        color = GRAY

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color
    )

    embed.set_footer(
        text="ali's adm house • Shop Status ♡"
    )

    await status_channel.send(
        embed=embed
    )

    pending_renames[
        status_channel.id
    ] = channel_name

    await interaction.response.send_message(
        f"♡ Shop status updated to "
        f"**{state.name}** in "
        f"{status_channel.mention}!",
        ephemeral=True
    )


# =========================================================
# SAY / ANNOUNCEMENT
# =========================================================

@bot.tree.command(
    name="say",
    description="Send a styled announcement."
)
@app_commands.describe(
    channel="Channel where the message should be sent",
    message="Message to send",
    role="Optional role to ping"
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

    embed.set_footer(
        text="୨୧ ali's adm house • Announcements ♡"
    )

    content = (
        role.mention
        if role
        else None
    )

    await channel.send(
        content=content,
        embed=embed,
        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )

    await interaction.response.send_message(
        f"♡ Message sent to {channel.mention}.",
        ephemeral=True
    )


# =========================================================
# WARN
# =========================================================

@bot.tree.command(
    name="warn",
    description="Warn a user."
)
@app_commands.describe(
    user="The user to warn",
    reason="Reason for the warning"
)
async def warn(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff members can warn users.",
            ephemeral=True
        )

    allowed, error = can_moderate(
        interaction,
        user
    )

    if not allowed:

        return await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True
        )

    embed = discord.Embed(
        title="⚠️ You have been warned",
        description=f"**Reason:** {reason}",
        color=RED
    )

    embed.set_footer(
        text="ali's adm house • Moderation ♡"
    )

    try:
        await user.send(
            embed=embed
        )
    except discord.Forbidden:
        pass

    await interaction.response.send_message(
        f"⚠️ Warned {user.mention} for: "
        f"**{reason}**",
        ephemeral=True
    )


# =========================================================
# CLEAR
# =========================================================

@bot.tree.command(
    name="clear",
    description="Delete messages."
)
@app_commands.describe(
    amount="Number of messages to delete (1-100)"
)
async def clear(
    interaction: discord.Interaction,
    amount: int
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can delete messages.",
            ephemeral=True
        )

    if not 1 <= amount <= 100:

        return await interaction.response.send_message(
            "❌ Amount must be between 1 and 100.",
            ephemeral=True
        )

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):

        return await interaction.response.send_message(
            "❌ This command must be used in a text channel.",
            ephemeral=True
        )

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        deleted = await interaction.channel.purge(
            limit=amount
        )

        await interaction.followup.send(
            f"🗑️ Deleted **{len(deleted)}** message(s).",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.followup.send(
            "❌ I don't have permission to delete messages.",
            ephemeral=True
        )


# =========================================================
# GIVE ROLE
# =========================================================

@bot.tree.command(
    name="giverole",
    description="Give a role to a user."
)
async def giverole(
    interaction: discord.Interaction,
    user: discord.Member,
    role: discord.Role
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can give roles.",
            ephemeral=True
        )

    if role.is_default():

        return await interaction.response.send_message(
            "❌ You cannot give the @everyone role.",
            ephemeral=True
        )

    if (
        interaction.guild.me
        and role >= interaction.guild.me.top_role
    ):

        return await interaction.response.send_message(
            "❌ That role is higher than or equal to my highest role.",
            ephemeral=True
        )

    if (
        interaction.user.id
        != interaction.guild.owner_id
        and role >= interaction.user.top_role
    ):

        return await interaction.response.send_message(
            "❌ You cannot give a role equal to or higher than your highest role.",
            ephemeral=True
        )

    try:

        await user.add_roles(
            role,
            reason=f"Role given by {interaction.user}"
        )

        await interaction.response.send_message(
            f"✅ Gave {user.mention} "
            f"the {role.mention} role!",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ I don't have permission to give that role.",
            ephemeral=True
        )


# =========================================================
# MUTE
# =========================================================

@bot.tree.command(
    name="mute",
    description="Timeout a user for 10 minutes."
)
@app_commands.describe(
    user="The user to mute",
    reason="Reason for muting"
)
async def mute(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can mute users.",
            ephemeral=True
        )

    allowed, error = can_moderate(
        interaction,
        user
    )

    if not allowed:

        return await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True
        )

    try:

        until = (
            discord.utils.utcnow()
            + datetime.timedelta(minutes=10)
        )

        await user.timeout(
            until,
            reason=reason
        )

        await interaction.response.send_message(
            f"🔇 Muted {user.mention} for "
            f"**10 minutes**.\n"
            f"Reason: **{reason}**",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ I don't have permission to timeout that user.",
            ephemeral=True
        )


# =========================================================
# BAN
# =========================================================

@bot.tree.command(
    name="ban",
    description="Ban a user."
)
@app_commands.describe(
    user="The user to ban",
    reason="Reason for banning"
)
async def ban(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can ban users.",
            ephemeral=True
        )

    allowed, error = can_moderate(
        interaction,
        user
    )

    if not allowed:

        return await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True
        )

    try:

        await user.send(
            f"🚫 You have been banned from "
            f"**{interaction.guild.name}**.\n"
            f"Reason: **{reason}**"
        )

    except discord.Forbidden:
        pass

    try:

        await interaction.guild.ban(
            user,
            reason=reason,
            delete_message_seconds=0
        )

        await interaction.response.send_message(
            f"🚫 Banned {user.mention}.\n"
            f"Reason: **{reason}**",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ I don't have permission to ban that user.",
            ephemeral=True
        )


# =========================================================
# KICK
# =========================================================

@bot.tree.command(
    name="kick",
    description="Kick a user."
)
@app_commands.describe(
    user="The user to kick",
    reason="Reason for kicking"
)
async def kick(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can kick users.",
            ephemeral=True
        )

    allowed, error = can_moderate(
        interaction,
        user
    )

    if not allowed:

        return await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True
        )

    try:

        await user.send(
            f"👢 You have been kicked from "
            f"**{interaction.guild.name}**.\n"
            f"Reason: **{reason}**"
        )

    except discord.Forbidden:
        pass

    try:

        await user.kick(
            reason=reason
        )

        await interaction.response.send_message(
            f"👢 Kicked {user.mention}.\n"
            f"Reason: **{reason}**",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ I don't have permission to kick that user.",
            ephemeral=True
        )


# =========================================================
# LOCK CHANNEL
# =========================================================

@bot.tree.command(
    name="lockchannel",
    description="Lock a channel."
)
@app_commands.describe(
    channel="Channel to lock",
    reason="Reason for locking"
)
async def lockchannel(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can lock channels.",
            ephemeral=True
        )

    target = (
        channel
        or interaction.channel
    )

    if not isinstance(
        target,
        discord.TextChannel
    ):

        return await interaction.response.send_message(
            "❌ Invalid channel.",
            ephemeral=True
        )

    try:

        await target.set_permissions(
            interaction.guild.default_role,
            send_messages=False,
            reason=reason
        )

        await interaction.response.send_message(
            f"🔒 Locked {target.mention}.\n"
            f"Reason: **{reason}**",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ I don't have permission to lock that channel.",
            ephemeral=True
        )


# =========================================================
# UNLOCK CHANNEL
# =========================================================

@bot.tree.command(
    name="unlockchannel",
    description="Unlock a channel."
)
@app_commands.describe(
    channel="Channel to unlock",
    reason="Reason for unlocking"
)
async def unlockchannel(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        return await interaction.response.send_message(
            "❌ Only staff can unlock channels.",
            ephemeral=True
        )

    target = (
        channel
        or interaction.channel
    )

    if not isinstance(
        target,
        discord.TextChannel
    ):

        return await interaction.response.send_message(
            "❌ Invalid channel.",
            ephemeral=True
        )

    try:

        await target.set_permissions(
            interaction.guild.default_role,
            send_messages=None,
            reason=reason
        )

        await interaction.response.send_message(
            f"🔓 Unlocked {target.mention}.\n"
            f"Reason: **{reason}**",
            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            "❌ I don't have permission to unlock that channel.",
            ephemeral=True
        )


# =========================================================
# PREFIX VOUCH
# =========================================================

@bot.command(
    name="vouch"
)
async def vouch_prefix(
    ctx,
    *,
    message: str = None
):

    if not message:

        return await ctx.send(
            "❌ Please include a message!\n"
            "Example: `!vouch Great service!`",
            delete_after=10
        )

    if not ctx.guild:

        return

    channel = await post_vouch(
        ctx.guild,
        ctx.author,
        message
    )

    if not channel:

        return await ctx.send(
            "❌ The vouch channel hasn't been configured yet."
        )

    try:

        await ctx.message.delete()

    except discord.Forbidden:
        pass

    await ctx.send(
        f"♡ Thank you {ctx.author.mention}, "
        "your vouch has been posted! ⭐",
        delete_after=5
    )


# =========================================================
# PREFIX ERROR HANDLER
# =========================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    print(
        f"Prefix command error: {error}"
    )


# =========================================================
# GLOBAL ERROR HANDLER
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    print(
        f"Slash command error: {error}"
    )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                "❌ Something went wrong while running this command.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "❌ Something went wrong while running this command.",
                ephemeral=True
            )

    except discord.HTTPException:
        pass


# =========================================================
# RUN
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN environment variable is not set."
    )


keep_alive()

bot.run(TOKEN)
```

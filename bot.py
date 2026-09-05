import os
import json
import asyncio
import discord
import io
from PIL import Image, ImageFilter

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
    "welcome_goodbye_channel_id": int(os.getenv("WELCOME_GOODBYE_CHANNEL_ID", 0)) or None,
    "proof_channel_id": int(os.getenv("PROOF_CHANNEL_ID", 0)) or None,
    "staff_role_id": int(os.getenv("STAFF_ROLE_ID", 0)) or None,
    "customer_role_id": int(os.getenv("CUSTOMER_ROLE_ID", 1545438540362555463)) or 1545438540362555463
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
# IMAGE BLUR HELPER
# =========================================================

def blur_names(image_data: bytes) -> bytes:
    """Blur the top portion of an image where usernames typically appear."""
    try:
        # Open image from bytes
        img = Image.open(io.BytesIO(image_data)).convert("RGB")
        
        # Get image dimensions
        width, height = img.size
        
        # Blur the top 15% of the image (where usernames appear in screenshots)
        blur_height = int(height * 0.15)
        
        # Create a blurred copy of the top portion
        top_portion = img.crop((0, 0, width, blur_height))
        blurred_portion = top_portion.filter(ImageFilter.GaussianBlur(radius=15))
        
        # Paste the blurred portion back
        img.paste(blurred_portion, (0, 0))
        
        # Save to bytes
        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output.getvalue()
    
    except Exception as e:
        print(f"Error blurring image: {e}")
        return image_data


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
# BACKGROUND CHANNEL RENAME QUEUE
# =========================================================

pending_renames = {}

async def process_channel_renames():
    """Background loop that updates channel names as fast as Discord allows."""
    while True:
        if pending_renames:
            channel_id, new_name = list(pending_renames.items())[0]
            del pending_renames[channel_id]

            channel = bot.get_channel(channel_id)
            if channel and channel.name != new_name:
                try:
                    await channel.edit(name=new_name)
                    print(f"Successfully renamed channel {channel.id} to {new_name}")
                except discord.HTTPException as e:
                    if e.status == 429: # Rate limited by Discord
                        retry_after = getattr(e, 'retry_after', 300)
                        print(f"Rate limited on channel rename. Retrying in {retry_after}s...")
                        pending_renames[channel_id] = new_name
                        await asyncio.sleep(retry_after)
                except Exception as e:
                    print(f"Error renaming channel: {e}")

        await asyncio.sleep(5)


# =========================================================
# WELCOME & GOODBYE EVENTS (DECORATED EMBEDS)
# =========================================================

@bot.event
async def on_member_join(member: discord.Member):
    # Auto-assign customer role
    customer_role_id = config.get("customer_role_id")
    if customer_role_id:
        role = member.guild.get_role(customer_role_id)
        if role:
            try:
                await member.add_roles(role, reason="Automatic customer role on join")
            except discord.Forbidden:
                print(f"Failed to add role {role.name} to {member.name}: Lacks permissions.")
            except Exception as e:
                print(f"Error assigning customer role: {e}")

    # Send Welcome Message
    channel_id = config.get("welcome_goodbye_channel_id")
    if not channel_id:
        return

    channel = member.guild.get_channel(channel_id)
    if not channel:
        return

    # Highly Decorated Welcome Embed
    embed = discord.Embed(
        title="╭───────────── ୨୧ ─────────────╮\n       🌸˚₊ 𝘸𝘦𝘭𝘤𝘰𝘮𝘦 𝘵𝘰 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦! ♡\n╰───────────── ୨୧ ─────────────╯",
        description=(
            f" Welcome {member.mention}! We are so thrilled to have you join our community! ♡\n\n"
            "✦ **Getting Started:**\n"
            " Check out our products and shop listings!\n"
            " Open a support ticket to place custom orders or ask questions!\n"
            " Feel free to hang out and chat with our lovely members!\n\n"
            "─────────────── ୨୧ ───────────────"
        ),
        color=PINK
    )
    
    # User Profile Thumbnail & Custom Banner Image
    embed.set_thumbnail(url=member.display_avatar.url)
    
    # Dedicated Info Fields
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
    
    # Soft aesthetic anime/pink divider GIF (Replace URL with any banner image link if desired)
    embed.set_image(url="https://media.tenor.com/264pYc0nE40AAAAC/anime-aesthetic.gif")
    embed.set_footer(
        text="ali's adm house • Customer Shop ♡",
        icon_url=member.guild.icon.url if member.guild.icon else None
    )

    await channel.send(
        content=f"👋 Welcome to the server {member.mention}! ♡",
        embed=embed,
        allowed_mentions=discord.AllowedMentions(users=[member])
    )


@bot.event
async def on_member_remove(member: discord.Member):
    channel_id = config.get("welcome_goodbye_channel_id")
    if not channel_id:
        return

    channel = member.guild.get_channel(channel_id)
    if not channel:
        return

    # Highly Decorated Goodbye Embed
    embed = discord.Embed(
        title="╭───────────── ୨୧ ─────────────╮\n            💔˚₊ 𝘨𝘰𝘰𝘥𝘣𝘺𝘦, 𝘴𝘦𝘦 𝘺𝘰𝘶 𝘴𝘰𝘰𝘯! ♡\n╰───────────── ୨୧ ─────────────╯",
        description=(
            f"**{member.name}** has left **ali's adm house**... 💔\n\n"
            "We're sad to see you leave, but we hope to see you back again soon! ♡\n\n"
            "─────────────── ୨୧ ───────────────"
        ),
        color=GRAY
    )
    
    embed.set_thumbnail(url=member.display_avatar.url)
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
    
    # Cute goodbye banner image
    embed.set_image(url="https://media.tenor.com/E694tZ914x8AAAAC/anime-sad.gif")
    embed.set_footer(
        text="ali's adm house • Member Departure ♡",
        icon_url=member.guild.icon.url if member.guild.icon else None
    )

    await channel.send(embed=embed)


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
                "୨୧ **Build type:**\n\n"
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

    # Start background loop for renaming channels to avoid rate limits
    if not hasattr(bot, "_rename_task"):
        bot._rename_task = bot.loop.create_task(process_channel_renames())

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
# SLASH COMMANDS - SETUP
# =========================================================

@bot.tree.command(
    name="setup",
    description="Configure only the ticket system."
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    panel_channel="Channel where the ticket panel will be sent",
    ticket_category="Category where new tickets will be created",
    staff_role="Staff role allowed to manage tickets and /say",
    vouch_channel="Optional channel where /vouch messages are posted"
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
            "❌ You need **Administrator** permission to use `/setup`.",
            ephemeral=True
        )

    config["panel_channel_id"] = panel_channel.id
    config["ticket_category_id"] = ticket_category.id
    config["staff_role_id"] = staff_role.id if staff_role else None
    if vouch_channel:
        config["vouch_channel_id"] = vouch_channel.id

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
        "│ **Ticket Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"🎫 Panel: {panel_channel.mention}\n"
        f"📁 Ticket Category: **{ticket_category.name}**\n"
        f"👥 Staff Role: {staff_role.mention if staff_role else 'Manage Channels'}\n"
        f"⭐ Vouches: {vouch_channel.mention if vouch_channel else 'Not Updated'}",
        ephemeral=True
    )


@bot.tree.command(
    name="setupstatus",
    description="Configure only the shop status channel."
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    status_channel="Channel where order status updates will be posted"
)
async def setupstatus(
    interaction: discord.Interaction,
    status_channel: discord.TextChannel
):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ You need **Administrator** permission to use `/setupstatus`.",
            ephemeral=True
        )

    config["status_channel_id"] = status_channel.id
    save_config(config)

    await interaction.response.send_message(
        "╭───────────────୨୧\n"
        "│ **Status Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"📊 Status Channel: {status_channel.mention}",
        ephemeral=True
    )


@bot.tree.command(
    name="setupjoins",
    description="Configure only the welcome, goodbye, and auto-customer role system."
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    welcome_goodbye_channel="Channel where welcome and goodbye messages are sent",
    customer_role="Role automatically given to members upon joining"
)
async def setupjoins(
    interaction: discord.Interaction,
    welcome_goodbye_channel: discord.TextChannel,
    customer_role: discord.Role | None = None
):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ You need **Administrator** permission to use `/setupjoins`.",
            ephemeral=True
        )

    config["welcome_goodbye_channel_id"] = welcome_goodbye_channel.id
    if customer_role:
        config["customer_role_id"] = customer_role.id

    save_config(config)

    cust_role = interaction.guild.get_role(config.get("customer_role_id"))

    await interaction.response.send_message(
        "╭───────────────୨୧\n"
        "│ **Joins Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"👋 Welcome/Goodbye Channel: {welcome_goodbye_channel.mention}\n"
        f"🌸 Auto Customer Role: {cust_role.mention if cust_role else 'Not Configured'}",
        ephemeral=True
    )


@bot.tree.command(
    name="setupproof",
    description="Configure only the proof submission channel."
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    proof_channel="Channel where proof submissions will be posted"
)
async def setupproof(
    interaction: discord.Interaction,
    proof_channel: discord.TextChannel
):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ You need **Administrator** permission to use `/setupproof`.",
            ephemeral=True
        )

    config["proof_channel_id"] = proof_channel.id
    save_config(config)

    await interaction.response.send_message(
        "╭───────────────୨୧\n"
        "│ **Proof Setup Complete! ♡**\n"
        "╰───────────────୨୧\n\n"
        f"📸 Proof Channel: {proof_channel.mention}",
        ephemeral=True
    )


# =========================================================
# SLASH COMMANDS - UTILITY
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
    name="proof",
    description="Submit a proof screenshot with names automatically blurred."
)
@app_commands.describe(
    image="Screenshot/proof image (names in top area will be blurred)",
    description="Optional description of the proof"
)
async def proof(
    interaction: discord.Interaction,
    image: discord.Attachment,
    description: str = "No description provided"
):

    proof_channel_id = config.get("proof_channel_id")
    proof_channel = (
        interaction.guild.get_channel(proof_channel_id)
        if proof_channel_id and interaction.guild
        else None
    )

    if proof_channel is None:
        return await interaction.response.send_message(
            "❌ The proof channel hasn't been configured yet.\n\nAsk an administrator to use `/setupproof`.",
            ephemeral=True
        )

    # Check if it's an image
    if not image.content_type.startswith("image/"):
        return await interaction.response.send_message(
            "❌ Please upload an image file!",
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    try:
        # Download image
        image_data = await image.read()
        
        # Blur names
        blurred_data = blur_names(image_data)
        
        # Create embed
        embed = discord.Embed(
            title="୨୧・𝘯𝘦𝘸 𝘱𝘳𝘰𝘰𝘧 𝘴𝘶𝘣𝘮𝘪𝘴𝘴𝘪𝘰𝘯 ♡",
            description=(
                f"**Submitter:** {interaction.user.mention}\n"
                f"**Description:** {description}\n\n"
                "Names in the screenshot have been automatically blurred for privacy. ♡"
            ),
            color=PINK
        )
        embed.set_footer(text="ali's adm house • Proof Submissions ♡")
        
        # Send to proof channel with blurred image
        await proof_channel.send(
            embed=embed,
            file=discord.File(
                io.BytesIO(blurred_data),
                filename="proof.png"
            )
        )
        
        await interaction.followup.send(
            "✅ Your proof has been submitted! Names have been blurred for privacy. ♡",
            ephemeral=True
        )
    
    except Exception as e:
        print(f"Error processing proof: {e}")
        await interaction.followup.send(
            "❌ There was an error processing your image. Please try again.",
            ephemeral=True
        )


# =========================================================
# SLASH COMMANDS - VOUCH
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
    description="Check the total overall number of vouches in the server."
)
async def vouchcount(interaction: discord.Interaction):
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
    async for message in vouch_channel.history(limit=None):
        if message.author == bot.user:
            count += 1

    embed = discord.Embed(
        title="୨୧・𝘰𝘷𝘦𝘳𝘢𝘭𝘭 𝘷𝘰𝘶𝘤𝘩 𝘤𝘰𝘶𝘯𝘵 ♡",
        description=(
            f"**ali's adm house** currently has **{count}** total vouch(es)! ⭐\n\n"
            "Thank you to all our amazing customers! ♡"
        ),
        color=PINK
    )
    embed.set_footer(text="ali's adm house • Server Statistics ♡")

    await interaction.followup.send(embed=embed, ephemeral=True)


# =========================================================
# SLASH COMMANDS - SHOP STATUS
# =========================================================

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
            "❌ Status channel not configured! Use `/setupstatus` first.",
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

    # Queue the channel rename through the background processor
    pending_renames[status_channel.id] = channel_name


# =========================================================
# SLASH COMMANDS - ANNOUNCEMENTS
# =========================================================

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
# SLASH COMMANDS - MODERATION
# =========================================================

@bot.tree.command(
    name="warn",
    description="Warn a user with a reason."
)
@app_commands.describe(
    user="The user to warn",
    reason="Reason for the warning"
)
async def warn(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff members can warn users.",
            ephemeral=True
        )

    if user.id == interaction.user.id:
        return await interaction.response.send_message(
            "❌ You cannot warn yourself!",
            ephemeral=True
        )

    embed = discord.Embed(
        title="⚠️ You have been warned",
        description=f"**Reason:** {reason}",
        color=RED
    )
    embed.set_footer(text="ali's adm house • Moderation ♡")

    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass

    await interaction.response.send_message(
        f"⚠️ Warned {user.mention} for: **{reason}**",
        ephemeral=True
    )


@bot.tree.command(
    name="clear",
    description="Delete a specified number of messages."
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
            "❌ Only staff members can delete messages.",
            ephemeral=True
        )

    if amount < 1 or amount > 100:
        return await interaction.response.send_message(
            "❌ Please specify a number between 1 and 100.",
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    deleted = await interaction.channel.purge(limit=amount)

    await interaction.followup.send(
        f"🗑️ Deleted **{len(deleted)}** message(s).",
        ephemeral=True
    )


@bot.tree.command(
    name="giverole",
    description="Give a role to a user."
)
@app_commands.describe(
    user="The user to give the role to",
    role="The role to give"
)
async def giverole(
    interaction: discord.Interaction,
    user: discord.User,
    role: discord.Role
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff members can give roles.",
            ephemeral=True
        )

    member = interaction.guild.get_member(user.id)
    if not member:
        return await interaction.response.send_message(
            "❌ That user is not in this server.",
            ephemeral=True
        )

    try:
        await member.add_roles(role)
        await interaction.response.send_message(
            f"✅ Gave {member.mention} the {role.mention} role!",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to give that role.",
            ephemeral=True
        )


@bot.tree.command(
    name="mute",
    description="Mute a user."
)
@app_commands.describe(
    user="The user to mute",
    reason="Reason for muting"
)
async def mute(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff members can mute users.",
            ephemeral=True
        )

    member = interaction.guild.get_member(user.id)
    if not member:
        return await interaction.response.send_message(
            "❌ That user is not in this server.",
            ephemeral=True
        )

    if user.id == interaction.user.id:
        return await interaction.response.send_message(
            "❌ You cannot mute yourself!",
            ephemeral=True
        )

    try:
        await member.timeout(discord.utils.utcnow() + discord.utils.datetime.timedelta(minutes=10), reason=reason)
        await interaction.response.send_message(
            f"🔇 Muted {member.mention} for: **{reason}**",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to mute that user.",
            ephemeral=True
        )


@bot.tree.command(
    name="ban",
    description="Ban a user from the server."
)
@app_commands.describe(
    user="The user to ban",
    reason="Reason for banning"
)
async def ban(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff members can ban users.",
            ephemeral=True
        )

    if user.id == interaction.user.id:
        return await interaction.response.send_message(
            "❌ You cannot ban yourself!",
            ephemeral=True
        )

    try:
        await interaction.guild.ban(user, reason=reason)
        await interaction.response.send_message(
            f"🚫 Banned {user.mention} for: **{reason}**",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to ban that user.",
            ephemeral=True
        )


@bot.tree.command(
    name="kick",
    description="Kick a user from the server."
)
@app_commands.describe(
    user="The user to kick",
    reason="Reason for kicking"
)
async def kick(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff members can kick users.",
            ephemeral=True
        )

    member = interaction.guild.get_member(user.id)
    if not member:
        return await interaction.response.send_message(
            "❌ That user is not in this server.",
            ephemeral=True
        )

    if user.id == interaction.user.id:
        return await interaction.response.send_message(
            "❌ You cannot kick yourself!",
            ephemeral=True
        )

    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(
            f"👢 Kicked {member.mention} for: **{reason}**",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to kick that user.",
            ephemeral=True
        )


@bot.tree.command(
    name="lockchannel",
    description="Lock a channel to prevent messages."
)
@app_commands.describe(
    channel="The channel to lock (defaults to current channel)",
    reason="Reason for locking"
)
async def lockchannel(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff members can lock channels.",
            ephemeral=True
        )

    target_channel = channel or interaction.channel

    try:
        await target_channel.set_permissions(
            interaction.guild.default_role,
            send_messages=False,
            reason=reason
        )
        await interaction.response.send_message(
            f"🔒 Locked {target_channel.mention} for: **{reason}**",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to lock that channel.",
            ephemeral=True
        )


@bot.tree.command(
    name="unlockchannel",
    description="Unlock a channel to allow messages again."
)
@app_commands.describe(
    channel="The channel to unlock (defaults to current channel)",
    reason="Reason for unlocking"
)
async def unlockchannel(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):
        return await interaction.response.send_message(
            "❌ Only staff members can unlock channels.",
            ephemeral=True
        )

    target_channel = channel or interaction.channel

    try:
        await target_channel.set_permissions(
            interaction.guild.default_role,
            send_messages=True,
            reason=reason
        )
        await interaction.response.send_message(
            f"🔓 Unlocked {target_channel.mention} for: **{reason}**",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to unlock that channel.",
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

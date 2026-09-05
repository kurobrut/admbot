import os
import json
import io
import asyncio
from datetime import timedelta
from threading import Thread

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from PIL import Image, ImageFilter

import cv2
import numpy as np
import pytesseract


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

    print(
        f"Keep-alive web server started on port "
        f"{os.environ.get('PORT', '8080')}"
    )


# =========================================================
# CONFIG
# =========================================================

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "panel_channel_id": int(
        os.getenv("PANEL_CHANNEL_ID", 0)
    ) or None,

    "ticket_category_id": int(
        os.getenv("TICKET_CATEGORY_ID", 0)
    ) or None,

    "vouch_channel_id": int(
        os.getenv("VOUCH_CHANNEL_ID", 0)
    ) or None,

    "status_channel_id": int(
        os.getenv("STATUS_CHANNEL_ID", 0)
    ) or None,

    "welcome_goodbye_channel_id": int(
        os.getenv("WELCOME_GOODBYE_CHANNEL_ID", 0)
    ) or None,

    "proof_channel_id": int(
        os.getenv("PROOF_CHANNEL_ID", 0)
    ) or None,

    "staff_role_id": int(
        os.getenv("STAFF_ROLE_ID", 0)
    ) or None,

    "customer_role_id": int(
        os.getenv(
            "CUSTOMER_ROLE_ID",
            1545438540362555463
        )
    ) or 1545438540362555463,
    
    "blur_everything": bool(
        os.getenv("BLUR_EVERYTHING", "true").lower() == "true"
    )
}


def save_config(data):
    try:
        with open(
            CONFIG_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=2
            )

    except OSError as error:

        print(
            f"Could not save config: {error}"
        )


def load_config():

    if not os.path.exists(CONFIG_FILE):

        save_config(
            DEFAULT_CONFIG.copy()
        )

        return DEFAULT_CONFIG.copy()

    try:

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        changed = False

        for key, value in DEFAULT_CONFIG.items():

            if key not in data:

                data[key] = value
                changed = True

        if changed:
            save_config(data)

        return data

    except (
        json.JSONDecodeError,
        OSError
    ):

        save_config(
            DEFAULT_CONFIG.copy()
        )

        return DEFAULT_CONFIG.copy()


config = load_config()


# =========================================================
# DISCORD INTENTS
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

GREEN = discord.Color.from_rgb(
    87,
    242,
    135
)

RED = discord.Color.from_rgb(
    237,
    66,
    69
)

GRAY = discord.Color.from_rgb(
    149,
    165,
    166
)


# =========================================================
# EMBED HELPER
# =========================================================

def styled_embed(
    title,
    description,
    color=PINK
):

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
# ADVANCED PROOF TEXT BLUR - BLUR EVERYTHING
# =========================================================

def blur_region(
    image,
    x1,
    y1,
    x2,
    y2,
    radius=20
):
    """
    Blur one individual region without creating
    a giant rectangular blur across the screenshot.
    """

    width, height = image.size

    x1 = max(0, min(width, int(x1)))
    y1 = max(0, min(height, int(y1)))
    x2 = max(0, min(width, int(x2)))
    y2 = max(0, min(height, int(y2)))

    if x2 <= x1 or y2 <= y1:
        return

    crop = image.crop((x1, y1, x2, y2))
    crop = crop.filter(ImageFilter.GaussianBlur(radius=radius))

    image.paste(crop, (x1, y1))


def is_very_short_text(text):
    """Skip single characters or very short fragments"""
    return len(text.strip()) < 2


def blur_proof_text(
    image_data: bytes,
    blur_everything: bool = True
) -> bytes:
    """
    Scans the screenshot using OCR and blurs ALL text regions.
    
    FEATURES:
    - Blurs EVERYTHING by default (usernames, dates, times, all text)
    - OR use smart filters to skip certain patterns
    - Configurable behavior
    """

    try:
        print("[PROOF] Starting blur processing...")
        print(f"[PROOF] Blur mode: {'EVERYTHING' if blur_everything else 'SMART FILTERS'}")

        # =================================================
        # LOAD IMAGE
        # =================================================

        original = Image.open(
            io.BytesIO(image_data)
        ).convert("RGB")

        width, height = original.size
        print(f"[PROOF] Image size: {width}x{height}")

        # OpenCV image for processing
        cv_image = cv2.cvtColor(
            np.array(original),
            cv2.COLOR_RGB2BGR
        )

        gray = cv2.cvtColor(
            cv_image,
            cv2.COLOR_BGR2GRAY
        )

        # =================================================
        # UPSCALE FOR BETTER OCR
        # =================================================

        scale = 2

        enlarged = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

        # Apply preprocessing
        enlarged = cv2.GaussianBlur(enlarged, (3, 3), 0)
        _, enlarged = cv2.threshold(
            enlarged,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # =================================================
        # OCR - WITH ERROR HANDLING
        # =================================================

        try:
            print("[PROOF] Running Tesseract OCR...")

            ocr_data = pytesseract.image_to_data(
                enlarged,
                config="--oem 3 --psm 6",
                output_type=pytesseract.Output.DICT
            )

            print(f"[PROOF] OCR detected {len(ocr_data['text'])} text regions")

        except Exception as e:
            print(f"[PROOF] ⚠️ Tesseract error: {e}")
            print("[PROOF] Attempting fallback OCR...")

            try:
                ocr_data = pytesseract.image_to_data(
                    enlarged,
                    config="--oem 1 --psm 11",
                    output_type=pytesseract.Output.DICT
                )
                print(f"[PROOF] Fallback OCR detected {len(ocr_data['text'])} regions")
            except Exception as e2:
                print(f"[PROOF] ❌ Fallback also failed: {e2}")
                return image_data

        # =================================================
        # OUTPUT IMAGE
        # =================================================

        result = original.copy()

        # =================================================
        # COLLECT AND BLUR REGIONS
        # =================================================

        regions = []
        total_words = len(ocr_data["text"])

        for i in range(total_words):

            text = ocr_data["text"][i].strip()

            if not text:
                continue

            if is_very_short_text(text):
                continue

            try:
                confidence = float(ocr_data["conf"][i])
            except (ValueError, TypeError):
                confidence = 0

            # Lowered threshold to catch more text
            if confidence < 8:
                continue

            # Scale coordinates back to original image size
            x = int(ocr_data["left"][i] / scale)
            y = int(ocr_data["top"][i] / scale)
            w = int(ocr_data["width"][i] / scale)
            h = int(ocr_data["height"][i] / scale)

            if w < 2 or h < 2:
                continue

            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(width, x + w)
            y2 = min(height, y + h)

            if x2 <= x1 or y2 <= y1:
                continue

            regions.append({
                "text": text,
                "confidence": confidence,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": x2 - x1,
                "height": y2 - y1
            })

        print(f"[PROOF] Found {len(regions)} candidate regions to evaluate")

        # =================================================
        # PROCESS EACH REGION
        # =================================================

        blur_count = 0

        for region in regions:

            text = region["text"]
            x1 = region["x1"]
            y1 = region["y1"]
            x2 = region["x2"]
            y2 = region["y2"]
            region_height = region["height"]
            region_width = region["width"]

            # Skip very small text (less than 5px tall)
            if region_height < 5:
                continue

            # =============================================
            # BLUR EVERYTHING MODE (DEFAULT)
            # =============================================
            if blur_everything:
                
                # In blur everything mode:
                # - Blur text that is at least 5px tall with any confidence
                
                if region_height >= 5 and region["confidence"] >= 8:
                    
                    # Add padding around the text
                    pad_x = max(2, int(region_width * 0.12))
                    pad_y = max(2, int(region_height * 0.25))

                    bx1 = max(0, x1 - pad_x)
                    by1 = max(0, y1 - pad_y)
                    bx2 = min(width, x2 + pad_x)
                    by2 = min(height, y2 + pad_y)

                    # STRONG blur
                    blur_region(
                        result,
                        bx1,
                        by1,
                        bx2,
                        by2,
                        radius=25
                    )

                    blur_count += 1

                    print(
                        f"[PROOF] ✓ Blurred: {text!r} "
                        f"(conf={region['confidence']:.1f}, h={region_height}px)"
                    )

            # =============================================
            # SMART FILTER MODE
            # =============================================
            else:
                
                # Skip button text
                if text.lower().strip() in {
                    "view", "report", "refresh", "buy",
                    "cancel", "confirm", "close", "ok", "yes", "no"
                }:
                    continue

                # Only blur text >= 8px with good confidence
                if region_height >= 8 and region["confidence"] >= 15:
                    
                    pad_x = max(2, int(region_width * 0.1))
                    pad_y = max(2, int(region_height * 0.2))

                    bx1 = max(0, x1 - pad_x)
                    by1 = max(0, y1 - pad_y)
                    bx2 = min(width, x2 + pad_x)
                    by2 = min(height, y2 + pad_y)

                    blur_region(
                        result,
                        bx1,
                        by1,
                        bx2,
                        by2,
                        radius=20
                    )

                    blur_count += 1

                    print(
                        f"[PROOF] ✓ Blurred: {text!r} "
                        f"(conf={region['confidence']:.1f}, h={region_height}px)"
                    )

        print(f"[PROOF] ✅ Total blurred: {blur_count} regions")

        # =================================================
        # SAVE & RETURN
        # =================================================

        output = io.BytesIO()
        result.save(output, format="PNG")
        output.seek(0)

        return output.getvalue()

    except Exception as error:
        print(f"[PROOF] ❌ Critical error: {error}")
        import traceback
        traceback.print_exc()
        return image_data


# =========================================================
# STAFF CHECK
# =========================================================

def is_staff(
    interaction: discord.Interaction
):

    if interaction.guild is None:
        return False

    if interaction.user.guild_permissions.administrator:
        return True

    staff_role_id = config.get(
        "staff_role_id"
    )

    if staff_role_id:

        return any(
            role.id == staff_role_id
            for role in getattr(
                interaction.user,
                "roles",
                []
            )
        )

    return interaction.user.guild_permissions.manage_channels


# =========================================================
# CHANNEL RENAME QUEUE
# =========================================================

pending_renames = {}


async def process_channel_renames():

    while True:

        if pending_renames:

            channel_id, new_name = next(
                iter(
                    pending_renames.items()
                )
            )

            del pending_renames[
                channel_id
            ]

            channel = bot.get_channel(
                channel_id
            )

            if (
                channel
                and channel.name != new_name
            ):

                try:

                    await channel.edit(
                        name=new_name
                    )

                except discord.HTTPException as error:

                    if error.status == 429:

                        retry_after = getattr(
                            error,
                            "retry_after",
                            60
                        )

                        pending_renames[
                            channel_id
                        ] = new_name

                        await asyncio.sleep(
                            retry_after
                        )

                    else:

                        print(
                            f"Channel rename error: "
                            f"{error}"
                        )

                except Exception as error:

                    print(
                        f"Channel rename error: "
                        f"{error}"
                    )

        await asyncio.sleep(5)


# =========================================================
# MEMBER JOIN
# =========================================================

@bot.event
async def on_member_join(
    member: discord.Member
):

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
                    reason=(
                        "Automatic customer "
                        "role on join"
                    )
                )

            except discord.Forbidden:

                print(
                    f"Cannot give {role.name} "
                    f"to {member}"
                )

            except Exception as error:

                print(
                    f"Role assignment error: "
                    f"{error}"
                )

    channel_id = config.get(
        "welcome_goodbye_channel_id"
    )

    if not channel_id:
        return

    channel = member.guild.get_channel(
        channel_id
    )

    if not isinstance(
        channel,
        discord.TextChannel
    ):
        return

    embed = discord.Embed(

        title=(
            "╭───────────── ୨୧ ─────────────╮\n"
            "       🌸˚₊ 𝘸𝘦𝘭𝘤𝘰𝘮𝘦 𝘵𝘰 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦! ♡\n"
            "╰───────────── ୨୧ ─────────────╯"
        ),

        description=(
            f"Welcome {member.mention}! "
            "We are so thrilled to have you "
            "join our community! ♡\n\n"

            "✦ **Getting Started:**\n"
            "Check out our products and shop listings!\n"
            "Open a support ticket to place custom "
            "orders or ask questions!\n"
            "Feel free to hang out and chat with "
            "our lovely members!\n\n"

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
        value=(
            f"• `#{member.guild.member_count}`"
        ),
        inline=True
    )

    await channel.send(

        content=(
            f"👋 Welcome to the server "
            f"{member.mention}! ♡"
        ),

        embed=embed,

        allowed_mentions=discord.AllowedMentions(
            users=[member]
        )
    )


# =========================================================
# MEMBER LEAVE
# =========================================================

@bot.event
async def on_member_remove(
    member: discord.Member
):

    channel_id = config.get(
        "welcome_goodbye_channel_id"
    )

    if not channel_id:
        return

    channel = member.guild.get_channel(
        channel_id
    )

    if not isinstance(
        channel,
        discord.TextChannel
    ):
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

            "We're sad to see you leave, "
            "but we hope to see you back again soon! ♡\n\n"

            "─────────────── ୨୧ ───────────────"
        ),

        color=GRAY
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    await channel.send(
        embed=embed
    )


# =========================================================
# TICKET VIEW
# =========================================================

class TicketView(
    discord.ui.View
):

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

        if not isinstance(
            category,
            discord.CategoryChannel
        ):

            return await interaction.response.send_message(

                "❌ The ticket category "
                "hasn't been configured yet.",

                ephemeral=True
            )

        for channel in guild.text_channels:

            if channel.topic == (
                f"ali_adm_ticket:"
                f"{interaction.user.id}"
            ):

                return await interaction.response.send_message(

                    f"❌ You already have an "
                    f"open ticket: "
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

            overwrites[
                staff_role
            ] = discord.PermissionOverwrite(

                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                attach_files=True,
                embed_links=True
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

                "❌ I don't have permission "
                "to create ticket channels.",

                ephemeral=True
            )

        embed = discord.Embed(

            title=(
                "୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡"
            ),

            description=(
                f"Welcome {interaction.user.mention}! ♡\n\n"

                "Thank you for contacting "
                "**ali's adm house**!\n\n"

                "Please tell us what you need help with.\n\n"

                "୨୧ **House:**\n"
                "୨୧ **Build type:**\n\n"

                "A staff member will be with "
                "you shortly. ♡"
            ),

            color=PINK
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

class CloseTicketView(
    discord.ui.View
):

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

        if is_staff(interaction):

            await interaction.response.send_message(

                "🔒 Closing ticket in "
                "**3 seconds**..."
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

        guild = interaction.guild

        if guild is None:
            return

        vouch_channel_id = config.get(
            "vouch_channel_id"
        )

        vouch_channel = (
            guild.get_channel(
                vouch_channel_id
            )
            if vouch_channel_id
            else None
        )

        if not isinstance(
            vouch_channel,
            discord.TextChannel
        ):

            return await interaction.response.send_message(

                "❌ The vouch channel has "
                "not been configured yet.",

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

                if (
                    message.created_at
                    >= ticket_created_at
                ):

                    has_vouched = True
                    break

        bot_commands_channel = discord.utils.get(

            guild.text_channels,

            name="₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼"
        )

        if bot_commands_channel:

            commands_mention = (
                bot_commands_channel.mention
            )

        else:

            commands_mention = (
                "`#₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼`"
            )

        if not has_vouched:

            return await interaction.response.send_message(

                "Did you vouch yet? ♡\n\n"

                f"Please use `/vouch` in "
                f"{commands_mention} "
                "before closing your ticket!",

                ephemeral=True
            )

        await interaction.response.send_message(

            "Thank you so much for your order "
            "and for leaving a vouch! ♡\n"

            "We hope to see you again at "
            "**ali's adm house**! 🌸\n\n"

            "🔒 *Closing this ticket "
            "in 3 seconds...*"
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
# READY
# =========================================================

@bot.event
async def on_ready():

    print(
        f"Logged in as {bot.user} "
        f"(ID: {bot.user.id})"
    )

    if not getattr(
        bot,
        "_persistent_views_loaded",
        False
    ):

        bot.add_view(
            TicketView()
        )

        bot.add_view(
            CloseTicketView()
        )

        bot._persistent_views_loaded = True

    if not hasattr(
        bot,
        "_rename_task"
    ):

        bot._rename_task = asyncio.create_task(
            process_channel_renames()
        )

    if not getattr(
        bot,
        "_commands_synced",
        False
    ):

        try:

            synced = await bot.tree.sync()

            bot._commands_synced = True

            print(
                f"Successfully synced "
                f"{len(synced)} slash commands."
            )

        except Exception as error:

            print(
                f"Command sync error: {error}"
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
    panel_channel="Channel for the ticket panel",
    ticket_category="Category where tickets are created",
    staff_role="Staff role",
    vouch_channel="Vouch channel"
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

    config[
        "panel_channel_id"
    ] = panel_channel.id

    config[
        "ticket_category_id"
    ] = ticket_category.id

    config[
        "staff_role_id"
    ] = (
        staff_role.id
        if staff_role
        else None
    )

    if vouch_channel:

        config[
            "vouch_channel_id"
        ] = vouch_channel.id

    save_config(config)

    embed = discord.Embed(

        title=(
            "୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡"
        ),

        description=(
            "Need help with an order?\n"
            "Want to ask about one of our houses?\n\n"

            "Click **🎫 Open Ticket** below "
            "to create a private ticket with "
            "our staff! ♡"
        ),

        color=PINK
    )

    await panel_channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(

        "♡ Ticket system configured successfully!",

        ephemeral=True
    )


# =========================================================
# SETUP STATUS
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

    config[
        "status_channel_id"
    ] = status_channel.id

    save_config(config)

    await interaction.response.send_message(

        f"♡ Status channel set to "
        f"{status_channel.mention}.",

        ephemeral=True
    )


# =========================================================
# SETUP JOINS
# =========================================================

@bot.tree.command(
    name="setupjoins",
    description="Configure welcome/goodbye messages."
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

    config[
        "welcome_goodbye_channel_id"
    ] = welcome_goodbye_channel.id

    if customer_role:

        config[
            "customer_role_id"
        ] = customer_role.id

    save_config(config)

    await interaction.response.send_message(

        "♡ Welcome/goodbye system configured!",

        ephemeral=True
    )


# =========================================================
# SETUP PROOF
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

    config[
        "proof_channel_id"
    ] = proof_channel.id

    save_config(config)

    await interaction.response.send_message(

        "♡ Proof channel configured successfully!\n\n"
        f"📸 Proof Channel: {proof_channel.mention}",

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

        title=(
            "୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡"
        ),

        description=(
            "Need help? ♡\n\n"
            "Click **🎫 Open Ticket** below "
            "to create a private ticket."
        ),

        color=PINK
    )

    await channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(

        f"♡ Ticket panel sent to "
        f"{channel.mention}.",

        ephemeral=True
    )


# =========================================================
# PING
# =========================================================

@bot.tree.command(
    name="ping",
    description="Check the bot latency."
)
async def ping(
    interaction: discord.Interaction
):

    latency = round(
        bot.latency * 1000
    )

    await interaction.response.send_message(

        f"♡ Pong!\n"
        f"🌸 Latency: **{latency}ms**",

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
    image="Upload your proof screenshot"
)
async def proof(
    interaction: discord.Interaction,
    image: discord.Attachment
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

    if not isinstance(
        proof_channel,
        discord.TextChannel
    ):

        return await interaction.response.send_message(

            "❌ The proof channel hasn't "
            "been configured yet.\n\n"

            "Ask an administrator to use "
            "`/setupproof`.",

            ephemeral=True
        )

    # =====================================================
    # IMAGE CHECK
    # =====================================================

    if not image.content_type:

        filename = (
            image.filename.lower()
        )

        valid_extensions = (
            ".png",
            ".jpg",
            ".jpeg",
            ".webp"
        )

        if not filename.endswith(
            valid_extensions
        ):

            return await interaction.response.send_message(

                "❌ Please upload an image!",

                ephemeral=True
            )

    elif not image.content_type.startswith(
        "image/"
    ):

        return await interaction.response.send_message(

            "❌ Please upload an image file!",

            ephemeral=True
        )

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        # =================================================
        # DOWNLOAD IMAGE
        # =================================================

        image_data = await image.read()

        # =================================================
        # GET BLUR MODE FROM CONFIG
        # =================================================
        
        blur_everything = config.get(
            "blur_everything",
            True
        )

        # =================================================
        # SCAN WHOLE IMAGE + BLUR TEXT
        # =================================================

        blurred_data = blur_proof_text(
            image_data,
            blur_everything=blur_everything
        )

        # =================================================
        # SEND PROOF
        # =================================================

        file = discord.File(

            io.BytesIO(
                blurred_data
            ),

            filename="proof.png"
        )

        await proof_channel.send(

            content=(
                "♡ **New Proof!**\n"
                "Thank you so much! ♡"
            ),

            file=file
        )

        # =================================================
        # USER CONFIRMATION
        # =================================================

        await interaction.followup.send(

            "♡ Your proof has been submitted!\n"
            "Thank you so much! ⭐",

            ephemeral=True
        )

    except Exception as error:

        print(
            f"Proof processing error: {error}"
        )

        await interaction.followup.send(

            "❌ There was an error processing "
            "your proof. Please try again.",

            ephemeral=True
        )


# =========================================================
# VOUCH
# =========================================================

@bot.tree.command(
    name="vouch",
    description="Leave a vouch."
)
@app_commands.describe(
    message="Your vouch message"
)
async def vouch(
    interaction: discord.Interaction,
    message: str
):

    channel_id = config.get(
        "vouch_channel_id"
    )

    channel = (
        interaction.guild.get_channel(
            channel_id
        )
        if channel_id
        and interaction.guild
        else None
    )

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        return await interaction.response.send_message(

            "❌ The vouch channel hasn't "
            "been configured yet.",

            ephemeral=True
        )

    embed = discord.Embed(

        title=(
            "୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡"
        ),

        description=(
            f"**{message}**\n\n"

            "୨୧ **𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳**\n"
            f"{interaction.user.mention}\n\n"

            "Thank you so much! ♡"
        ),

        color=PINK
    )

    embed.set_author(
        name=(
            "୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡"
        )
    )

    await channel.send(

        content=interaction.user.mention,

        embed=embed,

        allowed_mentions=discord.AllowedMentions(
            users=[interaction.user]
        )
    )

    await interaction.response.send_message(

        "♡ Your vouch has been posted! "
        "Thank you! ⭐",

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

    channel_id = config.get(
        "vouch_channel_id"
    )

    channel = (
        interaction.guild.get_channel(
            channel_id
        )
        if channel_id
        and interaction.guild
        else None
    )

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        return await interaction.response.send_message(

            "❌ Vouch channel isn't configured.",

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

    await interaction.followup.send(

        f"♡ **ali's adm house** has "
        f"**{count}** vouch(es)! ⭐",

        ephemeral=True
    )


# =========================================================
# STATUS
# =========================================================

@bot.tree.command(
    name="status",
    description="Update the shop status."
)
@app_commands.choices(
    state=[
        app_commands.Choice(
            name="Available",
            value="available"
        ),

        app_commands.Choice(
            name="Busy",
            value="busy"
        ),

        app_commands.Choice(
            name="Closed",
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

            "❌ Only staff can update the status.",

            ephemeral=True
        )

    status_channel_id = config.get(
        "status_channel_id"
    )

    channel = (
        interaction.guild.get_channel(
            status_channel_id
        )
        if status_channel_id
        else None
    )

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        return await interaction.response.send_message(

            "❌ Status channel isn't configured.",

            ephemeral=True
        )

    if state.value == "available":

        title = (
            "🟢・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘢𝘷𝘢𝘪𝘭𝘢𝘣𝘭𝘦"
        )

        description = (
            "Our shop is currently **OPEN** "
            "for new orders! ♡"
        )

        color = GREEN

        channel_name = "🟢-available"

    elif state.value == "busy":

        title = (
            "🔴・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘣𝘶𝘴𝘺"
        )

        description = (
            "Our shop is currently **BUSY**! ♡\n"
            "Orders may take a little longer."
        )

        color = RED

        channel_name = "🔴-busy"

    else:

        title = (
            "⚪・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘤𝘭𝘰𝘴𝘦𝘥"
        )

        description = (
            "Our shop is currently **CLOSED**! ♡"
        )

        color = GRAY

        channel_name = "⚪-closed"

    embed = discord.Embed(

        title=title,

        description=description,

        color=color
    )

    await channel.send(
        embed=embed
    )

    pending_renames[
        channel.id
    ] = channel_name

    await interaction.response.send_message(

        f"♡ Shop status changed to "
        f"**{state.name}**.",

        ephemeral=True
    )


# =========================================================
# SAY
# =========================================================

@bot.tree.command(
    name="say",
    description="Send an announcement."
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

    await channel.send(

        content=(
            role.mention
            if role
            else None
        ),

        embed=embed,

        allowed_mentions=discord.AllowedMentions(
            roles=True
        )
    )

    await interaction.response.send_message(

        f"♡ Announcement sent to "
        f"{channel.mention}.",

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
    user="User to warn",
    reason="Reason"
)
async def warn(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str
):

    if not is_staff(interaction):

        return await interaction.response.send_message(

            "❌ Only staff can warn users.",

            ephemeral=True
        )

    if user.id == interaction.user.id:

        return await interaction.response.send_message(

            "❌ You cannot warn yourself.",

            ephemeral=True
        )

    if (
        interaction.user != interaction.guild.owner
        and user.top_role >= interaction.user.top_role
    ):

        return await interaction.response.send_message(

            "❌ You cannot warn someone with "
            "an equal or higher role.",

            ephemeral=True
        )

    try:

        await user.send(

            embed=discord.Embed(

                title="⚠️ You have been warned",

                description=(
                    f"Reason: **{reason}**"
                ),

                color=RED
            )
        )

    except discord.Forbidden:

        pass

    await interaction.response.send_message(

        f"⚠️ Warned {user.mention}.\n"
        f"Reason: **{reason}**",

        ephemeral=True
    )


# =========================================================
# CLEAR
# =========================================================

@bot.tree.command(
    name="clear",
    description="Delete messages."
)
async def clear(
    interaction: discord.Interaction,
    amount: int
):

    if not is_staff(interaction):

        return await interaction.response.send_message(

            "❌ Only staff can clear messages.",

            ephemeral=True
        )

    if amount < 1 or amount > 100:

        return await interaction.response.send_message(

            "❌ Amount must be between 1 and 100.",

            ephemeral=True
        )

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):

        return await interaction.response.send_message(

            "❌ This isn't a text channel.",

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

            f"🗑️ Deleted **{len(deleted)}** messages.",

            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.followup.send(

            "❌ I don't have permission "
            "to delete messages.",

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

            "❌ You cannot give @everyone.",

            ephemeral=True
        )

    if (
        interaction.guild.me
        and role >= interaction.guild.me.top_role
    ):

        return await interaction.response.send_message(

            "❌ I cannot give that role because "
            "it is too high.",

            ephemeral=True
        )

    try:

        await user.add_roles(
            role,
            reason=(
                f"Given by {interaction.user}"
            )
        )

        await interaction.response.send_message(

            f"✅ Gave {user.mention} "
            f"{role.mention}.",

            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(

            "❌ I cannot give that role.",

            ephemeral=True
        )


# =========================================================
# MUTE
# =========================================================

@bot.tree.command(
    name="mute",
    description="Timeout a user for 10 minutes."
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

    if user.id == interaction.user.id:

        return await interaction.response.send_message(

            "❌ You cannot mute yourself.",

            ephemeral=True
        )

    if (
        interaction.user != interaction.guild.owner
        and user.top_role >= interaction.user.top_role
    ):

        return await interaction.response.send_message(

            "❌ You cannot mute someone with "
            "an equal or higher role.",

            ephemeral=True
        )

    if (
        interaction.guild.me
        and user.top_role >= interaction.guild.me.top_role
    ):

        return await interaction.response.send_message(

            "❌ I cannot mute that user.",

            ephemeral=True
        )

    try:

        await user.timeout(

            discord.utils.utcnow()
            + timedelta(minutes=10),

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

            "❌ I don't have permission "
            "to timeout that user.",

            ephemeral=True
        )


# =========================================================
# BAN
# =========================================================

@bot.tree.command(
    name="ban",
    description="Ban a user."
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

    if user.id == interaction.user.id:

        return await interaction.response.send_message(

            "❌ You cannot ban yourself.",

            ephemeral=True
        )

    if (
        interaction.user != interaction.guild.owner
        and user.top_role >= interaction.user.top_role
    ):

        return await interaction.response.send_message(

            "❌ You cannot ban someone with "
            "an equal or higher role.",

            ephemeral=True
        )

    if (
        interaction.guild.me
        and user.top_role >= interaction.guild.me.top_role
    ):

        return await interaction.response.send_message(

            "❌ I cannot ban that user.",

            ephemeral=True
        )

    try:

        await interaction.guild.ban(
            user,
            reason=reason
        )

        await interaction.response.send_message(

            f"🚫 Banned {user.mention}.\n"
            f"Reason: **{reason}**",

            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(

            "❌ I don't have permission "
            "to ban that user.",

            ephemeral=True
        )


# =========================================================
# KICK
# =========================================================

@bot.tree.command(
    name="kick",
    description="Kick a user."
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

    if user.id == interaction.user.id:

        return await interaction.response.send_message(

            "❌ You cannot kick yourself.",

            ephemeral=True
        )

    if (
        interaction.user != interaction.guild.owner
        and user.top_role >= interaction.user.top_role
    ):

        return await interaction.response.send_message(

            "❌ You cannot kick someone with "
            "an equal or higher role.",

            ephemeral=True
        )

    if (
        interaction.guild.me
        and user.top_role >= interaction.guild.me.top_role
    ):

        return await interaction.response.send_message(

            "❌ I cannot kick that user.",

            ephemeral=True
        )

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

            "❌ I don't have permission "
            "to kick that user.",

            ephemeral=True
        )


# =========================================================
# LOCK CHANNEL
# =========================================================

@bot.tree.command(
    name="lockchannel",
    description="Lock a channel."
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

            "❌ Invalid text channel.",

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

            "❌ I don't have permission "
            "to lock that channel.",

            ephemeral=True
        )


# =========================================================
# UNLOCK CHANNEL
# =========================================================

@bot.tree.command(
    name="unlockchannel",
    description="Unlock a channel."
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

            "❌ Invalid text channel.",

            ephemeral=True
        )

    try:

        await target.set_permissions(

            interaction.guild.default_role,

            send_messages=True,

            reason=reason
        )

        await interaction.response.send_message(

            f"🔓 Unlocked {target.mention}.\n"
            f"Reason: **{reason}**",

            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.response.send_message(

            "❌ I don't have permission "
            "to unlock that channel.",

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

    if message is None:

        return await ctx.send(

            "❌ Please include a vouch message!\n\n"
            "Example:\n"
            "`!vouch Great service! ♡`",

            delete_after=10
        )

    channel_id = config.get(
        "vouch_channel_id"
    )

    channel = (
        ctx.guild.get_channel(
            channel_id
        )
        if channel_id
        and ctx.guild
        else None
    )

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        return await ctx.send(
            "❌ Vouch channel isn't configured."
        )

    embed = discord.Embed(

        title=(
            "୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡"
        ),

        description=(
            f"**{message}**\n\n"

            "୨୧ **𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳**\n"
            f"{ctx.author.mention}\n\n"

            "Thank you so much! ♡"
        ),

        color=PINK
    )

    embed.set_author(
        name=(
            "୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡"
        )
    )

    await channel.send(

        content=ctx.author.mention,

        embed=embed,

        allowed_mentions=discord.AllowedMentions(
            users=[ctx.author]
        )
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
# COMMAND ERRORS
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

                "❌ Something went wrong "
                "while running that command.",

                ephemeral=True
            )

        else:

            await interaction.response.send_message(

                "❌ Something went wrong "
                "while running that command.",

                ephemeral=True
            )

    except Exception as send_error:

        print(
            f"Could not send error message: "
            f"{send_error}"
        )


# =========================================================
# START BOT
# =========================================================

TOKEN = os.getenv(
    "DISCORD_TOKEN"
)

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN is not set."
    )


keep_alive()

bot.run(TOKEN)

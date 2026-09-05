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
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    Thread(target=run_web, daemon=True).start()


# =========================================================
# CONFIG
# =========================================================

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "panel_channel_id": int(os.getenv("PANEL_CHANNEL_ID", 0)) or None,
    "ticket_category_id": int(os.getenv("TICKET_CATEGORY_ID", 0)) or None,
    "vouch_channel_id": int(os.getenv("VOUCH_CHANNEL_ID", 0)) or None,
    "status_channel_id": int(os.getenv("STATUS_CHANNEL_ID", 0)) or None,
    "welcome_goodbye_channel_id": int(
        os.getenv("WELCOME_GOODBYE_CHANNEL_ID", 0)
    ) or None,
    "proof_channel_id": int(os.getenv("PROOF_CHANNEL_ID", 0)) or None,
    "staff_role_id": int(os.getenv("STAFF_ROLE_ID", 0)) or None,
    "customer_role_id": int(
        os.getenv("CUSTOMER_ROLE_ID", 1545438540362555463)
    ) or 1545438540362555463,
    "blur_everything": bool(
        os.getenv("BLUR_EVERYTHING", "true").lower() == "true"
    )
}


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)

        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        merged = DEFAULT_CONFIG.copy()
        merged.update(loaded)

        return merged

    except Exception:
        return DEFAULT_CONFIG.copy()


config = load_config()


# =========================================================
# DISCORD
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

PINK = (255, 143, 194)
GREEN = (87, 242, 135)
RED = (237, 66, 69)
GRAY = (149, 165, 166)


# =========================================================
# EMBED HELPER
# =========================================================

def styled_embed(title, description="", color=PINK):

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.from_rgb(*color)
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

    if staff_role_id:

        role = interaction.guild.get_role(
            int(staff_role_id)
        )

        if role and role in interaction.user.roles:
            return True

    return interaction.user.guild_permissions.manage_channels


# =========================================================
# BLACK HIGHLIGHTED TEXT BLUR
# =========================================================
#
# Targets large bold black text such as:
#
#     SavvyS122994
#
# It does NOT simply blur every dark pixel.
#
# The detector:
# - Uses OCR first
# - Checks actual black pixels
# - Requires large text
# - Checks for a light surrounding background
# - Selects the strongest matching text only
# - Uses tight padding
#
# This prevents:
# - View button
# - Report button
# - gray boxes
# - refresh icon
# - borders
# - date/time
# from being blurred.
# =========================================================

def blur_proof_text(
    image_data: bytes,
    blur_everything: bool = True
) -> bytes:

    try:

        print("[PROOF] Starting large black-text scan...")

        original = Image.open(
            io.BytesIO(image_data)
        ).convert("RGB")

        width, height = original.size

        if width <= 0 or height <= 0:
            return image_data

        rgb = np.array(original)

        gray = cv2.cvtColor(
            rgb,
            cv2.COLOR_RGB2GRAY
        )

        # -------------------------------------------------
        # UPSCALE
        # -------------------------------------------------

        scale = 3

        enlarged = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

        # -------------------------------------------------
        # OCR CANDIDATES
        # -------------------------------------------------

        candidates = []

        ocr_variants = [
            (
                enlarged,
                "--oem 3 --psm 11"
            ),
            (
                cv2.threshold(
                    enlarged,
                    0,
                    255,
                    cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )[1],
                "--oem 3 --psm 11"
            ),
            (
                cv2.adaptiveThreshold(
                    enlarged,
                    255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY,
                    31,
                    9
                ),
                "--oem 3 --psm 11"
            ),
            (
                enlarged,
                "--oem 3 --psm 12"
            )
        ]

        for processed, ocr_config in ocr_variants:

            try:

                data = pytesseract.image_to_data(
                    processed,
                    config=ocr_config,
                    output_type=pytesseract.Output.DICT
                )

            except Exception as e:

                print(
                    f"[PROOF] OCR error: {e}"
                )

                continue

            texts = data.get("text", [])
            lefts = data.get("left", [])
            tops = data.get("top", [])
            widths = data.get("width", [])
            heights = data.get("height", [])
            confs = data.get("conf", [])

            for i in range(len(texts)):

                text = str(
                    texts[i]
                ).strip()

                if not text:
                    continue

                if len(text) < 2:
                    continue

                try:

                    confidence = float(
                        confs[i]
                    )

                except Exception:

                    confidence = 0

                # Stronger OCR requirement.
                if confidence < 35:
                    continue

                try:

                    x = int(
                        lefts[i] / scale
                    )

                    y = int(
                        tops[i] / scale
                    )

                    w = int(
                        widths[i] / scale
                    )

                    h = int(
                        heights[i] / scale
                    )

                except Exception:

                    continue

                if w <= 0 or h <= 0:
                    continue

                if x < 0 or y < 0:
                    continue

                if x >= width or y >= height:
                    continue

                x2 = min(
                    width,
                    x + w
                )

                y2 = min(
                    height,
                    y + h
                )

                w = x2 - x
                h = y2 - y

                # -------------------------------------------------
                # LARGE TEXT REQUIREMENTS
                # -------------------------------------------------

                if w < 35:
                    continue

                if h < 11:
                    continue

                if w > width * 0.55:
                    continue

                if h > height * 0.15:
                    continue

                aspect = w / max(h, 1)

                if aspect < 1.8:
                    continue

                # -------------------------------------------------
                # ACTUAL PIXEL CHECK
                # -------------------------------------------------

                candidate = gray[
                    y:y2,
                    x:x2
                ]

                if candidate.size == 0:
                    continue

                dark_ratio = float(
                    np.mean(
                        candidate <= 100
                    )
                )

                black_ratio = float(
                    np.mean(
                        candidate <= 75
                    )
                )

                # The target is genuinely black.
                if dark_ratio < 0.06:
                    continue

                if black_ratio < 0.025:
                    continue

                # -------------------------------------------------
                # LIGHT BACKGROUND CHECK
                # -------------------------------------------------

                pad = max(
                    5,
                    int(h * 0.7)
                )

                sx1 = max(
                    0,
                    x - pad
                )

                sy1 = max(
                    0,
                    y - pad
                )

                sx2 = min(
                    width,
                    x2 + pad
                )

                sy2 = min(
                    height,
                    y2 + pad
                )

                surrounding = gray[
                    sy1:sy2,
                    sx1:sx2
                ]

                if surrounding.size == 0:
                    continue

                surrounding_mean = float(
                    np.mean(
                        surrounding
                    )
                )

                candidate_mean = float(
                    np.mean(
                        candidate
                    )
                )

                # Target is on a light card/background.
                if surrounding_mean < 135:
                    continue

                if (
                    surrounding_mean
                    -
                    candidate_mean
                    < 35
                ):
                    continue

                # -------------------------------------------------
                # SCORE
                # -------------------------------------------------

                score = 0

                if h >= 16:
                    score += 3

                elif h >= 13:
                    score += 2

                if w >= 70:
                    score += 2

                if w >= 100:
                    score += 2

                if aspect >= 3:
                    score += 1

                if dark_ratio >= 0.10:
                    score += 2

                if black_ratio >= 0.05:
                    score += 2

                if confidence >= 60:
                    score += 2

                candidates.append(
                    {
                        "x1": x,
                        "y1": y,
                        "x2": x2,
                        "y2": y2,
                        "text": text,
                        "confidence": confidence,
                        "dark_ratio": dark_ratio,
                        "black_ratio": black_ratio,
                        "score": score
                    }
                )

        print(
            f"[PROOF] OCR candidates: "
            f"{len(candidates)}"
        )

        # -------------------------------------------------
        # REMOVE DUPLICATES
        # -------------------------------------------------

        unique = []

        for candidate in candidates:

            duplicate = False

            for existing in unique:

                ax1 = candidate["x1"]
                ay1 = candidate["y1"]
                ax2 = candidate["x2"]
                ay2 = candidate["y2"]

                bx1 = existing["x1"]
                by1 = existing["y1"]
                bx2 = existing["x2"]
                by2 = existing["y2"]

                ix1 = max(
                    ax1,
                    bx1
                )

                iy1 = max(
                    ay1,
                    by1
                )

                ix2 = min(
                    ax2,
                    bx2
                )

                iy2 = min(
                    ay2,
                    by2
                )

                if ix2 <= ix1 or iy2 <= iy1:
                    continue

                intersection = (
                    (ix2 - ix1)
                    *
                    (iy2 - iy1)
                )

                area_a = (
                    (ax2 - ax1)
                    *
                    (ay2 - ay1)
                )

                area_b = (
                    (bx2 - bx1)
                    *
                    (by2 - by1)
                )

                smaller_area = min(
                    area_a,
                    area_b
                )

                overlap_ratio = (
                    intersection
                    /
                    max(smaller_area, 1)
                )

                if overlap_ratio > 0.50:

                    duplicate = True

                    if (
                        candidate["score"]
                        >
                        existing["score"]
                    ):

                        existing.update(
                            candidate
                        )

                    break

            if not duplicate:
                unique.append(
                    candidate
                )

        candidates = unique

        print(
            f"[PROOF] Unique candidates: "
            f"{len(candidates)}"
        )

        # -------------------------------------------------
        # SORT BY STRENGTH
        # -------------------------------------------------

        candidates.sort(
            key=lambda item: (
                item["score"],
                item["confidence"],
                item["black_ratio"],
                item["dark_ratio"]
            ),
            reverse=True
        )

        # -------------------------------------------------
        # SELECT STRONGEST TARGET ONLY
        # -------------------------------------------------

        selected = None

        if candidates:

            selected = candidates[0]

            print(
                "[PROOF] Selected target:"
                f" {selected['text']}"
                f" | score={selected['score']}"
                f" | confidence="
                f"{selected['confidence']:.1f}"
                f" | box=("
                f"{selected['x1']},"
                f"{selected['y1']},"
                f"{selected['x2']},"
                f"{selected['y2']})"
            )

        # -------------------------------------------------
        # CHARACTER LEVEL FALLBACK
        # -------------------------------------------------

        if selected is None:

            print(
                "[PROOF] Normal OCR failed."
                " Trying character OCR..."
            )

            try:

                boxes = pytesseract.image_to_boxes(
                    enlarged,
                    config="--oem 3 --psm 11"
                )

                chars = []

                for line in boxes.splitlines():

                    parts = line.split()

                    if len(parts) < 6:
                        continue

                    char = parts[0]

                    try:

                        bx1 = int(
                            int(parts[1]) / scale
                        )

                        by_bottom = int(
                            int(parts[2]) / scale
                        )

                        bx2 = int(
                            int(parts[3]) / scale
                        )

                        by_top = int(
                            int(parts[4]) / scale
                        )

                    except Exception:

                        continue

                    # Tesseract coordinates are bottom-up.
                    cy1 = (
                        height
                        -
                        by_top
                    )

                    cy2 = (
                        height
                        -
                        by_bottom
                    )

                    cw = bx2 - bx1
                    ch = cy2 - cy1

                    if cw < 2:
                        continue

                    if ch < 7:
                        continue

                    chars.append(
                        (
                            bx1,
                            cy1,
                            bx2,
                            cy2,
                            char
                        )
                    )

                chars.sort(
                    key=lambda item: (
                        item[1],
                        item[0]
                    )
                )

                lines = []

                for char in chars:

                    cx = (
                        char[0]
                        +
                        char[2]
                    ) / 2

                    cy = (
                        char[1]
                        +
                        char[3]
                    ) / 2

                    placed = False

                    for line in lines:

                        average_y = np.mean(
                            [
                                (
                                    c[1]
                                    +
                                    c[3]
                                ) / 2
                                for c in line
                            ]
                        )

                        if abs(
                            cy - average_y
                        ) <= 10:

                            line.append(
                                char
                            )

                            placed = True
                            break

                    if not placed:

                        lines.append(
                            [char]
                        )

                best = None
                best_score = 0

                for line in lines:

                    if len(line) < 4:
                        continue

                    line.sort(
                        key=lambda item: item[0]
                    )

                    lx1 = min(
                        c[0]
                        for c in line
                    )

                    ly1 = min(
                        c[1]
                        for c in line
                    )

                    lx2 = max(
                        c[2]
                        for c in line
                    )

                    ly2 = max(
                        c[3]
                        for c in line
                    )

                    lw = lx2 - lx1
                    lh = ly2 - ly1

                    if lw < 50:
                        continue

                    if lh < 12:
                        continue

                    if lw / max(lh, 1) < 2:
                        continue

                    candidate = gray[
                        ly1:ly2,
                        lx1:lx2
                    ]

                    if candidate.size == 0:
                        continue

                    dark_ratio = float(
                        np.mean(
                            candidate <= 100
                        )
                    )

                    black_ratio = float(
                        np.mean(
                            candidate <= 75
                        )
                    )

                    if dark_ratio < 0.07:
                        continue

                    if black_ratio < 0.025:
                        continue

                    pad = 6

                    sx1 = max(
                        0,
                        lx1 - pad
                    )

                    sy1 = max(
                        0,
                        ly1 - pad
                    )

                    sx2 = min(
                        width,
                        lx2 + pad
                    )

                    sy2 = min(
                        height,
                        ly2 + pad
                    )

                    surrounding = gray[
                        sy1:sy2,
                        sx1:sx2
                    ]

                    if surrounding.size == 0:
                        continue

                    surrounding_mean = float(
                        np.mean(
                            surrounding
                        )
                    )

                    candidate_mean = float(
                        np.mean(
                            candidate
                        )
                    )

                    if surrounding_mean < 135:
                        continue

                    if (
                        surrounding_mean
                        -
                        candidate_mean
                        < 35
                    ):
                        continue

                    score = (
                        len(line) * 2
                        +
                        int(lw / 30)
                        +
                        int(lh / 5)
                    )

                    if dark_ratio >= 0.12:
                        score += 3

                    if black_ratio >= 0.05:
                        score += 3

                    if score > best_score:

                        best_score = score

                        best = {
                            "x1": lx1,
                            "y1": ly1,
                            "x2": lx2,
                            "y2": ly2,
                            "text": "",
                            "score": score
                        }

                if best is not None:

                    selected = best

                    print(
                        "[PROOF] Character OCR selected:"
                        f" box=("
                        f"{best['x1']},"
                        f"{best['y1']},"
                        f"{best['x2']},"
                        f"{best['y2']})"
                    )

            except Exception as e:

                print(
                    f"[PROOF] Character OCR error: {e}"
                )

        # -------------------------------------------------
        # NO TARGET
        # -------------------------------------------------

        if selected is None:

            print(
                "[PROOF] No target text found."
            )

            # NEVER mass blur the proof.
            return image_data

        # -------------------------------------------------
        # TARGET BOX
        # -------------------------------------------------

        x1 = int(
            selected["x1"]
        )

        y1 = int(
            selected["y1"]
        )

        x2 = int(
            selected["x2"]
        )

        y2 = int(
            selected["y2"]
        )

        rw = x2 - x1
        rh = y2 - y1

        if rw <= 0 or rh <= 0:
            return image_data

        # -------------------------------------------------
        # VERY TIGHT PADDING
        # -------------------------------------------------

        # Only enough to cover the username.
        pad_x = max(
            3,
            int(rw * 0.025)
        )

        pad_y = max(
            3,
            int(rh * 0.20)
        )

        bx1 = max(
            0,
            x1 - pad_x
        )

        by1 = max(
            0,
            y1 - pad_y
        )

        bx2 = min(
            width,
            x2 + pad_x
        )

        by2 = min(
            height,
            y2 + pad_y
        )

        # -------------------------------------------------
        # MASK
        # -------------------------------------------------

        mask = np.zeros(
            (height, width),
            dtype=np.uint8
        )

        cv2.rectangle(
            mask,
            (bx1, by1),
            (bx2, by2),
            255,
            -1
        )

        # Tiny expansion for antialiased edges.
        mask = cv2.dilate(
            mask,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (3, 3)
            ),
            iterations=1
        )

        # -------------------------------------------------
        # BLUR
        # -------------------------------------------------

        blurred = original.filter(
            ImageFilter.GaussianBlur(
                radius=25
            )
        )

        mask_image = Image.fromarray(
            mask,
            mode="L"
        )

        mask_image = mask_image.filter(
            ImageFilter.GaussianBlur(
                radius=0.8
            )
        )

        result = Image.composite(
            blurred,
            original,
            mask_image
        )

        # -------------------------------------------------
        # SAVE
        # -------------------------------------------------

        output = io.BytesIO()

        result.save(
            output,
            format="PNG"
        )

        output.seek(0)

        print(
            "[PROOF] Target text blurred successfully."
        )

        return output.getvalue()

    except Exception as e:

        print(
            f"[PROOF] Blur error: {e}"
        )

        return image_data


# =========================================================
# CHANNEL RENAME QUEUE
# =========================================================

pending_renames = {}


async def process_channel_renames():

    await bot.wait_until_ready()

    while not bot.is_closed():

        if pending_renames:

            items = list(
                pending_renames.items()
            )

            for channel_id, new_name in items:

                channel = bot.get_channel(
                    channel_id
                )

                if channel is None:

                    pending_renames.pop(
                        channel_id,
                        None
                    )

                    continue

                try:

                    await channel.edit(
                        name=new_name
                    )

                    pending_renames.pop(
                        channel_id,
                        None
                    )

                    await asyncio.sleep(2)

                except discord.HTTPException as e:

                    if e.status == 429:

                        retry_after = getattr(
                            e,
                            "retry_after",
                            5
                        )

                        print(
                            f"Rate limited. "
                            f"Retrying in {retry_after}s"
                        )

                        await asyncio.sleep(
                            retry_after
                        )

                    else:

                        print(
                            f"Channel rename error: {e}"
                        )

                        pending_renames.pop(
                            channel_id,
                            None
                        )

        await asyncio.sleep(5)


# =========================================================
# MEMBER JOIN
# =========================================================

@bot.event
async def on_member_join(member):

    try:

        customer_role_id = config.get(
            "customer_role_id"
        )

        if customer_role_id:

            role = member.guild.get_role(
                int(customer_role_id)
            )

            if role:

                try:

                    await member.add_roles(
                        role,
                        reason="Automatic customer role"
                    )

                except Exception as e:

                    print(
                        f"Customer role error: {e}"
                    )

        channel_id = config.get(
            "welcome_goodbye_channel_id"
        )

        if not channel_id:
            return

        channel = member.guild.get_channel(
            int(channel_id)
        )

        if not channel:
            return

        embed = styled_embed(
            """
╭───────────── ୨୧ ─────────────╮
       🌸˚₊ 𝘸𝘦𝘭𝘤𝘰𝘮𝘦 𝘵𝘰 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦! ♡
╰───────────── ୨୧ ─────────────╯
            """,
            f"""
Welcome {member.mention}! ♡

**Getting Started**
୨୧ Check out our products and shop
୨୧ Open a support ticket if you need help
୨୧ Read the server information
୨୧ Have fun and enjoy your stay! ♡

━━━━━━━━━━━━━━━━━━━━
            """
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.add_field(
            name="Customer",
            value=member.mention,
            inline=True
        )

        embed.add_field(
            name="Member Count",
            value=str(
                member.guild.member_count
            ),
            inline=True
        )

        await channel.send(
            content=member.mention,
            embed=embed
        )

    except Exception as e:

        print(
            f"Join event error: {e}"
        )


# =========================================================
# MEMBER LEAVE
# =========================================================

@bot.event
async def on_member_remove(member):

    try:

        channel_id = config.get(
            "welcome_goodbye_channel_id"
        )

        if not channel_id:
            return

        channel = member.guild.get_channel(
            int(channel_id)
        )

        if not channel:
            return

        embed = styled_embed(
            """
╭───────────── ୨୧ ─────────────╮
            💔˚₊ 𝘨𝘰𝘰𝘥𝘣𝘺𝘦, 𝘴𝘦𝘦 𝘺𝘰𝘶 𝘴𝘰𝘰𝘯! ♡
╰───────────── ୨୧ ─────────────╯
            """,
            f"""
{member.mention} has left ali's adm house. ♡

We hope to see you again soon!
            """
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        await channel.send(
            embed=embed
        )

    except Exception as e:

        print(
            f"Leave event error: {e}"
        )


# =========================================================
# TICKET VIEW
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="Open Ticket",
        emoji="🎀",
        style=discord.ButtonStyle.primary,
        custom_id="ali_adm_open_ticket"
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "This can only be used in a server.",
                ephemeral=True
            )

            return

        category_id = config.get(
            "ticket_category_id"
        )

        if not category_id:

            await interaction.response.send_message(
                "Tickets are not configured yet.",
                ephemeral=True
            )

            return

        category = interaction.guild.get_channel(
            int(category_id)
        )

        if not category:

            await interaction.response.send_message(
                "The ticket category could not be found.",
                ephemeral=True
            )

            return

        for channel in category.channels:

            if (
                channel.topic
                == f"ali_adm_ticket:{interaction.user.id}"
            ):

                await interaction.response.send_message(
                    f"You already have an open ticket: {channel.mention}",
                    ephemeral=True
                )

                return

        overwrites = {
            interaction.guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        staff_role_id = config.get(
            "staff_role_id"
        )

        if staff_role_id:

            staff_role = interaction.guild.get_role(
                int(staff_role_id)
            )

            if staff_role:

                overwrites[staff_role] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_messages=True
                    )
                )

        channel_name = (
            f"ticket-{interaction.user.name}"
        )[:90]

        try:

            ticket = await interaction.guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                topic=(
                    f"ali_adm_ticket:"
                    f"{interaction.user.id}"
                )
            )

        except Exception as e:

            await interaction.response.send_message(
                f"Could not create ticket: `{e}`",
                ephemeral=True
            )

            return

        embed = styled_embed(
            "୨୧・𝘵𝘪𝘤𝘬𝘦𝘵 𝘰𝘱𝘦𝘯𝘦𝘥 ♡",
            f"""
Welcome {interaction.user.mention}! ♡

Please tell us:

୨୧ What house/build do you want?
୨୧ What type of build?
୨୧ Any specific details?
୨୧ Anything else we should know?

A staff member will help you shortly. ♡
            """
        )

        await interaction.response.send_message(
            f"Your ticket has been created: {ticket.mention}",
            ephemeral=True
        )

        await ticket.send(
            content=interaction.user.mention,
            embed=embed,
            view=CloseTicketView()
        )


# =========================================================
# CLOSE TICKET VIEW
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

        if not interaction.guild:

            await interaction.response.send_message(
                "This can only be used in a server.",
                ephemeral=True
            )

            return

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "This is not a ticket channel.",
                ephemeral=True
            )

            return

        if is_staff(interaction):

            await interaction.response.send_message(
                "🔒 Closing ticket in 3 seconds...",
                ephemeral=False
            )

            await asyncio.sleep(3)

            try:

                await channel.delete(
                    reason="Ticket closed by staff"
                )

            except Exception:
                pass

            return

        vouch_channel_id = config.get(
            "vouch_channel_id"
        )

        if not vouch_channel_id:

            await interaction.response.send_message(
                "Vouch channel is not configured.",
                ephemeral=True
            )

            return

        vouch_channel = interaction.guild.get_channel(
            int(vouch_channel_id)
        )

        if not vouch_channel:

            await interaction.response.send_message(
                "Vouch channel could not be found.",
                ephemeral=True
            )

            return

        has_vouched = False

        try:

            async for message in vouch_channel.history(
                limit=1000
            ):

                if message.author.id != bot.user.id:
                    continue

                if (
                    interaction.user.mention
                    in message.content
                    or str(interaction.user.id)
                    in message.content
                ):

                    has_vouched = True
                    break

        except Exception as e:

            print(
                f"Vouch check error: {e}"
            )

        if not has_vouched:

            await interaction.response.send_message(
                """
You need to leave a vouch before closing your ticket. ♡

Please use `/vouch` in
`₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼`
                """,
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "🔒 Vouch found! Closing ticket in 3 seconds...",
            ephemeral=False
        )

        await asyncio.sleep(3)

        try:

            await channel.delete(
                reason="Ticket closed"
            )

        except Exception:
            pass


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
        "_persistent_views_added",
        False
    ):

        bot.add_view(
            TicketView()
        )

        bot.add_view(
            CloseTicketView()
        )

        bot._persistent_views_added = True

    if not getattr(
        bot,
        "_rename_task_started",
        False
    ):

        asyncio.create_task(
            process_channel_renames()
        )

        bot._rename_task_started = True

    if not getattr(
        bot,
        "_commands_synced",
        False
    ):

        try:

            synced = await bot.tree.sync()

            print(
                f"Synced {len(synced)} slash commands."
            )

            bot._commands_synced = True

        except Exception as e:

            print(
                f"Slash command sync error: {e}"
            )


# =========================================================
# SETUP
# =========================================================

@bot.tree.command(
    name="setup",
    description="Set up the ali's adm house ticket system."
)
@app_commands.describe(
    panel_channel="Ticket panel channel",
    ticket_category="Ticket category",
    staff_role="Optional staff role",
    vouch_channel="Optional vouch channel"
)
async def setup(
    interaction: discord.Interaction,
    panel_channel: discord.TextChannel,
    ticket_category: discord.CategoryChannel,
    staff_role: discord.Role = None,
    vouch_channel: discord.TextChannel = None
):

    if not interaction.user.guild_permissions.administrator:

        await interaction.response.send_message(
            "You need Administrator permission.",
            ephemeral=True
        )

        return

    config["panel_channel_id"] = panel_channel.id
    config["ticket_category_id"] = ticket_category.id

    if staff_role:
        config["staff_role_id"] = staff_role.id

    if vouch_channel:
        config["vouch_channel_id"] = vouch_channel.id

    save_config()

    embed = styled_embed(
        "୨୧・𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡",
        """
Need help with your house?

Open a ticket below and tell us
what house/build you would like. ♡

୨୧ Custom houses
୨୧ Grinding houses
୨୧ Cute houses
୨୧ Anime/cartoon houses
୨୧ And more!
        """
    )

    await panel_channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        "Ticket system configured! ♡",
        ephemeral=True
    )


# =========================================================
# SETUP STATUS
# =========================================================

@bot.tree.command(
    name="setupstatus",
    description="Set up the status channel."
)
async def setupstatus(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    if not interaction.user.guild_permissions.administrator:

        await interaction.response.send_message(
            "You need Administrator permission.",
            ephemeral=True
        )

        return

    config["status_channel_id"] = channel.id

    save_config()

    await interaction.response.send_message(
        f"Status channel set to {channel.mention}.",
        ephemeral=True
    )


# =========================================================
# SETUP JOINS
# =========================================================

@bot.tree.command(
    name="setupjoins",
    description="Set up welcome and goodbye messages."
)
@app_commands.describe(
    channel="Welcome/goodbye channel",
    customer_role="Customer role"
)
async def setupjoins(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    customer_role: discord.Role = None
):

    if not interaction.user.guild_permissions.administrator:

        await interaction.response.send_message(
            "You need Administrator permission.",
            ephemeral=True
        )

        return

    config["welcome_goodbye_channel_id"] = channel.id

    if customer_role:
        config["customer_role_id"] = customer_role.id

    save_config()

    await interaction.response.send_message(
        "Welcome/goodbye system configured! ♡",
        ephemeral=True
    )


# =========================================================
# SETUP PROOF
# =========================================================

@bot.tree.command(
    name="setupproof",
    description="Set up the proof channel."
)
async def setupproof(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    if not interaction.user.guild_permissions.administrator:

        await interaction.response.send_message(
            "You need Administrator permission.",
            ephemeral=True
        )

        return

    config["proof_channel_id"] = channel.id

    save_config()

    await interaction.response.send_message(
        f"Proof channel set to {channel.mention}.",
        ephemeral=True
    )


# =========================================================
# TICKET PANEL
# =========================================================

@bot.tree.command(
    name="ticketpanel",
    description="Send the ticket panel."
)
async def ticketpanel(
    interaction: discord.Interaction
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    embed = styled_embed(
        "୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
        """
Need help?

Click **Open Ticket** below to create
your private support ticket. ♡
        """
    )

    await interaction.channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        "Ticket panel sent! ♡",
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

    await interaction.response.send_message(
        f"🏓 Pong! `{latency}ms`",
        ephemeral=True
    )


# =========================================================
# PROOF
# =========================================================

@bot.tree.command(
    name="proof",
    description="Upload a proof image."
)
@app_commands.describe(
    image="Proof image"
)
async def proof(
    interaction: discord.Interaction,
    image: discord.Attachment
):

    proof_channel_id = config.get(
        "proof_channel_id"
    )

    if not proof_channel_id:

        await interaction.response.send_message(
            "Proof channel is not configured.",
            ephemeral=True
        )

        return

    proof_channel = interaction.guild.get_channel(
        int(proof_channel_id)
    )

    if not proof_channel:

        await interaction.response.send_message(
            "Proof channel could not be found.",
            ephemeral=True
        )

        return

    valid_extensions = (
        ".png",
        ".jpg",
        ".jpeg",
        ".webp"
    )

    content_type = (
        image.content_type or ""
    ).lower()

    filename = image.filename.lower()

    if not (
        content_type.startswith("image/")
        or filename.endswith(valid_extensions)
    ):

        await interaction.response.send_message(
            "Please upload a PNG, JPG, JPEG, or WEBP image.",
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        image_data = await image.read()

        blur_everything = config.get(
            "blur_everything",
            True
        )

        blurred_data = blur_proof_text(
            image_data,
            blur_everything=blur_everything
        )

        file = discord.File(
            io.BytesIO(blurred_data),
            filename="proof.png"
        )

        await proof_channel.send(
            content="""
♡ **New Proof!**
Thank you so much! ♡
            """,
            file=file
        )

        await interaction.followup.send(
            "Your proof has been submitted! ♡",
            ephemeral=True
        )

    except Exception as e:

        print(
            f"Proof command error: {e}"
        )

        await interaction.followup.send(
            "Something went wrong while processing the proof.",
            ephemeral=True
        )


# =========================================================
# VOUCH
# =========================================================

@bot.tree.command(
    name="vouch",
    description="Leave a customer vouch."
)
@app_commands.describe(
    message="Your vouch message"
)
async def vouch(
    interaction: discord.Interaction,
    message: str
):

    vouch_channel_id = config.get(
        "vouch_channel_id"
    )

    if not vouch_channel_id:

        await interaction.response.send_message(
            "Vouch channel is not configured.",
            ephemeral=True
        )

        return

    channel = interaction.guild.get_channel(
        int(vouch_channel_id)
    )

    if not channel:

        await interaction.response.send_message(
            "Vouch channel could not be found.",
            ephemeral=True
        )

        return

    embed = styled_embed(
        "୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡",
        f"""
**Message**
{message}

**Customer**
{interaction.user.mention}
        """
    )

    embed.set_author(
        name="୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡"
    )

    await channel.send(
        content=interaction.user.mention,
        embed=embed
    )

    await interaction.response.send_message(
        "Thank you for your vouch! ♡",
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

    vouch_channel_id = config.get(
        "vouch_channel_id"
    )

    if not vouch_channel_id:

        await interaction.response.send_message(
            "Vouch channel is not configured.",
            ephemeral=True
        )

        return

    channel = interaction.guild.get_channel(
        int(vouch_channel_id)
    )

    if not channel:

        await interaction.response.send_message(
            "Vouch channel could not be found.",
            ephemeral=True
        )

        return

    count = 0

    try:

        async for message in channel.history(
            limit=None
        ):

            if (
                bot.user
                and message.author.id == bot.user.id
            ):

                count += 1

    except Exception as e:

        print(
            f"Vouch count error: {e}"
        )

    await interaction.response.send_message(
        f"୨୧ Total vouches: **{count}** ♡",
        ephemeral=True
    )


# =========================================================
# STATUS
# =========================================================

@bot.tree.command(
    name="status",
    description="Change shop status."
)
@app_commands.describe(
    status="Shop status"
)
@app_commands.choices(
    status=[
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
    status: app_commands.Choice[str]
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    status_channel_id = config.get(
        "status_channel_id"
    )

    if not status_channel_id:

        await interaction.response.send_message(
            "Status channel is not configured.",
            ephemeral=True
        )

        return

    channel = interaction.guild.get_channel(
        int(status_channel_id)
    )

    if not channel:

        await interaction.response.send_message(
            "Status channel could not be found.",
            ephemeral=True
        )

        return

    statuses = {

        "available": (
            "🟢",
            "𝘢𝘷𝘢𝘪𝘭𝘢𝘣𝘭𝘦",
            GREEN
        ),

        "busy": (
            "🔴",
            "𝘣𝘶𝘴𝘺",
            RED
        ),

        "closed": (
            "⚪",
            "𝘤𝘭𝘰𝘴𝘦𝘥",
            GRAY
        )
    }

    emoji, text, color = statuses[
        status.value
    ]

    embed = styled_embed(
        f"{emoji}・𝘴𝘩𝘰𝘱 𝘴𝘵𝘢𝘵𝘶𝘴",
        f"""
Our shop is currently:

**{text}**

♡ ali's adm house
        """,
        color
    )

    await channel.send(
        embed=embed
    )

    rename_map = {
        "available": "🟢-available",
        "busy": "🔴-busy",
        "closed": "⚪-closed"
    }

    pending_renames[
        channel.id
    ] = rename_map[
        status.value
    ]

    await interaction.response.send_message(
        f"Status changed to **{text}**.",
        ephemeral=True
    )


# =========================================================
# SAY
# =========================================================

@bot.tree.command(
    name="say",
    description="Send an announcement."
)
@app_commands.describe(
    channel="Channel to send the message",
    message="Announcement message",
    role="Optional role to mention"
)
async def say(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str,
    role: discord.Role = None
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    embed = styled_embed(
        "𝘢𝘯𝘯𝘰𝘶𝘯𝘤𝘦𝘮𝘦𝘯𝘵",
        message
    )

    content = (
        role.mention
        if role
        else None
    )

    await channel.send(
        content=content,
        embed=embed
    )

    await interaction.response.send_message(
        "Announcement sent! ♡",
        ephemeral=True
    )


# =========================================================
# WARN
# =========================================================

@bot.tree.command(
    name="warn",
    description="Warn a member."
)
@app_commands.describe(
    user="Member to warn",
    reason="Reason for warning"
)
async def warn(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    if user == interaction.user:

        await interaction.response.send_message(
            "You can't warn yourself.",
            ephemeral=True
        )

        return

    if (
        user.top_role >= interaction.user.top_role
        and interaction.guild.owner_id
        != interaction.user.id
    ):

        await interaction.response.send_message(
            "You can't warn someone with an equal or higher role.",
            ephemeral=True
        )

        return

    embed = styled_embed(
        "⚠️・𝘸𝘢𝘳𝘯𝘪𝘯𝘨",
        f"""
You have received a warning in
**{interaction.guild.name}**.

**Reason**
{reason}
        """,
        RED
    )

    try:

        await user.send(
            embed=embed
        )

    except Exception:
        pass

    await interaction.response.send_message(
        f"{user.mention} has been warned.",
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
    amount="Number of messages to delete"
)
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100]
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):

        await interaction.response.send_message(
            "This command can only be used in a text channel.",
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        deleted = await interaction.channel.purge(
            limit=amount
        )

        await interaction.followup.send(
            f"Deleted **{len(deleted)}** messages. ♡",
            ephemeral=True
        )

    except Exception as e:

        await interaction.followup.send(
            f"Could not delete messages: `{e}`",
            ephemeral=True
        )


# =========================================================
# GIVE ROLE
# =========================================================

@bot.tree.command(
    name="giverole",
    description="Give a role to a member."
)
@app_commands.describe(
    user="Member",
    role="Role to give"
)
async def giverole(
    interaction: discord.Interaction,
    user: discord.Member,
    role: discord.Role
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    if role.is_default():

        await interaction.response.send_message(
            "You can't give the @everyone role.",
            ephemeral=True
        )

        return

    if role >= interaction.guild.me.top_role:

        await interaction.response.send_message(
            "My role is not high enough to give that role.",
            ephemeral=True
        )

        return

    if (
        role >= interaction.user.top_role
        and interaction.guild.owner_id
        != interaction.user.id
    ):

        await interaction.response.send_message(
            "You can't give a role equal to or higher than your highest role.",
            ephemeral=True
        )

        return

    try:

        await user.add_roles(
            role,
            reason=f"Given by {interaction.user}"
        )

        await interaction.response.send_message(
            f"Added {role.mention} to {user.mention}. ♡",
            ephemeral=True
        )

    except Exception as e:

        await interaction.response.send_message(
            f"Could not give role: `{e}`",
            ephemeral=True
        )


# =========================================================
# MUTE
# =========================================================

@bot.tree.command(
    name="mute",
    description="Timeout a member for 10 minutes."
)
@app_commands.describe(
    user="Member to mute"
)
async def mute(
    interaction: discord.Interaction,
    user: discord.Member
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    if user == interaction.user:

        await interaction.response.send_message(
            "You can't mute yourself.",
            ephemeral=True
        )

        return

    if (
        user.top_role >= interaction.user.top_role
        and interaction.guild.owner_id
        != interaction.user.id
    ):

        await interaction.response.send_message(
            "You can't mute someone with an equal or higher role.",
            ephemeral=True
        )

        return

    try:

        await user.timeout(
            timedelta(minutes=10),
            reason=f"Muted by {interaction.user}"
        )

        await interaction.response.send_message(
            f"{user.mention} has been muted for 10 minutes.",
            ephemeral=True
        )

    except Exception as e:

        await interaction.response.send_message(
            f"Could not mute user: `{e}`",
            ephemeral=True
        )


# =========================================================
# BAN
# =========================================================

@bot.tree.command(
    name="ban",
    description="Ban a member."
)
@app_commands.describe(
    user="Member to ban",
    reason="Ban reason"
)
async def ban(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    if user == interaction.user:

        await interaction.response.send_message(
            "You can't ban yourself.",
            ephemeral=True
        )

        return

    if user == interaction.guild.owner:

        await interaction.response.send_message(
            "You can't ban the server owner.",
            ephemeral=True
        )

        return

    if (
        user.top_role >= interaction.user.top_role
        and interaction.guild.owner_id
        != interaction.user.id
    ):

        await interaction.response.send_message(
            "You can't ban someone with an equal or higher role.",
            ephemeral=True
        )

        return

    try:

        await interaction.guild.ban(
            user,
            reason=reason
        )

        await interaction.response.send_message(
            f"{user.mention} has been banned.",
            ephemeral=True
        )

    except Exception as e:

        await interaction.response.send_message(
            f"Could not ban user: `{e}`",
            ephemeral=True
        )


# =========================================================
# KICK
# =========================================================

@bot.tree.command(
    name="kick",
    description="Kick a member."
)
@app_commands.describe(
    user="Member to kick",
    reason="Kick reason"
)
async def kick(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    if user == interaction.user:

        await interaction.response.send_message(
            "You can't kick yourself.",
            ephemeral=True
        )

        return

    if (
        user.top_role >= interaction.user.top_role
        and interaction.guild.owner_id
        != interaction.user.id
    ):

        await interaction.response.send_message(
            "You can't kick someone with an equal or higher role.",
            ephemeral=True
        )

        return

    try:

        await interaction.guild.kick(
            user,
            reason=reason
        )

        await interaction.response.send_message(
            f"{user.mention} has been kicked.",
            ephemeral=True
        )

    except Exception as e:

        await interaction.response.send_message(
            f"Could not kick user: `{e}`",
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
    channel: discord.TextChannel = None,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    if channel is None:
        channel = interaction.channel

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        await interaction.response.send_message(
            "That is not a text channel.",
            ephemeral=True
        )

        return

    try:

        await channel.set_permissions(
            interaction.guild.default_role,
            send_messages=False,
            reason=reason
        )

        await interaction.response.send_message(
            f"🔒 Locked {channel.mention}.",
            ephemeral=True
        )

    except Exception as e:

        await interaction.response.send_message(
            f"Could not lock channel: `{e}`",
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
    channel: discord.TextChannel = None,
    reason: str = "No reason provided"
):

    if not is_staff(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this.",
            ephemeral=True
        )

        return

    if channel is None:
        channel = interaction.channel

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        await interaction.response.send_message(
            "That is not a text channel.",
            ephemeral=True
        )

        return

    try:

        await channel.set_permissions(
            interaction.guild.default_role,
            send_messages=True,
            reason=reason
        )

        await interaction.response.send_message(
            f"🔓 Unlocked {channel.mention}.",
            ephemeral=True
        )

    except Exception as e:

        await interaction.response.send_message(
            f"Could not unlock channel: `{e}`",
            ephemeral=True
        )


# =========================================================
# PREFIX VOUCH
# =========================================================

@bot.command(
    name="vouch"
)
async def prefix_vouch(
    ctx,
    *,
    message: str
):

    if not ctx.guild:
        return

    vouch_channel_id = config.get(
        "vouch_channel_id"
    )

    if not vouch_channel_id:
        return

    channel = ctx.guild.get_channel(
        int(vouch_channel_id)
    )

    if not channel:
        return

    embed = styled_embed(
        "୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡",
        f"""
**Message**
{message}

**Customer**
{ctx.author.mention}
        """
    )

    embed.set_author(
        name="୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡"
    )

    await channel.send(
        content=ctx.author.mention,
        embed=embed
    )

    try:

        await ctx.message.delete()

    except Exception:
        pass


# =========================================================
# PREFIX COMMAND ERROR
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
# SLASH COMMAND ERROR
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error
):

    print(
        f"Slash command error: {error}"
    )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                "Something went wrong while running that command.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "Something went wrong while running that command.",
                ephemeral=True
            )

    except Exception as e:

        print(
            f"Could not send slash error: {e}"
        )


# =========================================================
# START
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

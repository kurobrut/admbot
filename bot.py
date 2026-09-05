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
    "blur_everything": os.getenv(
        "BLUR_EVERYTHING",
        "true"
    ).lower() == "true"
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
# HYBRID PROOF TEXT DETECTOR
# =========================================================
#
# This does NOT rely only on OCR.
#
# It combines:
#
# 1. Normal OCR
# 2. Inverted OCR
# 3. Adaptive threshold OCR
# 4. Character-level OCR
# 5. Dark pixel detection
# 6. Connected component detection
# 7. Morphological text grouping
# 8. Large safety padding
#
# This is specifically designed to catch bold/dark text such
# as usernames even if Tesseract fails to recognize them.
# =========================================================

def blur_proof_text(
    image_data: bytes,
    blur_everything: bool = True
) -> bytes:

    try:

        print("[PROOF] Starting hybrid proof scan...")

        original = Image.open(
            io.BytesIO(image_data)
        ).convert("RGB")

        width, height = original.size

        if width <= 0 or height <= 0:
            return image_data

        rgb = np.array(original)

        # =================================================
        # OPENCV BASE
        # =================================================

        gray = cv2.cvtColor(
            rgb,
            cv2.COLOR_RGB2GRAY
        )

        # =================================================
        # 3X UPSCALE
        # =================================================

        scale = 3

        enlarged = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

        # =================================================
        # CONTRAST ENHANCEMENT
        # =================================================

        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8)
        )

        enhanced = clahe.apply(
            enlarged
        )

        # =================================================
        # THRESHOLDS
        # =================================================

        otsu = cv2.threshold(
            enhanced,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]

        inverted_otsu = cv2.bitwise_not(
            otsu
        )

        adaptive = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11
        )

        inverted_adaptive = cv2.bitwise_not(
            adaptive
        )

        # =================================================
        # SHARPEN
        # =================================================

        sharpen_kernel = np.array([
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0]
        ])

        sharpened = cv2.filter2D(
            enhanced,
            -1,
            sharpen_kernel
        )

        ocr_images = [
            enhanced,
            sharpened,
            otsu,
            inverted_otsu,
            adaptive,
            inverted_adaptive
        ]

        # =================================================
        # OCR DETECTION
        # =================================================

        raw_regions = []

        ocr_configs = [
            "--oem 3 --psm 6",
            "--oem 3 --psm 11",
            "--oem 3 --psm 12"
        ]

        for processed in ocr_images:

            for ocr_config in ocr_configs:

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

                texts = data.get(
                    "text",
                    []
                )

                lefts = data.get(
                    "left",
                    []
                )

                tops = data.get(
                    "top",
                    []
                )

                widths = data.get(
                    "width",
                    []
                )

                heights = data.get(
                    "height",
                    []
                )

                confs = data.get(
                    "conf",
                    []
                )

                for i in range(len(texts)):

                    text = str(
                        texts[i]
                    ).strip()

                    if not text:
                        continue

                    try:
                        confidence = float(
                            confs[i]
                        )
                    except Exception:
                        confidence = 0

                    if confidence < 0:
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

                    if w < 2 or h < 2:
                        continue

                    if w > width * 0.90:
                        continue

                    if h > height * 0.25:
                        continue

                    x1 = max(
                        0,
                        x
                    )

                    y1 = max(
                        0,
                        y
                    )

                    x2 = min(
                        width,
                        x + w
                    )

                    y2 = min(
                        height,
                        y + h
                    )

                    if x2 <= x1 or y2 <= y1:
                        continue

                    raw_regions.append({
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "confidence": confidence,
                        "source": "ocr",
                        "text": text
                    })

        print(
            f"[PROOF] OCR regions: "
            f"{len(raw_regions)}"
        )

        # =================================================
        # CHARACTER LEVEL OCR
        # =================================================

        character_regions = []

        for processed in ocr_images:

            try:

                boxes = pytesseract.image_to_boxes(
                    processed,
                    config="--oem 3 --psm 11"
                )

            except Exception:
                continue

            if not boxes:
                continue

            for line in boxes.splitlines():

                parts = line.split()

                if len(parts) < 5:
                    continue

                try:

                    char = parts[0]

                    if not char.strip():
                        continue

                    bx1 = int(parts[1])
                    by1 = int(parts[2])
                    bx2 = int(parts[3])
                    by2 = int(parts[4])

                    image_ocr_height = (
                        processed.shape[0]
                    )

                    x1 = int(
                        bx1 / scale
                    )

                    x2 = int(
                        bx2 / scale
                    )

                    y1 = int(
                        (image_ocr_height - by2)
                        / scale
                    )

                    y2 = int(
                        (image_ocr_height - by1)
                        / scale
                    )

                    if x2 <= x1 or y2 <= y1:
                        continue

                    if (x2 - x1) < 2:
                        continue

                    if (y2 - y1) < 2:
                        continue

                    character_regions.append({
                        "x1": max(0, x1),
                        "y1": max(0, y1),
                        "x2": min(width, x2),
                        "y2": min(height, y2),
                        "confidence": 5,
                        "source": "characters",
                        "text": char
                    })

                except Exception:
                    continue

        print(
            f"[PROOF] Character regions: "
            f"{len(character_regions)}"
        )

        # =================================================
        # VISUAL DARK-TEXT DETECTOR
        # =================================================
        #
        # This is the important new part.
        #
        # It does not care whether OCR understands the
        # text. It looks for groups of dark pixels that
        # visually resemble text.
        # =================================================

        visual_regions = []

        # Use several darkness thresholds.
        darkness_thresholds = [
            80,
            105,
            130,
            155
        ]

        for threshold in darkness_thresholds:

            # Dark pixels become white.
            dark_mask = cv2.inRange(
                gray,
                0,
                threshold
            )

            # Remove tiny noise.
            small_kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (2, 2)
            )

            dark_mask = cv2.morphologyEx(
                dark_mask,
                cv2.MORPH_OPEN,
                small_kernel,
                iterations=1
            )

            # -------------------------------------------------
            # Connect letters horizontally.
            #
            # Example:
            #
            # m c 4 4 4 z
            #
            # becomes one larger region.
            # -------------------------------------------------

            horizontal_kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (13, 3)
            )

            grouped = cv2.morphologyEx(
                dark_mask,
                cv2.MORPH_CLOSE,
                horizontal_kernel,
                iterations=1
            )

            grouped = cv2.dilate(
                grouped,
                horizontal_kernel,
                iterations=1
            )

            # -------------------------------------------------
            # Find connected components.
            # -------------------------------------------------

            contours, _ = cv2.findContours(
                grouped,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:

                x, y, w, h = cv2.boundingRect(
                    contour
                )

                area = w * h

                # Basic filtering.
                if w < 5:
                    continue

                if h < 3:
                    continue

                if area < 25:
                    continue

                # Don't consider the entire screenshot
                # one text region.
                if w > width * 0.80:
                    continue

                if h > height * 0.15:
                    continue

                # Very tall/narrow UI elements are unlikely
                # to be text.
                aspect = w / max(h, 1)

                if aspect < 0.35:
                    continue

                # Convert to a region.
                visual_regions.append({
                    "x1": x,
                    "y1": y,
                    "x2": x + w,
                    "y2": y + h,
                    "confidence": 100,
                    "source": "visual",
                    "text": ""
                })

        print(
            f"[PROOF] Visual regions: "
            f"{len(visual_regions)}"
        )

        # =================================================
        # STRONGER DARK-TEXT PASS
        # =================================================
        #
        # Detect darker text that is surrounded by a light
        # background. This works particularly well for
        # usernames on white/gray cards.
        # =================================================

        local_dark_mask = np.zeros(
            (height, width),
            dtype=np.uint8
        )

        # Several thresholds are combined.
        for threshold in [95, 120, 145]:

            local_mask = cv2.inRange(
                gray,
                0,
                threshold
            )

            local_dark_mask = cv2.bitwise_or(
                local_dark_mask,
                local_mask
            )

        # Connect characters horizontally.
        line_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (17, 5)
        )

        local_dark_mask = cv2.morphologyEx(
            local_dark_mask,
            cv2.MORPH_CLOSE,
            line_kernel,
            iterations=1
        )

        # Small dilation catches bold edges.
        local_dark_mask = cv2.dilate(
            local_dark_mask,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (5, 3)
            ),
            iterations=1
        )

        contours, _ = cv2.findContours(
            local_dark_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:

            x, y, w, h = cv2.boundingRect(
                contour
            )

            if w < 5:
                continue

            if h < 3:
                continue

            if w > width * 0.75:
                continue

            if h > height * 0.12:
                continue

            area = w * h

            if area < 20:
                continue

            visual_regions.append({
                "x1": x,
                "y1": y,
                "x2": x + w,
                "y2": y + h,
                "confidence": 110,
                "source": "bold_visual",
                "text": ""
            })

        # =================================================
        # COMBINE ALL DETECTIONS
        # =================================================

        all_regions = (
            raw_regions
            + character_regions
            + visual_regions
        )

        print(
            f"[PROOF] Total raw regions: "
            f"{len(all_regions)}"
        )

        if not all_regions:

            print(
                "[PROOF] Nothing detected."
            )

            return image_data

        # =================================================
        # REGION HELPERS
        # =================================================

        def region_area(region):

            return max(
                0,
                region["x2"] - region["x1"]
            ) * max(
                0,
                region["y2"] - region["y1"]
            )

        def intersection(a, b):

            x1 = max(
                a["x1"],
                b["x1"]
            )

            y1 = max(
                a["y1"],
                b["y1"]
            )

            x2 = min(
                a["x2"],
                b["x2"]
            )

            y2 = min(
                a["y2"],
                b["y2"]
            )

            if x2 <= x1 or y2 <= y1:
                return 0

            return (
                (x2 - x1)
                * (y2 - y1)
            )

        # =================================================
        # DEDUPLICATE
        # =================================================

        all_regions.sort(
            key=lambda region: (
                region["confidence"],
                region_area(region)
            ),
            reverse=True
        )

        cleaned_regions = []

        for region in all_regions:

            area = region_area(
                region
            )

            if area <= 0:
                continue

            duplicate = False

            for existing in cleaned_regions:

                overlap = intersection(
                    region,
                    existing
                )

                if overlap <= 0:
                    continue

                smaller_area = min(
                    area,
                    region_area(existing)
                )

                if smaller_area <= 0:
                    continue

                overlap_ratio = (
                    overlap
                    / smaller_area
                )

                if overlap_ratio >= 0.60:

                    duplicate = True
                    break

            if not duplicate:

                cleaned_regions.append(
                    region
                )

        print(
            f"[PROOF] Cleaned regions: "
            f"{len(cleaned_regions)}"
        )

        # =================================================
        # CREATE MASK
        # =================================================

        mask = np.zeros(
            (height, width),
            dtype=np.uint8
        )

        button_words = {
            "close",
            "cancel",
            "submit",
            "send",
            "back",
            "next",
            "open",
            "menu",
            "shop",
            "buy",
            "edit",
            "save",
            "done",
            "copy",
            "delete"
        }

        accepted = 0

        for region in cleaned_regions:

            x1 = region["x1"]
            y1 = region["y1"]
            x2 = region["x2"]
            y2 = region["y2"]

            confidence = region[
                "confidence"
            ]

            text = region.get(
                "text",
                ""
            ).lower().strip()

            rw = x2 - x1
            rh = y2 - y1

            if rw < 2 or rh < 2:
                continue

            # -------------------------------------------------
            # SMART MODE
            # -------------------------------------------------

            if not blur_everything:

                if (
                    text in button_words
                    and confidence >= 30
                ):
                    continue

                if confidence < 20:
                    continue

            # -------------------------------------------------
            # EXTRA PADDING
            # -------------------------------------------------

            if blur_everything:

                # Larger padding specifically designed
                # for bold usernames.
                pad_x = max(
                    8,
                    int(rw * 0.22)
                )

                pad_y = max(
                    8,
                    int(rh * 0.60)
                )

            else:

                pad_x = max(
                    5,
                    int(rw * 0.15)
                )

                pad_y = max(
                    5,
                    int(rh * 0.35)
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

            cv2.rectangle(
                mask,
                (bx1, by1),
                (bx2, by2),
                255,
                -1
            )

            accepted += 1

        print(
            f"[PROOF] Accepted regions: "
            f"{accepted}"
        )

        # =================================================
        # CONNECT NEARBY TEXT
        # =================================================

        if blur_everything:

            # Horizontal connection is strong because
            # usernames and highlighted text are usually
            # horizontal.
            horizontal = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (15, 5)
            )

            mask = cv2.dilate(
                mask,
                horizontal,
                iterations=1
            )

            # Expand around bold glyph edges.
            strong = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (9, 9)
            )

            mask = cv2.dilate(
                mask,
                strong,
                iterations=1
            )

        else:

            normal = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (7, 5)
            )

            mask = cv2.dilate(
                mask,
                normal,
                iterations=1
            )

        # =================================================
        # CLOSE SMALL GAPS
        # =================================================

        close_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (9, 5)
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            close_kernel,
            iterations=1
        )

        # =================================================
        # FINAL SAFETY EXPANSION
        # =================================================

        if blur_everything:

            final_kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (7, 7)
            )

            mask = cv2.dilate(
                mask,
                final_kernel,
                iterations=1
            )

        # =================================================
        # STRONG BLUR
        # =================================================

        if blur_everything:

            blur_radius = 42

        else:

            blur_radius = 25

        blurred = original.filter(
            ImageFilter.GaussianBlur(
                radius=blur_radius
            )
        )

        # =================================================
        # SOFT MASK EDGES
        # =================================================

        mask_image = Image.fromarray(
            mask,
            mode="L"
        )

        soft_mask = mask_image.filter(
            ImageFilter.GaussianBlur(
                radius=2
            )
        )

        # =================================================
        # COMPOSITE
        # =================================================

        result = Image.composite(
            blurred,
            original,
            soft_mask
        )

        # =================================================
        # SECOND BLUR
        # =================================================

        if blur_everything:

            second_blurred = result.filter(
                ImageFilter.GaussianBlur(
                    radius=14
                )
            )

            result = Image.composite(
                second_blurred,
                result,
                soft_mask
            )

        # =================================================
        # OUTPUT
        # =================================================

        output = io.BytesIO()

        result.save(
            output,
            format="PNG"
        )

        output.seek(0)

        print(
            "[PROOF] Hybrid blur finished successfully."
        )

        return output.getvalue()

    except Exception as e:

        print(
            f"[PROOF] Hybrid blur error: {e}"
        )

        # If image processing fails, don't break
        # the Discord command.
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
# SAY / ANNOUNCEMENT
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

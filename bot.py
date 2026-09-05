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
    "welcome_goodbye_channel_id": int(os.getenv("WELCOME_GOODBYE_CHANNEL_ID", 0)) or None,
    "proof_channel_id": int(os.getenv("PROOF_CHANNEL_ID", 0)) or None,
    "staff_role_id": int(os.getenv("STAFF_ROLE_ID", 0)) or None,
    "customer_role_id": int(os.getenv("CUSTOMER_ROLE_ID", 1545438540362555463)) or 1545438540362555463,
    "blur_everything": bool(os.getenv("BLUR_EVERYTHING", "true").lower() == "true")
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

bot = commands.Bot(command_prefix="!", intents=intents)


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
    embed.set_footer(text="୨୧ ali's adm house • Customer Shop ♡")
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
        role = interaction.guild.get_role(int(staff_role_id))
        if role and role in interaction.user.roles:
            return True

    return interaction.user.guild_permissions.manage_channels


# =========================================================
# PROOF BLUR
# =========================================================
#
# IMPORTANT:
# This detector is card-aware.
#
# It first finds the WHITE/LIGHT proof cards, then ONLY scans
# the upper text area of each card. This prevents:
#
# - green "View" from being blurred
# - orange "Report" from being blurred
# - gray background from being blurred
# - black refresh icon from being blurred
# - item icons from being blurred
#
# It specifically looks for a BLACK/DARK, BOLD, HORIZONTAL
# text line such as:
#
#     Arthurbns29
#     mc444z
#     SavvyS122994
#
# =========================================================

def blur_proof_text(image_data: bytes, blur_everything: bool = True) -> bytes:

    try:
        print("[PROOF] Starting card-aware black username scan...")

        original = Image.open(io.BytesIO(image_data)).convert("RGB")
        width, height = original.size

        if width <= 0 or height <= 0:
            return image_data

        rgb = np.array(original)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        # -------------------------------------------------
        # 1. FIND LIGHT/WHITE CARDS
        # -------------------------------------------------

        # The cards in the supplied template are much lighter
        # than the gray page background.
        light_mask = cv2.inRange(gray, 215, 255)

        # Fill small gaps caused by rounded corners/text.
        light_mask = cv2.morphologyEx(
            light_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)),
            iterations=2
        )

        light_mask = cv2.morphologyEx(
            light_mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
            iterations=1
        )

        contours, _ = cv2.findContours(
            light_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        cards = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h

            # A proof card is a reasonably wide rectangle.
            if w < max(100, int(width * 0.25)):
                continue

            if h < 45:
                continue

            if area < width * height * 0.015:
                continue

            if w > width * 0.75:
                continue

            if h > height * 0.70:
                continue

            aspect = w / max(h, 1)

            if aspect < 1.4:
                continue

            # Verify that the inside is actually light.
            ix1 = min(width - 1, x + 5)
            iy1 = min(height - 1, y + 5)
            ix2 = max(ix1 + 1, min(width, x + w - 5))
            iy2 = max(iy1 + 1, min(height, y + h - 5))

            inside = gray[iy1:iy2, ix1:ix2]

            if inside.size == 0:
                continue

            light_ratio = np.mean(inside >= 210)

            if light_ratio < 0.45:
                continue

            cards.append((x, y, w, h))

        # Merge cards that overlap or are almost identical.
        merged_cards = []

        for card in sorted(cards, key=lambda c: (c[1], c[0])):
            x, y, w, h = card
            x2 = x + w
            y2 = y + h

            merged = False

            for i, old in enumerate(merged_cards):
                ox, oy, ow, oh = old
                ox2 = ox + ow
                oy2 = oy + oh

                overlap_x = min(x2, ox2) - max(x, ox)
                overlap_y = min(y2, oy2) - max(y, oy)

                close = (
                    abs(x - ox) <= 8
                    and abs(y - oy) <= 8
                )

                if overlap_x > 0 and overlap_y > 0 or close:
                    nx1 = min(x, ox)
                    ny1 = min(y, oy)
                    nx2 = max(x2, ox2)
                    ny2 = max(y2, oy2)
                    merged_cards[i] = (
                        nx1,
                        ny1,
                        nx2 - nx1,
                        ny2 - ny1
                    )
                    merged = True
                    break

            if not merged:
                merged_cards.append(card)

        cards = merged_cards

        print(f"[PROOF] Light cards found: {len(cards)}")

        # -------------------------------------------------
        # 2. FALLBACK CARD DETECTION
        # -------------------------------------------------
        #
        # If anti-aliasing prevents the white-card detector
        # from finding a card, look for large bright areas.
        # This still stays restricted to the top text zone.
        # -------------------------------------------------

        if not cards:
            print("[PROOF] No cards found with primary detector; using fallback.")

            fallback = cv2.threshold(
                gray,
                195,
                255,
                cv2.THRESH_BINARY
            )[1]

            fallback = cv2.morphologyEx(
                fallback,
                cv2.MORPH_CLOSE,
                cv2.getStructuringElement(cv2.MORPH_RECT, (25, 15)),
                iterations=2
            )

            contours, _ = cv2.findContours(
                fallback,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)

                if w < width * 0.25:
                    continue

                if h < 45:
                    continue

                if w / max(h, 1) < 1.4:
                    continue

                cards.append((x, y, w, h))

        # -------------------------------------------------
        # 3. SCAN ONLY THE NAME AREA
        # -------------------------------------------------

        name_regions = []

        for x, y, w, h in cards:

            # The username is near the very top of the card.
            #
            # Example:
            # card top
            #   ↓
            #   Arthurbns29   <-- target
            #   Sep 5, 2026
            #   10:30 PM
            #   [View] [Report]
            #
            # We deliberately stop before the buttons.

            top_margin = max(4, int(h * 0.035))
            band_height = min(
                max(34, int(h * 0.34)),
                72
            )

            nx1 = max(0, x + 8)
            ny1 = max(0, y + top_margin)
            nx2 = min(width, x + int(w * 0.62))
            ny2 = min(height, y + band_height)

            if nx2 <= nx1 or ny2 <= ny1:
                continue

            roi = gray[ny1:ny2, nx1:nx2]

            if roi.size == 0:
                continue

            # -------------------------------------------------
            # BLACK/DARK PIXEL MASK
            # -------------------------------------------------

            # Usernames are genuinely dark. Date/time is lower
            # and therefore normally outside this region.
            dark = cv2.inRange(
                roi,
                0,
                105
            )

            # Remove tiny noise.
            dark = cv2.morphologyEx(
                dark,
                cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)),
                iterations=1
            )

            # Connect letters in the username.
            grouped = cv2.dilate(
                dark,
                cv2.getStructuringElement(cv2.MORPH_RECT, (5, 2)),
                iterations=1
            )

            grouped = cv2.morphologyEx(
                grouped,
                cv2.MORPH_CLOSE,
                cv2.getStructuringElement(cv2.MORPH_RECT, (13, 3)),
                iterations=2
            )

            text_contours, _ = cv2.findContours(
                grouped,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            local_candidates = []

            for contour in text_contours:

                cx, cy, cw, ch = cv2.boundingRect(contour)

                if cw < 15:
                    continue

                if ch < 7:
                    continue

                if ch > 45:
                    continue

                if cw > roi.shape[1] * 0.95:
                    continue

                aspect = cw / max(ch, 1)

                # Username-like horizontal shape.
                if aspect < 1.4:
                    continue

                box = roi[
                    max(0, cy):min(roi.shape[0], cy + ch),
                    max(0, cx):min(roi.shape[1], cx + cw)
                ]

                if box.size == 0:
                    continue

                dark_ratio = np.mean(box <= 120)

                # Bold text should have enough dark pixels.
                if dark_ratio < 0.035:
                    continue

                # Check the surrounding pixels are substantially
                # lighter than the text.
                pad = 4

                sx1 = max(0, cx - pad)
                sy1 = max(0, cy - pad)
                sx2 = min(roi.shape[1], cx + cw + pad)
                sy2 = min(roi.shape[0], cy + ch + pad)

                surrounding = roi[sy1:sy2, sx1:sx2]

                if surrounding.size == 0:
                    continue

                surrounding_mean = float(np.mean(surrounding))
                box_mean = float(np.mean(box))

                if surrounding_mean < 145:
                    continue

                if surrounding_mean - box_mean < 25:
                    continue

                local_candidates.append(
                    (
                        cx,
                        cy,
                        cx + cw,
                        cy + ch,
                        dark_ratio
                    )
                )

            # -------------------------------------------------
            # 4. OCR FALLBACK INSIDE THE NAME BAND ONLY
            # -------------------------------------------------

            # OCR is NOT run over the whole screenshot anymore.
            # It is restricted to the top of a detected card.
            #
            # This prevents OCR from selecting View/Report,
            # dates, icons, and the refresh symbol.

            try:
                up = cv2.resize(
                    roi,
                    None,
                    fx=3,
                    fy=3,
                    interpolation=cv2.INTER_CUBIC
                )

                ocr_data = pytesseract.image_to_data(
                    up,
                    config="--oem 3 --psm 7",
                    output_type=pytesseract.Output.DICT
                )

                texts = ocr_data.get("text", [])
                lefts = ocr_data.get("left", [])
                tops = ocr_data.get("top", [])
                widths = ocr_data.get("width", [])
                heights = ocr_data.get("height", [])
                confs = ocr_data.get("conf", [])

                for i, text in enumerate(texts):

                    text = str(text).strip()

                    if not text:
                        continue

                    try:
                        conf = float(confs[i])
                    except Exception:
                        conf = 0

                    if conf < 15:
                        continue

                    ox = int(lefts[i] / 3)
                    oy = int(tops[i] / 3)
                    ow = int(widths[i] / 3)
                    oh = int(heights[i] / 3)

                    if ow < 15 or oh < 6:
                        continue

                    ox2 = min(roi.shape[1], ox + ow)
                    oy2 = min(roi.shape[0], oy + oh)

                    if ox2 <= ox or oy2 <= oy:
                        continue

                    ocr_box = roi[oy:oy2, ox:ox2]

                    if ocr_box.size == 0:
                        continue

                    dark_ratio = np.mean(ocr_box <= 125)

                    if dark_ratio < 0.025:
                        continue

                    local_candidates.append(
                        (
                            ox,
                            oy,
                            ox2,
                            oy2,
                            dark_ratio
                        )
                    )

            except Exception as e:
                print(f"[PROOF] OCR fallback error: {e}")

            # -------------------------------------------------
            # 5. MERGE NAME PIECES
            # -------------------------------------------------

            if not local_candidates:
                continue

            local_candidates.sort(key=lambda r: (r[1], r[0]))

            # Start with each candidate and merge pieces that
            # belong to the same horizontal username.
            merged = []

            for candidate in local_candidates:

                cx1, cy1, cx2, cy2, score = candidate

                found = False

                for j, current in enumerate(merged):

                    mx1, my1, mx2, my2 = current

                    horizontal_gap = max(
                        0,
                        max(mx1 - cx2, cx1 - mx2)
                    )

                    vertical_gap = max(
                        0,
                        max(my1 - cy2, cy1 - my2)
                    )

                    height1 = cy2 - cy1
                    height2 = my2 - my1

                    similar_height = (
                        min(height1, height2)
                        >= max(4, int(max(height1, height2) * 0.45))
                    )

                    if (
                        horizontal_gap <= 14
                        and vertical_gap <= 10
                        and similar_height
                    ):
                        merged[j] = (
                            min(mx1, cx1),
                            min(my1, cy1),
                            max(mx2, cx2),
                            max(my2, cy2)
                        )
                        found = True
                        break

                if not found:
                    merged.append(
                        (cx1, cy1, cx2, cy2)
                    )

            # -------------------------------------------------
            # 6. ACCEPT ONLY THE MOST USERNAME-LIKE LINE
            # -------------------------------------------------

            for mx1, my1, mx2, my2 in merged:

                mw = mx2 - mx1
                mh = my2 - my1

                if mw < 18 or mh < 6:
                    continue

                if mw / max(mh, 1) < 1.5:
                    continue

                # Convert back to full-image coordinates.
                fx1 = nx1 + mx1
                fy1 = ny1 + my1
                fx2 = nx1 + mx2
                fy2 = ny1 + my2

                # Extra verification against original image.
                check = gray[
                    max(0, fy1):min(height, fy2),
                    max(0, fx1):min(width, fx2)
                ]

                if check.size == 0:
                    continue

                black_ratio = np.mean(check <= 125)

                if black_ratio < 0.025:
                    continue

                # Only accept text in the upper portion of the
                # card. This is the most important protection
                # against dates, buttons, and icons.
                relative_y = fy1 - y

                if relative_y > min(72, int(h * 0.40)):
                    continue

                name_regions.append(
                    (
                        fx1,
                        fy1,
                        fx2,
                        fy2
                    )
                )

        print(f"[PROOF] Username regions found: {len(name_regions)}")

        # -------------------------------------------------
        # 7. DEDUPLICATE / MERGE FINAL REGIONS
        # -------------------------------------------------

        final_regions = []

        for region in name_regions:

            x1, y1, x2, y2 = region

            merged = False

            for i, old in enumerate(final_regions):

                ox1, oy1, ox2, oy2 = old

                overlap_x = min(x2, ox2) - max(x1, ox1)
                overlap_y = min(y2, oy2) - max(y1, oy1)

                if overlap_x > 0 and overlap_y > 0:
                    final_regions[i] = (
                        min(x1, ox1),
                        min(y1, oy1),
                        max(x2, ox2),
                        max(y2, oy2)
                    )
                    merged = True
                    break

            if not merged:
                final_regions.append(region)

        # -------------------------------------------------
        # 8. BUILD SMALL LOCAL MASKS
        # -------------------------------------------------

        mask = np.zeros(
            (height, width),
            dtype=np.uint8
        )

        accepted = 0

        for x1, y1, x2, y2 in final_regions:

            rw = x2 - x1
            rh = y2 - y1

            if rw < 18 or rh < 6:
                continue

            # Padding is deliberately small.
            # We want the name covered, but NOT the date.
            pad_x = max(5, int(rw * 0.08))
            pad_y = max(4, int(rh * 0.45))

            bx1 = max(0, x1 - pad_x)
            by1 = max(0, y1 - pad_y)
            bx2 = min(width, x2 + pad_x)
            by2 = min(height, y2 + pad_y)

            cv2.rectangle(
                mask,
                (bx1, by1),
                (bx2, by2),
                255,
                -1
            )

            accepted += 1

        print(f"[PROOF] Final username regions: {accepted}")

        if accepted == 0:
            print("[PROOF] No username text found; returning original.")
            return image_data

        # Tiny expansion for anti-aliased edges.
        mask = cv2.dilate(
            mask,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (3, 3)
            ),
            iterations=1
        )

        # -------------------------------------------------
        # 9. STRONG LOCAL BLUR
        # -------------------------------------------------

        blurred = original.filter(
            ImageFilter.GaussianBlur(radius=32)
        )

        mask_image = Image.fromarray(mask, mode="L")

        # Keep edges reasonably hard so the entire name is hidden.
        mask_image = mask_image.filter(
            ImageFilter.GaussianBlur(radius=0.7)
        )

        result = Image.composite(
            blurred,
            original,
            mask_image
        )

        # One extra pass only inside the mask.
        extra_blur = result.filter(
            ImageFilter.GaussianBlur(radius=10)
        )

        result = Image.composite(
            extra_blur,
            result,
            mask_image
        )

        output = io.BytesIO()
        result.save(output, format="PNG")
        output.seek(0)

        print("[PROOF] Black username text blurred successfully.")

        return output.getvalue()

    except Exception as e:
        print(f"[PROOF] Blur error: {e}")
        return image_data


# =========================================================
# CHANNEL RENAME QUEUE
# =========================================================

pending_renames = {}

async def process_channel_renames():
    await bot.wait_until_ready()

    while not bot.is_closed():

        if pending_renames:

            items = list(pending_renames.items())

            for channel_id, new_name in items:

                channel = bot.get_channel(channel_id)

                if channel is None:
                    pending_renames.pop(channel_id, None)
                    continue

                try:
                    await channel.edit(name=new_name)
                    pending_renames.pop(channel_id, None)
                    await asyncio.sleep(2)

                except discord.HTTPException as e:

                    if e.status == 429:
                        retry_after = getattr(e, "retry_after", 5)
                        print(f"Rate limited. Retrying in {retry_after}s")
                        await asyncio.sleep(retry_after)

                    else:
                        print(f"Channel rename error: {e}")
                        pending_renames.pop(channel_id, None)

        await asyncio.sleep(5)


# =========================================================
# MEMBER JOIN
# =========================================================

@bot.event
async def on_member_join(member):
    try:
        customer_role_id = config.get("customer_role_id")

        if customer_role_id:
            role = member.guild.get_role(int(customer_role_id))

            if role:
                try:
                    await member.add_roles(
                        role,
                        reason="Automatic customer role"
                    )
                except Exception as e:
                    print(f"Customer role error: {e}")

        channel_id = config.get("welcome_goodbye_channel_id")

        if not channel_id:
            return

        channel = member.guild.get_channel(int(channel_id))

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

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="Customer",
            value=member.mention,
            inline=True
        )

        embed.add_field(
            name="Member Count",
            value=str(member.guild.member_count),
            inline=True
        )

        await channel.send(
            content=member.mention,
            embed=embed
        )

    except Exception as e:
        print(f"Join event error: {e}")


# =========================================================
# MEMBER LEAVE
# =========================================================

@bot.event
async def on_member_remove(member):
    try:
        channel_id = config.get("welcome_goodbye_channel_id")

        if not channel_id:
            return

        channel = member.guild.get_channel(int(channel_id))

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

        embed.set_thumbnail(url=member.display_avatar.url)

        await channel.send(embed=embed)

    except Exception as e:
        print(f"Leave event error: {e}")


# =========================================================
# TICKET VIEW
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

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

        category_id = config.get("ticket_category_id")

        if not category_id:
            await interaction.response.send_message(
                "Tickets are not configured yet.",
                ephemeral=True
            )
            return

        category = interaction.guild.get_channel(int(category_id))

        if not category:
            await interaction.response.send_message(
                "The ticket category could not be found.",
                ephemeral=True
            )
            return

        for channel in category.channels:
            if channel.topic == f"ali_adm_ticket:{interaction.user.id}":
                await interaction.response.send_message(
                    f"You already have an open ticket: {channel.mention}",
                    ephemeral=True
                )
                return

        overwrites = {
            interaction.guild.default_role:
                discord.PermissionOverwrite(view_channel=False),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        staff_role_id = config.get("staff_role_id")

        if staff_role_id:
            staff_role = interaction.guild.get_role(int(staff_role_id))

            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        channel_name = f"ticket-{interaction.user.name}"[:90]

        try:
            ticket = await interaction.guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"ali_adm_ticket:{interaction.user.id}"
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
            await interaction.response.send_message(
                "This can only be used in a server.",
                ephemeral=True
            )
            return

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
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
                await channel.delete(reason="Ticket closed by staff")
            except Exception:
                pass

            return

        vouch_channel_id = config.get("vouch_channel_id")

        if not vouch_channel_id:
            await interaction.response.send_message(
                "Vouch channel is not configured.",
                ephemeral=True
            )
            return

        vouch_channel = interaction.guild.get_channel(int(vouch_channel_id))

        if not vouch_channel:
            await interaction.response.send_message(
                "Vouch channel could not be found.",
                ephemeral=True
            )
            return

        has_vouched = False

        try:
            async for message in vouch_channel.history(limit=1000):

                if message.author.id != bot.user.id:
                    continue

                if (
                    interaction.user.mention in message.content
                    or str(interaction.user.id) in message.content
                ):
                    has_vouched = True
                    break

        except Exception as e:
            print(f"Vouch check error: {e}")

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
            await channel.delete(reason="Ticket closed")
        except Exception:
            pass


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    if not getattr(bot, "_persistent_views_added", False):
        bot.add_view(TicketView())
        bot.add_view(CloseTicketView())
        bot._persistent_views_added = True

    if not getattr(bot, "_rename_task_started", False):
        asyncio.create_task(process_channel_renames())
        bot._rename_task_started = True

    if not getattr(bot, "_commands_synced", False):

        try:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} slash commands.")
            bot._commands_synced = True

        except Exception as e:
            print(f"Slash command sync error: {e}")


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

    await panel_channel.send(embed=embed, view=TicketView())

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
async def ticketpanel(interaction: discord.Interaction):

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
async def ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

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
@app_commands.describe(image="Proof image")
async def proof(
    interaction: discord.Interaction,
    image: discord.Attachment
):

    proof_channel_id = config.get("proof_channel_id")

    if not proof_channel_id:
        await interaction.response.send_message(
            "Proof channel is not configured.",
            ephemeral=True
        )
        return

    proof_channel = interaction.guild.get_channel(int(proof_channel_id))

    if not proof_channel:
        await interaction.response.send_message(
            "Proof channel could not be found.",
            ephemeral=True
        )
        return

    valid_extensions = (".png", ".jpg", ".jpeg", ".webp")
    content_type = (image.content_type or "").lower()
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

    await interaction.response.defer(ephemeral=True)

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

        print(f"Proof command error: {e}")

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
@app_commands.describe(message="Your vouch message")
async def vouch(
    interaction: discord.Interaction,
    message: str
):

    vouch_channel_id = config.get("vouch_channel_id")

    if not vouch_channel_id:
        await interaction.response.send_message(
            "Vouch channel is not configured.",
            ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(int(vouch_channel_id))

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
async def vouchcount(interaction: discord.Interaction):

    vouch_channel_id = config.get("vouch_channel_id")

    if not vouch_channel_id:
        await interaction.response.send_message(
            "Vouch channel is not configured.",
            ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(int(vouch_channel_id))

    if not channel:
        await interaction.response.send_message(
            "Vouch channel could not be found.",
            ephemeral=True
        )
        return

    count = 0

    try:
        async for message in channel.history(limit=None):
            if bot.user and message.author.id == bot.user.id:
                count += 1
    except Exception as e:
        print(f"Vouch count error: {e}")

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
@app_commands.describe(status="Shop status")
@app_commands.choices(
    status=[
        app_commands.Choice(name="Available", value="available"),
        app_commands.Choice(name="Busy", value="busy"),
        app_commands.Choice(name="Closed", value="closed")
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

    status_channel_id = config.get("status_channel_id")

    if not status_channel_id:
        await interaction.response.send_message(
            "Status channel is not configured.",
            ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(int(status_channel_id))

    if not channel:
        await interaction.response.send_message(
            "Status channel could not be found.",
            ephemeral=True
        )
        return

    statuses = {
        "available": ("🟢", "𝘢𝘷𝘢𝘪𝘭𝘢𝘣𝘭𝘦", GREEN),
        "busy": ("🔴", "𝘣𝘶𝘴𝘺", RED),
        "closed": ("⚪", "𝘤𝘭𝘰𝘴𝘦𝘥", GRAY)
    }

    emoji, text, color = statuses[status.value]

    embed = styled_embed(
        f"{emoji}・𝘴𝘩𝘰𝘱 𝘴𝘵𝘢𝘵𝘶𝘴",
        f"""
Our shop is currently:

**{text}**

♡ ali's adm house
        """,
        color
    )

    await channel.send(embed=embed)

    rename_map = {
        "available": "🟢-available",
        "busy": "🔴-busy",
        "closed": "⚪-closed"
    }

    pending_renames[channel.id] = rename_map[status.value]

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

    content = role.mention if role else None

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
        and interaction.guild.owner_id != interaction.user.id
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
        await user.send(embed=embed)
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
@app_commands.describe(amount="Number of messages to delete")
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

    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "This command can only be used in a text channel.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await interaction.channel.purge(limit=amount)

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
        and interaction.guild.owner_id != interaction.user.id
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
@app_commands.describe(user="Member to mute")
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
        and interaction.guild.owner_id != interaction.user.id
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
        and interaction.guild.owner_id != interaction.user.id
    ):
        await interaction.response.send_message(
            "You can't ban someone with an equal or higher role.",
            ephemeral=True
        )
        return

    try:
        await interaction.guild.ban(user, reason=reason)

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
        and interaction.guild.owner_id != interaction.user.id
    ):
        await interaction.response.send_message(
            "You can't kick someone with an equal or higher role.",
            ephemeral=True
        )
        return

    try:
        await interaction.guild.kick(user, reason=reason)

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

    if not isinstance(channel, discord.TextChannel):
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

    if not isinstance(channel, discord.TextChannel):
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

@bot.command(name="vouch")
async def prefix_vouch(ctx, *, message: str):

    if not ctx.guild:
        return

    vouch_channel_id = config.get("vouch_channel_id")

    if not vouch_channel_id:
        return

    channel = ctx.guild.get_channel(int(vouch_channel_id))

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
async def on_command_error(ctx, error):

    if isinstance(error, commands.CommandNotFound):
        return

    print(f"Prefix command error: {error}")


# =========================================================
# SLASH COMMAND ERROR
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error
):

    print(f"Slash command error: {error}")

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
        print(f"Could not send slash error: {e}")


# =========================================================
# START
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set.")

keep_alive()
bot.run(TOKEN)

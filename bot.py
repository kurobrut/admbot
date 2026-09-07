import os
import json
import io
import asyncio
import traceback
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

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.json")


def environment_int(name, default=None):
    """Read an integer environment value without crashing startup."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[CONFIG] Ignoring invalid {name}: {raw!r}")
        return default

CONFIG_ENV_KEYS = {
    "panel_channel_id": "PANEL_CHANNEL_ID",
    "ticket_category_id": "TICKET_CATEGORY_ID",
    "vouch_channel_id": "VOUCH_CHANNEL_ID",
    "status_channel_id": "STATUS_CHANNEL_ID",
    "welcome_goodbye_channel_id": "WELCOME_GOODBYE_CHANNEL_ID",
    "proof_channel_id": "PROOF_CHANNEL_ID",
    "staff_role_id": "STAFF_ROLE_ID",
    "customer_role_id": "CUSTOMER_ROLE_ID",
}

DEFAULT_CONFIG = {
    "panel_channel_id": environment_int("PANEL_CHANNEL_ID"),
    "ticket_category_id": environment_int("TICKET_CATEGORY_ID"),
    "vouch_channel_id": environment_int("VOUCH_CHANNEL_ID"),
    "status_channel_id": environment_int("STATUS_CHANNEL_ID"),
    "welcome_goodbye_channel_id": environment_int("WELCOME_GOODBYE_CHANNEL_ID"),
    "proof_channel_id": environment_int("PROOF_CHANNEL_ID"),
    "staff_role_id": environment_int("STAFF_ROLE_ID"),
    "customer_role_id": environment_int(
        "CUSTOMER_ROLE_ID",
        1545438540362555463
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


def apply_environment_config(data):
    """Apply persistent hosting environment variables over local config."""
    changed = False
    for config_key, env_key in CONFIG_ENV_KEYS.items():
        raw = os.getenv(env_key)
        if raw is None or not raw.strip():
            continue
        try:
            value = int(raw)
        except ValueError:
            print(f"[CONFIG] Ignoring invalid {env_key}: {raw!r}")
            continue
        if data.get(config_key) != value:
            data[config_key] = value
            changed = True
    return changed


if apply_environment_config(config):
    save_config(config)


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
        text="ali's adm house • Customer Shop ♡"
    )

    return embed


# =========================================================
# ADVANCED PROOF TEXT BLUR
# =========================================================

def blur_region(
    image,
    x1,
    y1,
    x2,
    y2,
    radius=7
):

    width, height = image.size

    x1 = max(
        0,
        min(width, int(x1))
    )

    y1 = max(
        0,
        min(height, int(y1))
    )

    x2 = max(
        0,
        min(width, int(x2))
    )

    y2 = max(
        0,
        min(height, int(y2))
    )

    if x2 <= x1 or y2 <= y1:
        return

    crop = image.crop(
        (
            x1,
            y1,
            x2,
            y2
        )
    )

    crop = crop.filter(
        ImageFilter.GaussianBlur(
            radius=radius
        )
    )

    image.paste(
        crop,
        (
            x1,
            y1
        )
    )


WATERMARK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "watermark.png"
)
_watermark_cache = None


def load_watermark():
    global _watermark_cache

    if _watermark_cache is not None:
        return _watermark_cache.copy()

    try:
        watermark = Image.open(WATERMARK_PATH).convert("RGBA")

        watermark_pixels = np.array(watermark)
        black_background = np.max(
            watermark_pixels[:, :, :3],
            axis=2
        ) < 35
        watermark_pixels[black_background, 3] = 0
        watermark_pixels[~black_background, 3] = 255
        watermark = Image.fromarray(watermark_pixels, "RGBA")

        if watermark.width <= 0 or watermark.height <= 0:
            return None

        _watermark_cache = watermark.copy()
        return watermark
    except (OSError, ValueError) as error:
        print(f"[PROOF] Could not load watermark: {error}")
        return None


def apply_watermark(image):
    watermark = load_watermark()
    if watermark is None:
        return image

    width, height = image.size
    target_width = max(1, int(width * 0.30))
    scale = target_width / watermark.width
    watermark_size = (
        max(1, int(watermark.width * scale)),
        max(1, int(watermark.height * scale))
    )
    watermark = watermark.resize(watermark_size, Image.Resampling.LANCZOS)

    base = image.convert("RGBA")
    position = (
        (width - watermark.width) // 2,
        (height - watermark.height) // 2
    )
    base.alpha_composite(watermark, dest=position)
    return base


def is_date_or_time(text):

    text_lower = text.lower().strip()

    if not text_lower:
        return True

    if ":" in text_lower:
        return True

    if "/" in text_lower:
        return True

    months = [
        "jan", "january", "feb", "february", "mar", "march",
        "apr", "april", "may", "jun", "june", "jul", "july",
        "aug", "august", "sep", "sept", "september", "oct",
        "october", "nov", "november", "dec", "december"
    ]

    for month in months:
        if month in text_lower:
            return True

    if text_lower.replace(",", "").replace(".", "").isdigit():
        return True

    return False


def is_button_text(text):

    text_lower = text.lower().strip()

    ignored = {
        "view", "report", "refresh", "buy",
        "cancel", "confirm", "close"
    }

    return text_lower in ignored


def calculate_dark_ratio(
    gray,
    x1,
    y1,
    x2,
    y2
):

    h, w = gray.shape

    x1 = max(0, min(w, int(x1)))
    y1 = max(0, min(h, int(y1)))
    x2 = max(0, min(w, int(x2)))
    y2 = max(0, min(h, int(y2)))

    if x2 <= x1 or y2 <= y1:
        return 0

    roi = gray[y1:y2, x1:x2]

    if roi.size == 0:
        return 0

    dark_pixels = np.sum(roi < 145)

    return dark_pixels / roi.size


class ProofProcessingError(RuntimeError):
    """Raised when a proof cannot be safely blurred."""


def blur_proof_text(image_data: bytes) -> bytes:

    try:
        print("[PROOF] Starting updated card-by-card username blur...")

        original = Image.open(io.BytesIO(image_data)).convert("RGB")
        width, height = original.size

        if width <= 0 or height <= 0:
            raise ProofProcessingError(
                "No proof cards were detected; refusing to send an unblurred image."
            )

        rgb = np.array(original)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        left_limit = min(width, max(250, int(width * 0.68)))
        light = cv2.inRange(gray, 185, 255)

        card_mask = cv2.morphologyEx(
            light,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13)),
            iterations=2
        )

        card_mask[:, left_limit:] = 0

        contours, _ = cv2.findContours(
            card_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        cards = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)

            if w < max(160, int(width * 0.30)):
                continue
            if h < 45:
                continue
            if w > int(width * 0.68):
                continue
            if w / max(h, 1) < 1.5:
                continue

            ix1 = max(0, x + 5)
            iy1 = max(0, y + 5)
            ix2 = min(width, x + w - 5)
            iy2 = min(height, y + h - 5)

            if ix2 <= ix1 or iy2 <= iy1:
                continue

            inside = gray[iy1:iy2, ix1:ix2]

            if inside.size == 0:
                continue

            if float(np.mean(inside >= 185)) < 0.40:
                continue

            cards.append((x, y, w, h))

        projection = (light[:, :left_limit] > 0).mean(axis=1)

        runs = []
        run_start = None

        for yy, density in enumerate(projection):
            active = density >= 0.50

            if active and run_start is None:
                run_start = yy
            elif not active and run_start is not None:
                if yy - run_start >= 20:
                    runs.append((run_start, yy))
                run_start = None

        if run_start is not None and height - run_start >= 20:
            runs.append((run_start, height))

        for ry1, ry2 in runs:
            span = gray[ry1:ry2, :left_limit]

            if span.size == 0:
                continue

            col_density = (span >= 185).mean(axis=0)
            active_cols = np.where(col_density >= 0.35)[0]

            if active_cols.size == 0:
                continue

            x1 = int(active_cols.min())
            x2 = int(active_cols.max()) + 1
            rw = x2 - x1

            if rw < max(160, int(width * 0.30)):
                continue

            cards.append((x1, ry1, rw, max(45, ry2 - ry1)))

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

                same_card = (
                    overlap_x > max(20, int(min(w, ow) * 0.45))
                    and overlap_y > 0
                )

                close_same_card = (
                    abs(x - ox) <= 15
                    and abs(y - oy) <= 15
                    and abs(w - ow) <= 25
                )

                if same_card or close_same_card:
                    merged_cards[i] = (
                        min(x, ox),
                        min(y, oy),
                        max(x2, ox2) - min(x, ox),
                        max(y2, oy2) - min(y, oy)
                    )
                    merged = True
                    break

            if not merged:
                merged_cards.append(card)

        cards = sorted(merged_cards, key=lambda c: (c[1], c[0]))

        if not cards:
            raise ProofProcessingError(
                "No proof cards were detected; refusing to send an unblurred image."
            )

        username_regions = []

        for card_index, (x, y, w, h) in enumerate(cards, 1):
            band_top = max(0, y + 5)
            band_bottom = min(height, y + min(58, max(38, int(h * 0.42))))
            band_left = max(0, x + 8)
            band_right = min(width, x + int(w * 0.60))

            if band_right <= band_left or band_bottom <= band_top:
                continue

            roi = gray[band_top:band_bottom, band_left:band_right]

            if roi.size == 0:
                continue

            dark = cv2.inRange(roi, 0, 135)
            dark = cv2.morphologyEx(
                dark,
                cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)),
                iterations=1
            )

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

            contours, _ = cv2.findContours(
                grouped,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            candidates = []

            for contour in contours:
                cx, cy, cw, ch = cv2.boundingRect(contour)

                if cw < 15 or ch < 6 or ch > 30:
                    continue
                if cw > roi.shape[1] * 0.95:
                    continue
                if cw / max(ch, 1) < 1.5:
                    continue

                box = roi[
                    max(0, cy):min(roi.shape[0], cy + ch),
                    max(0, cx):min(roi.shape[1], cx + cw)
                ]

                if box.size == 0:
                    continue

                dark_ratio = float(np.mean(box <= 135))

                if dark_ratio < 0.025:
                    continue

                pad = 5
                sx1 = max(0, cx - pad)
                sy1 = max(0, cy - pad)
                sx2 = min(roi.shape[1], cx + cw + pad)
                sy2 = min(roi.shape[0], cy + ch + pad)

                surrounding = roi[sy1:sy2, sx1:sx2]

                if surrounding.size == 0 or float(np.mean(surrounding)) < 135:
                    continue

                candidates.append((cx, cy, cx + cw, cy + ch, dark_ratio))

            try:
                up = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
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

                    if not text or is_date_or_time(text) or is_button_text(text):
                        continue

                    try:
                        conf = float(confs[i])
                    except Exception:
                        conf = 0

                    if conf < 10:
                        continue

                    ox = int(lefts[i] / 3)
                    oy = int(tops[i] / 3)
                    ow = int(widths[i] / 3)
                    oh = int(heights[i] / 3)

                    if ow < 15 or oh < 5:
                        continue

                    ox2 = min(roi.shape[1], ox + ow)
                    oy2 = min(roi.shape[0], oy + oh)

                    if ox2 <= ox or oy2 <= oy:
                        continue

                    ocr_box = roi[oy:oy2, ox:ox2]

                    if ocr_box.size == 0:
                        continue

                    dark_ratio = float(np.mean(ocr_box <= 140))

                    if dark_ratio < 0.02:
                        continue

                    candidates.append((ox, oy, ox2, oy2, dark_ratio))

            except Exception as error:
                print(f"[PROOF] OCR fallback error on card {card_index}: {error}")

            if not candidates:
                username_regions.append(
                    (band_left, band_top, band_right, min(height, y + 38))
                )
                continue

            candidates.sort(key=lambda item: (item[1], item[0]))
            merged = []

            for (cx1, cy1, cx2, cy2, score) in candidates:
                found = False

                for j, current in enumerate(merged):
                    mx1, my1, mx2, my2 = current
                    horizontal_gap = max(0, max(mx1 - cx2, cx1 - mx2))
                    vertical_gap = max(0, max(my1 - cy2, cy1 - my2))

                    if horizontal_gap <= 16 and vertical_gap <= 9:
                        merged[j] = (
                            min(mx1, cx1),
                            min(my1, cy1),
                            max(mx2, cx2),
                            max(my2, cy2)
                        )
                        found = True
                        break

                if not found:
                    merged.append((cx1, cy1, cx2, cy2))

            best = None
            best_score = -1

            for (mx1, my1, mx2, my2) in merged:
                mw = mx2 - mx1
                mh = my2 - my1

                if mw < 18 or mh < 5 or mw / max(mh, 1) < 1.5:
                    continue

                full_y = band_top + my1

                if full_y > y + 58:
                    continue

                check = gray[
                    max(0, band_top + my1):min(height, band_top + my2),
                    max(0, band_left + mx1):min(width, band_left + mx2)
                ]

                if check.size == 0:
                    continue

                darkness = float(np.mean(check <= 140))

                if darkness < 0.02:
                    continue

                score = mw + darkness * 100 - (my1 * 0.5)

                if score > best_score:
                    best_score = score
                    best = (
                        band_left + mx1,
                        band_top + my1,
                        band_left + mx2,
                        band_top + my2
                    )

            if best is None:
                best = (
                    band_left,
                    band_top,
                    band_right,
                    min(height, y + 38)
                )

            username_regions.append(best)

        if not username_regions:
            raise ProofProcessingError(
                "No username regions were detected; refusing to send an unblurred image."
            )

        result = original.copy()

        for (x1, y1, x2, y2) in username_regions:
            rw = x2 - x1
            rh = y2 - y1

            pad_x = max(5, int(rw * 0.08))
            pad_y = max(4, int(rh * 0.35))

            bx1 = max(0, x1 - pad_x)
            by1 = max(0, y1 - pad_y)
            bx2 = min(width, x2 + pad_x)
            by2 = min(height, y2 + pad_y)

            crop = result.crop((bx1, by1, bx2, by2))
            crop = crop.filter(ImageFilter.GaussianBlur(radius=12))
            result.paste(crop, (bx1, by1))

        result = apply_watermark(result)

        output = io.BytesIO()
        result.save(output, format="PNG", optimize=True)
        output.seek(0)

        return output.getvalue()

    except Exception as error:
        print(f"Proof processing error: {error}")
        raise ProofProcessingError(
            "Proof processing failed; refusing to send the original image."
        ) from error


# =========================================================
# PERMISSION / ERROR HELPERS
# =========================================================

def is_staff(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.guild_permissions.administrator:
        return True

    staff_role_id = config.get("staff_role_id")
    if staff_role_id:
        return any(role.id == staff_role_id for role in interaction.user.roles)

    return interaction.user.guild_permissions.manage_channels


def missing_bot_permissions(channel, *permissions):
    guild = getattr(channel, "guild", None)
    if not guild:
        return list(permissions)
    me = guild.me
    if me is None:
        return list(permissions)
    perms = channel.permissions_for(me)
    return [name for name, attr in permissions if not getattr(perms, attr, False)]


def member_hierarchy_error(interaction: discord.Interaction, target: discord.Member):
    guild = interaction.guild
    actor = interaction.user
    if guild is None or not isinstance(actor, discord.Member):
        return "❌ This command can only be used in a server."
    if target.id == actor.id:
        return "❌ You cannot target yourself."
    if target.id == guild.owner_id:
        return "❌ You cannot moderate the server owner."
    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        return "❌ You cannot target someone with an equal or higher role."
    me = guild.me
    if me is None:
        return "❌ I couldn't find my member role information."
    if target.top_role >= me.top_role:
        return "❌ I cannot target that user because their highest role is equal to or higher than mine."
    return None


async def safe_send(interaction: discord.Interaction, content=None, *, embed=None, ephemeral=False, view=None):
    try:
        kwargs = {
            "content": content,
            "embed": embed,
            "ephemeral": ephemeral,
        }
        if view is not None:
            kwargs["view"] = view

        if interaction.response.is_done():
            return await interaction.followup.send(**kwargs)
        return await interaction.response.send_message(**kwargs)
    except (discord.NotFound, discord.HTTPException) as error:
        print(f"[RESPONSE] Could not respond: {type(error).__name__}: {error}")
        return None


# =========================================================
# CHANNEL RENAME QUEUE
# =========================================================

pending_renames = {}


async def process_channel_renames():
    while True:
        try:
            if pending_renames:
                channel_id, new_name = next(iter(pending_renames.items()))
                del pending_renames[channel_id]

                channel = bot.get_channel(channel_id)
                if channel and channel.name != new_name:
                    try:
                        await channel.edit(name=new_name, reason="Shop status update")
                    except discord.HTTPException as error:
                        if error.status == 429:
                            pending_renames[channel_id] = new_name
                            await asyncio.sleep(max(1, getattr(error, "retry_after", 5)))
                        else:
                            print(f"[RENAME] HTTP error for {channel_id}: {error}")
                    except discord.Forbidden:
                        print(f"[RENAME] Missing Manage Channels for {channel_id}")
                    except Exception:
                        print(f"[RENAME] Unexpected error for {channel_id}")
                        traceback.print_exc()
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            print("[RENAME] Queue worker crashed; restarting loop.")
            traceback.print_exc()
            await asyncio.sleep(5)


# =========================================================
# MEMBER JOIN
# =========================================================

@bot.event
async def on_member_join(member: discord.Member):
    try:
        customer_role_id = config.get("customer_role_id")
        if customer_role_id:
            role = member.guild.get_role(int(customer_role_id))
            if role:
                me = member.guild.me
                if me and role >= me.top_role:
                    print(f"[WELCOME] Cannot give {role.name}: role is above the bot.")
                elif not me or not me.guild_permissions.manage_roles:
                    print(f"[WELCOME] I need Manage Roles to give {role.name}.")
                else:
                    try:
                        await member.add_roles(role, reason="Automatic customer role on join")
                    except discord.Forbidden:
                        print(f"[WELCOME] Cannot give {role.name} to {member}: check Manage Roles and hierarchy.")
                    except discord.HTTPException as error:
                        print(f"[WELCOME] Role assignment HTTP error: {error}")
    except Exception:
        print("[WELCOME] Unexpected role-assignment error")
        traceback.print_exc()

    channel_id = config.get("welcome_goodbye_channel_id")
    if not channel_id:
        return
    channel = member.guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        print(f"[WELCOME] Configured welcome channel {channel_id} was not found.")
        return

    # Mobile-optimized Embed layout
    embed = discord.Embed(
        title="🌸 Welcome to ali's adm house! ♡",
        description=(
            f"Welcome {member.mention}! We're so happy to have you here! ♡\n\n"
            "**Getting Started**\n"
            "• Check out our products and shop listings.\n"
            "• Open a support ticket for custom orders or questions.\n"
            "• Feel free to chat and enjoy the community! ♡"
        ),
        color=PINK
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🌸 Customer", value=member.mention, inline=False)
    embed.add_field(name="⭐ Total Members", value=f"`{member.guild.member_count}`", inline=False)
    embed.set_footer(text="ali's adm house • Welcome ♡")

    try:
        await channel.send(
            content=f"👋 Welcome to the server {member.mention}! ♡",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[member])
        )
    except discord.Forbidden:
        print(f"[WELCOME] Cannot send in #{channel.name}: check View Channel/Send Messages.")
    except discord.HTTPException as error:
        print(f"[WELCOME] HTTP error: {error}")


# =========================================================
# MEMBER LEAVE
# =========================================================

@bot.event
async def on_member_remove(member: discord.Member):
    channel_id = config.get("welcome_goodbye_channel_id")
    if not channel_id:
        return
    channel = member.guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        return

    # Mobile-optimized Embed layout
    embed = discord.Embed(
        title="💔 Goodbye, see you soon! ♡",
        description=(
            f"**{member.name}** has left **ali's adm house**...\n\n"
            "We're sad to see you leave, but we hope to see you back again soon! ♡"
        ),
        color=GRAY
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👋 Member", value=f"`{member.name}`", inline=False)
    embed.set_footer(text="ali's adm house • Goodbye ♡")

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        print(f"[GOODBYE] Cannot send in #{channel.name}: check Send Messages.")
    except discord.HTTPException as error:
        print(f"[GOODBYE] HTTP error: {error}")


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
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            return await safe_send(interaction, "❌ This button can only be used in a server.", ephemeral=True)

        category_id = config.get("ticket_category_id")
        category = guild.get_channel(int(category_id)) if category_id else None
        if not isinstance(category, discord.CategoryChannel):
            return await safe_send(interaction, "❌ The ticket category hasn't been configured yet.", ephemeral=True)

        topic = f"ali_adm_ticket:{interaction.user.id}"
        existing = discord.utils.find(lambda c: isinstance(c, discord.TextChannel) and c.topic == topic, guild.text_channels)
        if existing:
            return await safe_send(interaction, f"❌ You already have an open ticket: {existing.mention}", ephemeral=True)

        staff_role = guild.get_role(int(config["staff_role_id"])) if config.get("staff_role_id") else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                attach_files=True, embed_links=True
            )
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_channels=True, attach_files=True, embed_links=True
            )

        me = guild.me
        if me is None:
            return await safe_send(interaction, "❌ I couldn't find my server member information.", ephemeral=True)
        category_perms = category.permissions_for(me)
        missing = [name for name, attr in (
            ("View Channel", "view_channel"),
            ("Manage Channels", "manage_channels")
        ) if not getattr(category_perms, attr, False)]
        if missing:
            return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " for ticket creation.", ephemeral=True)

        username = "".join(c if c.isalnum() or c == "-" else "-" for c in interaction.user.name.lower().replace("_", "-"))
        ticket_name = f"ticket-{username}"[:90]

        try:
            await interaction.response.defer(ephemeral=True)
            ticket_channel = await guild.create_text_channel(
                name=ticket_name,
                category=category,
                overwrites=overwrites,
                topic=topic,
                reason=f"Ticket opened by {interaction.user}"
            )

            # Mobile-optimized Embed layout
            embed = discord.Embed(
                title="🎫 Support Tickets ♡",
                description=(
                    f"Welcome {interaction.user.mention}! ♡\n\n"
                    "Thank you for contacting **ali's adm house**!\n"
                    "Please specify the details below:\n\n"
                    "• **House:**\n"
                    "• **Build Type:**\n\n"
                    "A staff member will be with you shortly. ♡"
                ),
                color=PINK
            )
            embed.set_footer(text="ali's adm house • Support ♡")

            await ticket_channel.send(
                content=interaction.user.mention,
                embed=embed,
                view=CloseTicketView(),
                allowed_mentions=discord.AllowedMentions(users=[interaction.user])
            )
            await interaction.followup.send(f"🎫 Your ticket has been created: {ticket_channel.mention}", ephemeral=True)
        except discord.Forbidden:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Discord denied ticket creation. Check **Manage Channels**, **View Channel**, and role hierarchy.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Discord denied ticket creation. Check **Manage Channels**, **View Channel**, and role hierarchy.", ephemeral=True)
        except discord.HTTPException as error:
            print(f"[TICKET CREATE] HTTP error: {error}")
            await safe_send(interaction, f"❌ Discord returned an error while creating the ticket: `{error}`", ephemeral=True)
        except Exception:
            print("[TICKET CREATE] Unexpected error")
            traceback.print_exc()
            await safe_send(interaction, "❌ Something went wrong while creating the ticket. Check the bot console.", ephemeral=True)


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
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        guild = interaction.guild
        if guild is None or channel is None:
            return await safe_send(interaction, "❌ This ticket is no longer available.", ephemeral=True)

        if is_staff(interaction):
            try:
                await interaction.response.send_message("🔒 Closing ticket in **3 seconds**...")
                await asyncio.sleep(3)
                await channel.delete(reason=f"Ticket closed by staff {interaction.user}")
            except discord.NotFound:
                pass
            except discord.Forbidden:
                await safe_send(interaction, "❌ I cannot delete this ticket channel. Check **Manage Channels**.", ephemeral=True)
            except discord.HTTPException as error:
                print(f"[TICKET CLOSE] HTTP error: {error}")
                await safe_send(interaction, "❌ Discord rejected the ticket deletion.", ephemeral=True)
            return

        vouch_channel_id = config.get("vouch_channel_id")
        vouch_channel = guild.get_channel(int(vouch_channel_id)) if vouch_channel_id else None
        if not isinstance(vouch_channel, discord.TextChannel):
            return await safe_send(interaction, "❌ The vouch channel has not been configured yet.", ephemeral=True)

        ticket_created_at = getattr(channel, "created_at", discord.utils.utcnow())
        has_vouched = False
        try:
            async for message in vouch_channel.history(limit=200):
                if message.author != bot.user:
                    continue
                if (interaction.user in message.mentions or str(interaction.user.id) in message.content) and message.created_at >= ticket_created_at:
                    has_vouched = True
                    break
        except discord.Forbidden:
            return await safe_send(interaction, "❌ I cannot check the vouch channel. Please contact staff.", ephemeral=True)
        except discord.HTTPException as error:
            print(f"[TICKET VOUCH CHECK] HTTP error: {error}")
            return await safe_send(interaction, "❌ I couldn't verify your vouch right now. Please try again.", ephemeral=True)

        bot_commands_channel = discord.utils.get(guild.text_channels, name="₊˚♡-bot-commands")
        commands_mention = bot_commands_channel.mention if bot_commands_channel else "`#bot-commands`"
        if not has_vouched:
            return await safe_send(interaction, f"Did you vouch yet? ♡\n\nPlease use `/vouch` in {commands_mention} before closing your ticket!", ephemeral=True)

        try:
            await interaction.response.send_message(
                "Thank you so much for your order and for leaving a vouch! ♡\n"
                "We hope to see you again at **ali's adm house**! 🌸\n\n"
                "🔒 *Closing this ticket in 3 seconds...*"
            )
            await asyncio.sleep(3)
            await channel.delete(reason=f"Ticket closed by customer {interaction.user}")
        except discord.NotFound:
            pass
        except discord.Forbidden:
            await safe_send(interaction, "❌ I cannot delete this ticket channel. Please contact staff.", ephemeral=True)
        except discord.HTTPException as error:
            print(f"[TICKET CLOSE] Customer close HTTP error: {error}")
            await safe_send(interaction, "❌ Discord rejected the ticket deletion.", ephemeral=True)


# =========================================================
# SETUP
# =========================================================

@bot.tree.command(name="setup", description="Configure the ticket system.")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(panel_channel="Channel for the ticket panel", ticket_category="Category where tickets are created", staff_role="Staff role", vouch_channel="Vouch channel")
async def setup(interaction: discord.Interaction, panel_channel: discord.TextChannel, ticket_category: discord.CategoryChannel, staff_role: discord.Role | None = None, vouch_channel: discord.TextChannel | None = None):
    guild = interaction.guild
    if guild is None or not interaction.user.guild_permissions.administrator:
        return await safe_send(interaction, "❌ You need **Administrator** permission.", ephemeral=True)
    me = guild.me
    if me is None:
        return await safe_send(interaction, "❌ I couldn't find my server member information.", ephemeral=True)
    missing = missing_bot_permissions(panel_channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Embed Links", "embed_links"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in the panel channel.", ephemeral=True)
    cat_perms = ticket_category.permissions_for(me)
    if not cat_perms.view_channel or not cat_perms.manage_channels:
        return await safe_send(interaction, "❌ I need **View Channel** and **Manage Channels** for the ticket category.", ephemeral=True)
    if staff_role and (staff_role.is_default() or staff_role.managed or staff_role >= me.top_role):
        return await safe_send(interaction, "❌ I cannot use that staff role because it is managed or too high for my role.", ephemeral=True)

    config["panel_channel_id"] = panel_channel.id
    config["ticket_category_id"] = ticket_category.id
    config["staff_role_id"] = staff_role.id if staff_role else None
    if vouch_channel is not None:
        config["vouch_channel_id"] = vouch_channel.id
    save_config(config)

    # Mobile-optimized Embed layout
    embed = discord.Embed(
        title="🎫 Support Tickets ♡",
        description=(
            "Need help with an order or house builds?\n\n"
            "Click **🎫 Open Ticket** below to open a private ticket with staff! ♡"
        ),
        color=PINK
    )
    embed.set_footer(text="ali's adm house • Support ♡")

    try:
        await panel_channel.send(embed=embed, view=TicketView())
        await interaction.response.send_message("♡ Ticket system configured successfully!", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ Configuration was saved, but I cannot send the ticket panel there. Check my permissions.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[SETUP] HTTP error: {error}")
        await safe_send(interaction, "❌ Configuration was saved, but Discord rejected the panel message.", ephemeral=True)


# =========================================================
# SETUP STATUS
# =========================================================

@bot.tree.command(
    name="setupstatus",
    description="Configure the shop status channel."
)
@app_commands.default_permissions(administrator=True)
async def setupstatus(
    interaction: discord.Interaction,
    status_channel: discord.TextChannel
):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ You need **Administrator** permission.",
            ephemeral=True
        )

    missing = missing_bot_permissions(
        status_channel,
        ("View Channel", "view_channel"),
        ("Send Messages", "send_messages"),
        ("Manage Channels", "manage_channels")
    )
    if missing:
        return await interaction.response.send_message(
            "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in that channel.",
            ephemeral=True
        )

    config["status_channel_id"] = status_channel.id
    save_config(config)

    await interaction.response.send_message(
        f"♡ Status channel set to {status_channel.mention}.",
        ephemeral=True
    )


# =========================================================
# SETUP JOINS
# =========================================================

@bot.tree.command(
    name="setupjoins",
    description="Configure welcome/goodbye messages."
)
@app_commands.default_permissions(administrator=True)
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

    config["welcome_goodbye_channel_id"] = welcome_goodbye_channel.id

    if customer_role:
        me = interaction.guild.me
        if me and (customer_role.is_default() or customer_role.managed or customer_role >= me.top_role):
            return await interaction.response.send_message(
                "❌ I cannot automatically give that customer role because it is managed or too high for my role.",
                ephemeral=True
            )
        config["customer_role_id"] = customer_role.id

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
@app_commands.default_permissions(administrator=True)
async def setupproof(
    interaction: discord.Interaction,
    proof_channel: discord.TextChannel
):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ You need **Administrator** permission.",
            ephemeral=True
        )

    missing = missing_bot_permissions(
        proof_channel,
        ("View Channel", "view_channel"),
        ("Send Messages", "send_messages"),
        ("Attach Files", "attach_files")
    )
    if missing:
        return await interaction.response.send_message(
            "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in the proof channel.",
            ephemeral=True
        )

    config["proof_channel_id"] = proof_channel.id
    save_config(config)

    await interaction.response.send_message(
        "♡ Proof channel configured successfully!\n\n"
        f"📸 Proof Channel: {proof_channel.mention}",
        ephemeral=True
    )


# =========================================================
# TICKET PANEL
# =========================================================

@bot.tree.command(name="ticketpanel", description="Send a ticket panel.")
async def ticketpanel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ You need staff permissions.", ephemeral=True)
    missing = missing_bot_permissions(channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Embed Links", "embed_links"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in that channel.", ephemeral=True)

    # Mobile-optimized Embed layout
    embed = discord.Embed(
        title="🎫 Support Tickets ♡",
        description="Need help? ♡\n\nClick **🎫 Open Ticket** below to open a private ticket.",
        color=PINK
    )
    embed.set_footer(text="ali's adm house • Support ♡")

    try:
        await channel.send(embed=embed, view=TicketView())
        await safe_send(interaction, f"♡ Ticket panel sent to {channel.mention}.", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied sending the ticket panel.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[TICKET PANEL] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the ticket panel.", ephemeral=True)


# =========================================================
# PING
# =========================================================

@bot.tree.command(
    name="ping",
    description="Check the bot latency."
)
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"♡ Pong!\n🌸 Latency: **{latency}ms**",
        ephemeral=True
    )


# =========================================================
# PROOF
# =========================================================

@bot.tree.command(name="proof", description="Upload a proof image.")
@app_commands.describe(image="Proof image")
async def proof(interaction: discord.Interaction, image: discord.Attachment):
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)

    proof_channel_id = config.get("proof_channel_id")
    if not proof_channel_id:
        return await safe_send(interaction, "❌ Proof channel is not configured.", ephemeral=True)

    proof_channel = guild.get_channel(int(proof_channel_id))
    if not isinstance(proof_channel, discord.TextChannel):
        return await safe_send(interaction, "❌ Proof channel could not be found.", ephemeral=True)

    valid_extensions = (".png", ".jpg", ".jpeg", ".webp")
    content_type = (image.content_type or "").lower()
    filename = image.filename.lower()
    if not (content_type.startswith("image/") or filename.endswith(valid_extensions)):
        return await safe_send(interaction, "❌ Please upload a PNG, JPG, JPEG, or WEBP image.", ephemeral=True)

    if image.size > 10 * 1024 * 1024:
        return await safe_send(interaction, "❌ Please keep proof images under **10 MB**.", ephemeral=True)

    missing = missing_bot_permissions(proof_channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Attach Files", "attach_files"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in the proof channel.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    try:
        image_data = await image.read()
        with Image.open(io.BytesIO(image_data)) as check:
            check.verify()

        blurred_data = await asyncio.to_thread(
            blur_proof_text,
            image_data
        )
        file = discord.File(io.BytesIO(blurred_data), filename="proof.png")
        await proof_channel.send(
            content="♡ **New Proof!**\nThank you so much! ♡",
            file=file
        )
        await interaction.followup.send("♡ Your proof has been submitted!", ephemeral=True)
    except (OSError, ValueError):
        await interaction.followup.send("❌ That image could not be read. Please upload a valid PNG/JPG/WEBP image.", ephemeral=True)
    except ProofProcessingError as error:
        print(f"[PROOF] {error}")
        await interaction.followup.send("❌ I could not safely blur that proof image, so it was not uploaded. Please try a clearer screenshot.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I cannot post the processed proof. Check **Send Messages** and **Attach Files**.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[PROOF] Discord HTTP error: {error}")
        await interaction.followup.send("❌ Discord rejected the proof upload. Please try again.", ephemeral=True)
    except Exception:
        print("[PROOF] Unexpected error")
        traceback.print_exc()
        await interaction.followup.send("❌ Something went wrong while processing the proof. Check the bot console.", ephemeral=True)


# =========================================================
# VOUCH
# =========================================================

@bot.tree.command(name="vouch", description="Leave a vouch.")
@app_commands.describe(message="Your vouch message")
async def vouch(interaction: discord.Interaction, message: str):
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)

    message = message.strip()
    if not message:
        return await safe_send(interaction, "❌ Please enter a vouch message.", ephemeral=True)
    if len(message) > 1000:
        return await safe_send(interaction, "❌ Your vouch is too long. Please keep it under **1000 characters**.", ephemeral=True)

    channel_id = config.get("vouch_channel_id")
    channel = guild.get_channel(int(channel_id)) if channel_id else None
    if not isinstance(channel, discord.TextChannel):
        return await safe_send(interaction, "❌ The vouch channel hasn't been configured yet.", ephemeral=True)

    missing = missing_bot_permissions(channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Embed Links", "embed_links"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in the vouch channel.", ephemeral=True)

    # Mobile-optimized Embed layout
    embed = discord.Embed(
        title="⭐ New Customer Vouch ♡",
        description=(
            f"**\"{discord.utils.escape_markdown(message)}\"**\n\n"
            f"**Customer:** {interaction.user.mention}\n"
            "Thank you so much! ♡"
        ),
        color=PINK
    )
    embed.set_author(name="ali's adm house ♡")
    embed.set_footer(text="ali's adm house • Vouches ♡")

    try:
        await channel.send(
            content=interaction.user.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user])
        )
        await interaction.response.send_message("♡ Your vouch has been posted! Thank you! ⭐", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ I cannot post in the vouch channel. Check my channel permissions.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[VOUCH] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the vouch. Please try again.", ephemeral=True)


# =========================================================
# VOUCH COUNT
# =========================================================

@bot.tree.command(name="vouchcount", description="Check the total number of vouches.")
async def vouchcount(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)
    channel_id = config.get("vouch_channel_id")
    channel = guild.get_channel(int(channel_id)) if channel_id else None
    if not isinstance(channel, discord.TextChannel):
        return await safe_send(interaction, "❌ Vouch channel isn't configured.", ephemeral=True)

    missing = missing_bot_permissions(channel, ("View Channel", "view_channel"), ("Read Message History", "read_message_history"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in the vouch channel.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    count = 0
    try:
        async for msg in channel.history(limit=5000):
            if msg.author == bot.user and any(
                embed.title == "⭐ New Customer Vouch ♡" for embed in msg.embeds
            ):
                count += 1
        await interaction.followup.send(f"♡ **ali's adm house** has **{count}** vouch(es)! ⭐", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I cannot read the vouch channel history.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[VOUCH COUNT] HTTP error: {error}")
        await interaction.followup.send("❌ Discord rejected the history request. Please try again.", ephemeral=True)
    except Exception:
        print("[VOUCH COUNT] Unexpected error")
        traceback.print_exc()
        await interaction.followup.send("❌ Something went wrong while counting vouches.", ephemeral=True)


# =========================================================
# STATUS
# =========================================================

@bot.tree.command(name="status", description="Update the shop status.")
@app_commands.choices(state=[
    app_commands.Choice(name="Available", value="available"),
    app_commands.Choice(name="Busy", value="busy"),
    app_commands.Choice(name="Closed", value="closed")
])
async def status(interaction: discord.Interaction, state: app_commands.Choice[str]):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can update the status.", ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)

    status_channel_id = config.get("status_channel_id")
    channel = guild.get_channel(int(status_channel_id)) if status_channel_id else None
    if not isinstance(channel, discord.TextChannel):
        return await safe_send(interaction, "❌ Status channel isn't configured.", ephemeral=True)

    missing = missing_bot_permissions(channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Manage Channels", "manage_channels"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in the status channel.", ephemeral=True)

    # Mobile-optimized Embed titles and standard text formatting
    states = {
        "available": ("🟢 Orders are Available", "Our shop is currently **OPEN** for new orders! ♡", GREEN, "🟢-available"),
        "busy": ("🔴 Orders are Busy", "Our shop is currently **BUSY**! ♡\nOrders may take a little longer.", RED, "🔴-busy"),
        "closed": ("⚪ Orders are Closed", "Our shop is currently **CLOSED**! ♡", GRAY, "⚪-closed")
    }
    title, description, color, channel_name = states.get(state.value, states["closed"])
    
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="ali's adm house • Status ♡")

    try:
        await channel.send(embed=embed)
        pending_renames[channel.id] = channel_name
        await interaction.response.send_message(f"♡ Shop status changed to **{state.name}**.", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ I cannot update the status channel. Check **Send Messages** and **Manage Channels**.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[STATUS] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the status update.", ephemeral=True)


# =========================================================
# SAY - MULTIPLE ROLE SELECT
# =========================================================

class SayRoleSelect(discord.ui.Select):

    def __init__(self, roles, selected_roles):

        self.roles = roles
        self.selected_roles = selected_roles

        options = []

        for role in roles[:25]:
            options.append(
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    description=f"Mention {role.name}"[:100]
                )
            )

        super().__init__(
            placeholder="♡ Choose the role(s) to mention...",
            min_values=0,
            max_values=len(options),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        role_ids = {role.id for role in self.roles}

        self.selected_roles[:] = [
            role for role in self.selected_roles
            if role.id not in role_ids
        ]

        for value in self.values:
            role = interaction.guild.get_role(int(value))
            if role:
                self.selected_roles.append(role)

        await interaction.response.defer()


class SayRoleView(discord.ui.View):

    def __init__(self, interaction, channel, message):
        super().__init__(timeout=120)

        self.original_user = interaction.user
        self.channel = channel
        self.message = message
        self.selected_roles = []

        guild = interaction.guild
        me = guild.me

        roles = [
            role for role in guild.roles
            if not role.is_default()
            and (not me or role < me.top_role)
        ]

        for i in range(0, len(roles), 25):
            chunk = roles[i:i + 25]
            self.add_item(SayRoleSelect(chunk, self.selected_roles))

            if len(self.children) >= 5:
                break

        self.add_item(SaySendButton(self))


class SaySendButton(discord.ui.Button):
    def __init__(self, view):
        self.say_view = view
        super().__init__(label="Send Announcement ♡", style=discord.ButtonStyle.success, emoji="📢", row=4)

    async def callback(self, interaction: discord.Interaction):
        view = self.say_view
        if interaction.user.id != view.original_user.id:
            return await interaction.response.send_message("❌ Only the person who used `/say` can use this.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message("❌ This server is no longer available.", ephemeral=True)
        if view.channel.guild.id != interaction.guild.id:
            return await interaction.response.send_message("❌ Invalid announcement channel.", ephemeral=True)

        roles = [r for r in view.selected_roles if r in interaction.guild.roles and not r.is_default()]
        content = " ".join(role.mention for role in roles) if roles else None

        # Mobile-optimized Embed layout
        embed = discord.Embed(
            title="📢 Announcement ♡",
            description=f"**Hello Everyone!** ♡\n\n{view.message}",
            color=PINK
        )
        embed.set_footer(text="ali's adm house • Thank you for being part of our community ♡")
        embed.timestamp = discord.utils.utcnow()

        missing = missing_bot_permissions(view.channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Embed Links", "embed_links"), ("Mention Everyone", "mention_everyone")) if roles else missing_bot_permissions(view.channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Embed Links", "embed_links"))
        if missing:
            return await interaction.response.send_message("❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in that channel.", ephemeral=True)

        try:
            await view.channel.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))
            await interaction.response.edit_message(content=f"♡ Announcement sent to {view.channel.mention}.", view=None)
            view.stop()
        except discord.Forbidden:
            await interaction.response.send_message("❌ I cannot send the announcement in that channel.", ephemeral=True)
        except discord.HTTPException as error:
            print(f"[SAY] HTTP error: {error}")
            await interaction.response.send_message("❌ Discord rejected the announcement.", ephemeral=True)
        except Exception:
            print("[SAY] Unexpected error")
            traceback.print_exc()
            await interaction.response.send_message("❌ Something went wrong sending the announcement.", ephemeral=True)


@bot.tree.command(name="say", description="Send an announcement.")
@app_commands.describe(channel="Channel to announce in", message="Announcement message")
async def say(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can use `/say`.", ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)
    message = message.strip()
    if not message:
        return await safe_send(interaction, "❌ The announcement cannot be empty.", ephemeral=True)
    if len(message) > 4000:
        return await safe_send(interaction, "❌ Keep the announcement under **4000 characters**.", ephemeral=True)

    missing = missing_bot_permissions(channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Embed Links", "embed_links"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in that channel.", ephemeral=True)

    me = guild.me
    manageable_roles = [role for role in guild.roles if not role.is_default() and (me is None or role < me.top_role)]

    if len(manageable_roles) > 100:
        return await safe_send(interaction, "❌ There are too many manageable roles for this announcement menu. Please reduce the number of roles or mention roles manually.", ephemeral=True)

    try:
        view = SayRoleView(interaction, channel, message)
        await interaction.response.send_message(
            "♡ **Choose the role(s) to mention** ♡\n\nYou can select multiple roles, then press **Send Announcement ♡**.",
            view=view,
            ephemeral=True
        )
    except discord.HTTPException as error:
        print(f"[SAY] Could not open selector: {error}")
        await safe_send(interaction, "❌ Discord could not create the announcement menu.", ephemeral=True)

# =========================================================
# WARN
# =========================================================

@bot.tree.command(name="warn", description="Warn a user.")
@app_commands.describe(user="User to warn", reason="Reason")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can warn users.", ephemeral=True)
    reason = reason.strip() or "No reason provided"
    if len(reason) > 500:
        return await safe_send(interaction, "❌ Keep the reason under **500 characters**.", ephemeral=True)
    hierarchy_error = member_hierarchy_error(interaction, user)
    if hierarchy_error:
        return await safe_send(interaction, hierarchy_error, ephemeral=True)

    dm_sent = True
    try:
        # Mobile-optimized Embed layout
        embed = discord.Embed(
            title="⚠️ Warning Received",
            description=f"You have been issued a warning in **{interaction.guild.name}**.\n\n**Reason:** {discord.utils.escape_markdown(reason)}",
            color=RED
        )
        embed.set_footer(text="ali's adm house • Moderation ♡")
        await user.send(embed=embed)
    except discord.Forbidden:
        dm_sent = False
    except discord.HTTPException as error:
        print(f"[WARN] DM HTTP error: {error}")
        dm_sent = False

    suffix = " The user could not receive the DM." if not dm_sent else ""
    await safe_send(interaction, f"⚠️ Warned {user.mention}.\nReason: **{discord.utils.escape_markdown(reason)}**{suffix}", ephemeral=True)


# =========================================================
# CLEAR
# =========================================================

@bot.tree.command(name="clear", description="Delete recent messages.")
@app_commands.describe(amount="Number of messages to delete (1-100)")
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    guild = interaction.guild
    channel = interaction.channel
    if guild is None or channel is None:
        return await safe_send(interaction, "❌ This command can only be used in a server channel.", ephemeral=True)
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can clear messages.", ephemeral=True)
    if not isinstance(channel, discord.TextChannel):
        return await safe_send(interaction, "❌ This command can only be used in a text channel.", ephemeral=True)

    missing = missing_bot_permissions(channel, ("View Channel", "view_channel"), ("Read Message History", "read_message_history"), ("Manage Messages", "manage_messages"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in this channel.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    try:
        messages = [m async for m in channel.history(limit=int(amount))]
        if not messages:
            return await interaction.followup.send("❌ There are no messages to delete.", ephemeral=True)

        cutoff = discord.utils.utcnow() - timedelta(days=14)
        recent = [m for m in messages if m.created_at > cutoff]
        old = [m for m in messages if m.created_at <= cutoff]
        deleted_count = 0

        if recent:
            try:
                await channel.delete_messages(recent)
                deleted_count += len(recent)
            except discord.HTTPException as error:
                print(f"[CLEAR] Bulk delete failed ({error}); falling back to individual deletes.")
                for message in recent:
                    try:
                        await message.delete(reason=f"Cleared by {interaction.user}")
                        deleted_count += 1
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        print(f"[CLEAR] Forbidden deleting {message.id}")
                    except discord.HTTPException as individual_error:
                        print(f"[CLEAR] Individual delete failed for {message.id}: {individual_error}")

        for message in old:
            try:
                await message.delete(reason=f"Cleared by {interaction.user}")
                deleted_count += 1
            except discord.NotFound:
                pass
            except discord.Forbidden:
                print(f"[CLEAR] Forbidden deleting old message {message.id}")
            except discord.HTTPException as error:
                print(f"[CLEAR] Old message delete failed for {message.id}: {error}")

        if deleted_count == 0:
            return await interaction.followup.send("❌ I couldn't delete any messages. Check **Manage Messages** and my role hierarchy.", ephemeral=True)
        await interaction.followup.send(f"🗑️ Deleted **{deleted_count}** message(s).", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Discord denied the deletion. Check **Manage Messages** and **Read Message History**.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[CLEAR] HTTP error: {error}")
        await interaction.followup.send(f"❌ Discord returned an error while clearing messages: `{error}`", ephemeral=True)
    except Exception:
        print("[CLEAR] Unexpected error")
        traceback.print_exc()
        await interaction.followup.send("❌ Something went wrong while clearing messages. Check the bot console for the exact error.", ephemeral=True)


# =========================================================
# GIVE ROLE
# =========================================================

@bot.tree.command(name="giverole", description="Give a role to a user.")
async def giverole(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can give roles.", ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)
    if role.is_default() or role.managed:
        return await safe_send(interaction, "❌ You cannot give @everyone or a managed/integration role.", ephemeral=True)
    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        return await safe_send(interaction, "❌ I need **Manage Roles** to give roles.", ephemeral=True)
    if role >= me.top_role:
        return await safe_send(interaction, "❌ I cannot give that role because it is too high for my role hierarchy.", ephemeral=True)
    actor = interaction.user
    if actor.id != guild.owner_id and role >= actor.top_role and not actor.guild_permissions.administrator:
        return await safe_send(interaction, "❌ You cannot give a role equal to or higher than your highest role.", ephemeral=True)
    if role in user.roles:
        return await safe_send(interaction, f"❌ {user.mention} already has {role.mention}.", ephemeral=True)
    try:
        await user.add_roles(role, reason=f"Given by {interaction.user}")
        await safe_send(interaction, f"✅ Gave {user.mention} {role.mention}.", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied the role change. Check **Manage Roles** and hierarchy.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[GIVEROLE] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the role change.", ephemeral=True)


# =========================================================
# MUTE / UNMUTE
# =========================================================

def parse_timeout_duration(value: str):
    import re

    value = value.strip().lower()
    match = re.fullmatch(r"(\d+)\s*(s|m|h|d|w)", value)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
        "w": 7 * 24 * 60 * 60,
    }
    seconds = amount * multipliers[unit]

    if seconds < 1 or seconds > 28 * 24 * 60 * 60:
        return None

    return timedelta(seconds=seconds)


def format_timeout_duration(value: str) -> str:
    value = value.strip().lower()
    return value


@bot.tree.command(name="mute", description="Timeout a user for a specified duration.")
@app_commands.describe(
    user="The user to mute",
    duration="How long? Example: 10m, 1h, 1d, 1w (max 28d)",
    reason="Why are you muting this user?",
)
async def mute(
    interaction: discord.Interaction,
    user: discord.Member,
    duration: str = "10m",
    reason: str = "No reason provided",
):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can mute users.", ephemeral=True)

    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)

    hierarchy_error = member_hierarchy_error(interaction, user)
    if hierarchy_error:
        return await safe_send(interaction, hierarchy_error, ephemeral=True)

    timeout_duration = parse_timeout_duration(duration)
    if timeout_duration is None:
        return await safe_send(
            interaction,
            "❌ Invalid mute duration. Use something like **10m**, **1h**, **1d**, or **1w**. Maximum is **28d**.",
            ephemeral=True,
        )

    reason = reason.strip() or "No reason provided"
    if len(reason) > 500:
        return await safe_send(interaction, "❌ Keep the reason under **500 characters**.", ephemeral=True)

    me = guild.me
    if me is None or not me.guild_permissions.moderate_members:
        return await safe_send(interaction, "❌ I need **Moderate Members** permission to mute/timeout users.", ephemeral=True)

    try:
        await user.timeout(discord.utils.utcnow() + timeout_duration, reason=reason)
        await safe_send(
            interaction,
            f"🔇 Muted {user.mention} for **{format_timeout_duration(duration)}**.\nReason: **{discord.utils.escape_markdown(reason)}**",
            ephemeral=True,
        )
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied the timeout. Check **Moderate Members** and role hierarchy.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[MUTE] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the timeout.", ephemeral=True)


@bot.tree.command(name="unmute", description="Remove a user's timeout.")
@app_commands.describe(user="The user to unmute")
async def unmute(interaction: discord.Interaction, user: discord.Member):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can unmute users.", ephemeral=True)

    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)

    hierarchy_error = member_hierarchy_error(interaction, user)
    if hierarchy_error:
        return await safe_send(interaction, hierarchy_error, ephemeral=True)

    me = guild.me
    if me is None or not me.guild_permissions.moderate_members:
        return await safe_send(interaction, "❌ I need **Moderate Members** permission to remove timeouts.", ephemeral=True)

    try:
        await user.timeout(None, reason=f"Unmuted by {interaction.user}")
        await safe_send(interaction, f"🔊 Unmuted {user.mention}.", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied the unmute. Check **Moderate Members** and role hierarchy.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[UNMUTE] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the unmute.", ephemeral=True)


# =========================================================
# BAN / UNBAN
# =========================================================

@bot.tree.command(name="ban", description="Ban a user.")
@app_commands.describe(
    user="The user to ban",
    reason="Why are you banning this user?",
)
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can ban users.", ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)
    hierarchy_error = member_hierarchy_error(interaction, user)
    if hierarchy_error:
        return await safe_send(interaction, hierarchy_error, ephemeral=True)
    reason = reason.strip() or "No reason provided"
    if len(reason) > 500:
        return await safe_send(interaction, "❌ Keep the reason under **500 characters**.", ephemeral=True)
    me = guild.me
    if me is None or not me.guild_permissions.ban_members:
        return await safe_send(interaction, "❌ I need **Ban Members** permission.", ephemeral=True)
    try:
        await guild.ban(user, reason=reason)
        await safe_send(interaction, f"🚫 Banned {user.mention}.\nReason: **{discord.utils.escape_markdown(reason)}**", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied the ban. Check **Ban Members** and role hierarchy.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[BAN] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the ban.", ephemeral=True)


@bot.tree.command(name="unban", description="Unban a user by their Discord ID.")
@app_commands.describe(user_id="The user's Discord ID")
async def unban(interaction: discord.Interaction, user_id: str):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can unban users.", ephemeral=True)

    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)

    me = guild.me
    if me is None or not me.guild_permissions.ban_members:
        return await safe_send(interaction, "❌ I need **Ban Members** permission to unban users.", ephemeral=True)

    user_id = user_id.strip()
    if not user_id.isdigit():
        return await safe_send(interaction, "❌ Enter a valid Discord user ID.", ephemeral=True)

    try:
        target_id = int(user_id)
        user = await bot.fetch_user(target_id)
        await guild.unban(user, reason=f"Unbanned by {interaction.user}")
        await safe_send(interaction, f"✅ Unbanned **{discord.utils.escape_markdown(str(user))}** (`{target_id}`).", ephemeral=True)
    except discord.NotFound:
        await safe_send(interaction, "❌ That user is not banned, or the user ID does not exist.", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied the unban. Check **Ban Members** permission.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[UNBAN] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the unban.", ephemeral=True)


# =========================================================
# KICK
# =========================================================

@bot.tree.command(name="kick", description="Kick a user.")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can kick users.", ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)
    hierarchy_error = member_hierarchy_error(interaction, user)
    if hierarchy_error:
        return await safe_send(interaction, hierarchy_error, ephemeral=True)
    reason = reason.strip() or "No reason provided"
    if len(reason) > 500:
        return await safe_send(interaction, "❌ Keep the reason under **500 characters**.", ephemeral=True)
    me = guild.me
    if me is None or not me.guild_permissions.kick_members:
        return await safe_send(interaction, "❌ I need **Kick Members** permission.", ephemeral=True)
    try:
        dm_sent = True
        try:
            await user.send(
                f"👢 You have been kicked from **{discord.utils.escape_markdown(guild.name)}**.\n\n"
                f"Reason: **{discord.utils.escape_markdown(reason)}**"
            )
        except (discord.Forbidden, discord.HTTPException):
            dm_sent = False

        await user.kick(reason=reason)
        dm_status = "📩 DM sent to the user." if dm_sent else "⚠️ I could not DM the user (their DMs may be disabled)."
        await safe_send(
            interaction,
            f"👢 Kicked {user.mention}.\nReason: **{discord.utils.escape_markdown(reason)}**\n{dm_status}",
            ephemeral=True,
        )
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied the kick. Check **Kick Members** and role hierarchy.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[KICK] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the kick.", ephemeral=True)


# =========================================================
# LOCK CHANNEL
# =========================================================

@bot.tree.command(name="lockchannel", description="Lock a channel.")
async def lockchannel(interaction: discord.Interaction, channel: discord.TextChannel | None = None, reason: str = "No reason provided"):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can lock channels.", ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        return await safe_send(interaction, "❌ Invalid text channel.", ephemeral=True)
    me = guild.me
    if me is None or not me.guild_permissions.manage_channels:
        return await safe_send(interaction, "❌ I need **Manage Channels** permission.", ephemeral=True)
    missing = missing_bot_permissions(target, ("View Channel", "view_channel"), ("Manage Channels", "manage_channels"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in that channel.", ephemeral=True)
    reason = reason.strip() or "No reason provided"
    try:
        await target.set_permissions(guild.default_role, send_messages=False, reason=reason)
        await safe_send(interaction, f"🔒 Locked {target.mention}.\nReason: **{discord.utils.escape_markdown(reason)}**", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied the channel lock. Check **Manage Channels**.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[LOCK] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the channel lock.", ephemeral=True)


# =========================================================
# UNLOCK CHANNEL
# =========================================================

@bot.tree.command(name="unlockchannel", description="Unlock a channel.")
async def unlockchannel(interaction: discord.Interaction, channel: discord.TextChannel | None = None, reason: str = "No reason provided"):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ Only staff can unlock channels.", ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await safe_send(interaction, "❌ This command can only be used in a server.", ephemeral=True)
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        return await safe_send(interaction, "❌ Invalid text channel.", ephemeral=True)
    me = guild.me
    if me is None or not me.guild_permissions.manage_channels:
        return await safe_send(interaction, "❌ I need **Manage Channels** permission.", ephemeral=True)
    reason = reason.strip() or "No reason provided"
    try:
        await target.set_permissions(guild.default_role, send_messages=None, reason=reason)
        await safe_send(interaction, f"🔓 Unlocked {target.mention}.\nReason: **{discord.utils.escape_markdown(reason)}**", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, "❌ Discord denied the channel unlock. Check **Manage Channels**.", ephemeral=True)
    except discord.HTTPException as error:
        print(f"[UNLOCK] HTTP error: {error}")
        await safe_send(interaction, "❌ Discord rejected the channel unlock.", ephemeral=True)


# =========================================================
# PREFIX VOUCH
# =========================================================

@bot.command(name="vouch")
async def vouch_prefix(ctx, *, message: str = None):
    if message is None or not message.strip():
        return await ctx.send("❌ Please include a vouch message!\n\nExample:\n`!vouch Great service! ♡`", delete_after=10)
    message = message.strip()
    if len(message) > 1000:
        return await ctx.send("❌ Please keep your vouch under 1000 characters.", delete_after=10)
    if ctx.guild is None:
        return await ctx.send("❌ This command can only be used in a server.", delete_after=10)

    channel_id = config.get("vouch_channel_id")
    channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
    if not isinstance(channel, discord.TextChannel):
        return await ctx.send("❌ Vouch channel isn't configured.")

    # Mobile-optimized Embed layout
    embed = discord.Embed(
        title="⭐ New Customer Vouch ♡",
        description=(
            f"**\"{discord.utils.escape_markdown(message)}\"**\n\n"
            f"**Customer:** {ctx.author.mention}\n"
            "Thank you so much! ♡"
        ),
        color=PINK
    )
    embed.set_author(name="ali's adm house ♡")
    embed.set_footer(text="ali's adm house • Vouches ♡")

    try:
        await channel.send(content=ctx.author.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await ctx.send(f"♡ Thank you {ctx.author.mention}, your vouch has been posted! ⭐", delete_after=5)
    except discord.Forbidden:
        await ctx.send("❌ I cannot post in the vouch channel. Check my permissions.", delete_after=10)
    except discord.HTTPException as error:
        print(f"[PREFIX VOUCH] HTTP error: {error}")
        await ctx.send("❌ Discord rejected the vouch.", delete_after=10)


# =========================================================
# COMMAND ERRORS
# =========================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send(f"❌ Missing argument: **{error.param.name}**.", delete_after=10)
    if isinstance(error, commands.BadArgument):
        return await ctx.send("❌ One of the command arguments is invalid.", delete_after=10)
    print(f"[PREFIX COMMAND ERROR] {type(error).__name__}: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = error
    while hasattr(original, "original"):
        original = original.original
    command_name = interaction.command.name if interaction.command else "unknown"
    print(f"\n[SLASH COMMAND ERROR]\nCommand: /{command_name}\nUser: {interaction.user} ({interaction.user.id})\nGuild: {interaction.guild} ({interaction.guild.id if interaction.guild else 'DM'})\nType: {type(original).__name__}\nError: {original}")
    traceback.print_exception(type(original), original, original.__traceback__)

    if isinstance(original, app_commands.CommandOnCooldown):
        message = f"⏳ Please wait {original.retry_after:.1f}s before using this command again."
    elif isinstance(original, app_commands.MissingPermissions):
        message = "❌ You don't have the required permissions for this command."
    elif isinstance(original, app_commands.BotMissingPermissions):
        message = "❌ I am missing these permissions: **" + ", ".join(original.missing_permissions) + "**"
    elif isinstance(original, app_commands.TransformerError):
        message = "❌ One of the command options has an invalid value."
    elif isinstance(original, discord.Forbidden):
        message = "❌ Discord denied that action. Please check my permissions and role hierarchy."
    elif isinstance(original, discord.HTTPException):
        message = f"❌ Discord returned an error: `{original}`"
    elif isinstance(original, TypeError):
        message = "❌ That command received an invalid option. Please try the command again."
    else:
        message = "❌ Something went wrong while running that command. The bot console now contains the exact error."
    await safe_send(interaction, message, ephemeral=True)


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if not getattr(bot, "_persistent_views_loaded", False):
        try:
            bot.add_view(TicketView())
            bot.add_view(CloseTicketView())
            bot._persistent_views_loaded = True
        except Exception:
            print("[READY] Failed to load persistent views")
            traceback.print_exc()
    if not hasattr(bot, "_rename_task") or bot._rename_task.done():
        bot._rename_task = asyncio.create_task(process_channel_renames())
    if not getattr(bot, "_commands_synced", False):
        try:
            guild_id = os.getenv("DISCORD_GUILD_ID")
            if guild_id:
                synced = await bot.tree.sync(guild=discord.Object(id=int(guild_id)))
                print(f"Successfully synced {len(synced)} slash commands to guild {guild_id}.")
            else:
                synced = await bot.tree.sync()
                print(f"Successfully synced {len(synced)} global slash commands.")
            bot._commands_synced = True
        except ValueError:
            print("[READY] DISCORD_GUILD_ID is invalid; falling back to global sync.")
            try:
                synced = await bot.tree.sync()
                bot._commands_synced = True
                print(f"Successfully synced {len(synced)} global slash commands.")
            except Exception:
                print("[READY] Global command sync failed")
                traceback.print_exc()
        except Exception:
            print("[READY] Command sync failed")
            traceback.print_exc()


# =========================================================
# START BOT
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set.")


def main():
    keep_alive()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()

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
    ) or 1545438540362555463
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
    """
    Blur one individual region without creating
    a giant rectangular blur across the screenshot.
    """

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


def is_date_or_time(text):
    """
    Prevent dates/times from being blurred.
    """

    text_lower = text.lower().strip()

    if not text_lower:
        return True

    if ":" in text_lower:
        return True

    if "/" in text_lower:
        return True

    months = [
        "jan",
        "january",
        "feb",
        "february",
        "mar",
        "march",
        "apr",
        "april",
        "may",
        "jun",
        "june",
        "jul",
        "july",
        "aug",
        "august",
        "sep",
        "sept",
        "september",
        "oct",
        "october",
        "nov",
        "november",
        "dec",
        "december"
    ]

    for month in months:

        if month in text_lower:
            return True

    if text_lower.replace(
        ",",
        ""
    ).replace(
        ".",
        ""
    ).isdigit():

        return True

    return False


def is_button_text(text):
    """
    Don't blur the large View / Report buttons.
    """

    text_lower = text.lower().strip()

    ignored = {
        "view",
        "report",
        "refresh",
        "buy",
        "cancel",
        "confirm",
        "close"
    }

    return text_lower in ignored


def calculate_dark_ratio(
    gray,
    x1,
    y1,
    x2,
    y2
):
    """
    Calculates how much dark text exists inside
    an OCR region.
    """

    h, w = gray.shape

    x1 = max(
        0,
        min(w, int(x1))
    )

    y1 = max(
        0,
        min(h, int(y1))
    )

    x2 = max(
        0,
        min(w, int(x2))
    )

    y2 = max(
        0,
        min(h, int(y2))
    )

    if x2 <= x1 or y2 <= y1:
        return 0

    roi = gray[
        y1:y2,
        x1:x2
    ]

    if roi.size == 0:
        return 0

    dark_pixels = np.sum(
        roi < 145
    )

    return dark_pixels / roi.size


def blur_proof_text(
    image_data: bytes,
    blur_everything: bool = True
) -> bytes:
    """
    Card-aware username blur.

    ONLY the proof-image blur logic is handled here.
    It detects each visible proof card independently, including
    partially visible cards at the bottom of a screenshot, then
    searches only the username band at the top of each card.

    Dates, times, buttons, refresh icons, item icons, and the rest
    of the screenshot are deliberately outside the target region.
    """

    try:
        print("[PROOF] Starting updated card-by-card username blur...")

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

        # =========================================================
        # 1. DETECT THE LEFT-SIDE PROOF CARDS
        # =========================================================

        left_limit = min(
            width,
            max(250, int(width * 0.68))
        )

        light = cv2.inRange(
            gray,
            185,
            255
        )

        card_mask = cv2.morphologyEx(
            light,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (13, 13)
            ),
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

            x, y, w, h = cv2.boundingRect(
                contour
            )

            if w < max(
                160,
                int(width * 0.30)
            ):
                continue

            if h < 45:
                continue

            if w > int(width * 0.68):
                continue

            if w / max(h, 1) < 1.5:
                continue

            ix1 = max(
                0,
                x + 5
            )

            iy1 = max(
                0,
                y + 5
            )

            ix2 = min(
                width,
                x + w - 5
            )

            iy2 = min(
                height,
                y + h - 5
            )

            if ix2 <= ix1 or iy2 <= iy1:
                continue

            inside = gray[
                iy1:iy2,
                ix1:ix2
            ]

            if inside.size == 0:
                continue

            if float(
                np.mean(inside >= 185)
            ) < 0.40:
                continue

            cards.append(
                (
                    x,
                    y,
                    w,
                    h
                )
            )

        # ---------------------------------------------------------
        # Row-projection fallback.
        # ---------------------------------------------------------

        projection = (
            light[:, :left_limit] > 0
        ).mean(axis=1)

        runs = []
        run_start = None

        for yy, density in enumerate(
            projection
        ):

            active = density >= 0.50

            if active and run_start is None:

                run_start = yy

            elif (
                not active
                and run_start is not None
            ):

                if yy - run_start >= 20:

                    runs.append(
                        (
                            run_start,
                            yy
                        )
                    )

                run_start = None

        if (
            run_start is not None
            and height - run_start >= 20
        ):

            runs.append(
                (
                    run_start,
                    height
                )
            )

        for ry1, ry2 in runs:

            span = gray[
                ry1:ry2,
                :left_limit
            ]

            if span.size == 0:
                continue

            col_density = (
                span >= 185
            ).mean(axis=0)

            active_cols = np.where(
                col_density >= 0.35
            )[0]

            if active_cols.size == 0:
                continue

            x1 = int(
                active_cols.min()
            )

            x2 = int(
                active_cols.max()
            ) + 1

            rw = x2 - x1

            if rw < max(
                160,
                int(width * 0.30)
            ):
                continue

            cards.append(
                (
                    x1,
                    ry1,
                    rw,
                    max(
                        45,
                        ry2 - ry1
                    )
                )
            )

        # ---------------------------------------------------------
        # Merge duplicate card detections.
        # ---------------------------------------------------------

        merged_cards = []

        for card in sorted(
            cards,
            key=lambda c: (
                c[1],
                c[0]
            )
        ):

            x, y, w, h = card

            x2 = x + w
            y2 = y + h

            merged = False

            for i, old in enumerate(
                merged_cards
            ):

                ox, oy, ow, oh = old

                ox2 = ox + ow
                oy2 = oy + oh

                overlap_x = (
                    min(x2, ox2)
                    - max(x, ox)
                )

                overlap_y = (
                    min(y2, oy2)
                    - max(y, oy)
                )

                same_card = (
                    overlap_x
                    > max(
                        20,
                        int(
                            min(w, ow)
                            * 0.45
                        )
                    )
                    and overlap_y > 0
                )

                close_same_card = (
                    abs(x - ox) <= 15
                    and abs(y - oy) <= 15
                    and abs(w - ow) <= 25
                )

                if (
                    same_card
                    or close_same_card
                ):

                    merged_cards[i] = (
                        min(x, ox),
                        min(y, oy),
                        max(x2, ox2)
                        - min(x, ox),
                        max(y2, oy2)
                        - min(y, oy)
                    )

                    merged = True

                    break

            if not merged:

                merged_cards.append(
                    card
                )

        cards = sorted(
            merged_cards,
            key=lambda c: (
                c[1],
                c[0]
            )
        )

        print(
            f"[PROOF] Visible proof cards detected: "
            f"{len(cards)}"
        )

        if not cards:

            print(
                "[PROOF] No proof cards detected; "
                "returning original image."
            )

            return image_data

        # =========================================================
        # 2. FIND USERNAME INSIDE EACH CARD ONLY
        # =========================================================

        username_regions = []

        for card_index, (
            x,
            y,
            w,
            h
        ) in enumerate(
            cards,
            1
        ):

            band_top = max(
                0,
                y + 5
            )

            band_bottom = min(
                height,
                y + min(
                    58,
                    max(
                        38,
                        int(h * 0.42)
                    )
                )
            )

            band_left = max(
                0,
                x + 8
            )

            band_right = min(
                width,
                x + int(w * 0.60)
            )

            if (
                band_right <= band_left
                or band_bottom <= band_top
            ):
                continue

            roi = gray[
                band_top:band_bottom,
                band_left:band_right
            ]

            if roi.size == 0:
                continue

            # -----------------------------------------------------
            # DARK TEXT DETECTOR
            # -----------------------------------------------------

            dark = cv2.inRange(
                roi,
                0,
                135
            )

            dark = cv2.morphologyEx(
                dark,
                cv2.MORPH_OPEN,
                cv2.getStructuringElement(
                    cv2.MORPH_RECT,
                    (2, 2)
                ),
                iterations=1
            )

            grouped = cv2.dilate(
                dark,
                cv2.getStructuringElement(
                    cv2.MORPH_RECT,
                    (5, 2)
                ),
                iterations=1
            )

            grouped = cv2.morphologyEx(
                grouped,
                cv2.MORPH_CLOSE,
                cv2.getStructuringElement(
                    cv2.MORPH_RECT,
                    (13, 3)
                ),
                iterations=2
            )

            contours, _ = cv2.findContours(
                grouped,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            candidates = []

            for contour in contours:

                cx, cy, cw, ch = cv2.boundingRect(
                    contour
                )

                if cw < 15 or ch < 6:
                    continue

                if ch > 30:
                    continue

                if cw > roi.shape[1] * 0.95:
                    continue

                aspect = cw / max(
                    ch,
                    1
                )

                if aspect < 1.5:
                    continue

                box = roi[
                    max(0, cy):
                    min(
                        roi.shape[0],
                        cy + ch
                    ),
                    max(0, cx):
                    min(
                        roi.shape[1],
                        cx + cw
                    )
                ]

                if box.size == 0:
                    continue

                dark_ratio = float(
                    np.mean(
                        box <= 135
                    )
                )

                if dark_ratio < 0.025:
                    continue

                pad = 5

                sx1 = max(
                    0,
                    cx - pad
                )

                sy1 = max(
                    0,
                    cy - pad
                )

                sx2 = min(
                    roi.shape[1],
                    cx + cw + pad
                )

                sy2 = min(
                    roi.shape[0],
                    cy + ch + pad
                )

                surrounding = roi[
                    sy1:sy2,
                    sx1:sx2
                ]

                if surrounding.size == 0:
                    continue

                if float(
                    np.mean(surrounding)
                ) < 135:
                    continue

                candidates.append(
                    (
                        cx,
                        cy,
                        cx + cw,
                        cy + ch,
                        dark_ratio
                    )
                )

            # -----------------------------------------------------
            # OCR FALLBACK
            # -----------------------------------------------------

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

                texts = ocr_data.get(
                    "text",
                    []
                )

                lefts = ocr_data.get(
                    "left",
                    []
                )

                tops = ocr_data.get(
                    "top",
                    []
                )

                widths = ocr_data.get(
                    "width",
                    []
                )

                heights = ocr_data.get(
                    "height",
                    []
                )

                confs = ocr_data.get(
                    "conf",
                    []
                )

                for i, text in enumerate(
                    texts
                ):

                    text = str(
                        text
                    ).strip()

                    if not text:
                        continue

                    if is_date_or_time(
                        text
                    ):
                        continue

                    if is_button_text(
                        text
                    ):
                        continue

                    try:

                        conf = float(
                            confs[i]
                        )

                    except Exception:

                        conf = 0

                    if conf < 10:
                        continue

                    ox = int(
                        lefts[i] / 3
                    )

                    oy = int(
                        tops[i] / 3
                    )

                    ow = int(
                        widths[i] / 3
                    )

                    oh = int(
                        heights[i] / 3
                    )

                    if ow < 15 or oh < 5:
                        continue

                    ox2 = min(
                        roi.shape[1],
                        ox + ow
                    )

                    oy2 = min(
                        roi.shape[0],
                        oy + oh
                    )

                    if (
                        ox2 <= ox
                        or oy2 <= oy
                    ):
                        continue

                    ocr_box = roi[
                        oy:oy2,
                        ox:ox2
                    ]

                    if ocr_box.size == 0:
                        continue

                    dark_ratio = float(
                        np.mean(
                            ocr_box <= 140
                        )
                    )

                    if dark_ratio < 0.02:
                        continue

                    candidates.append(
                        (
                            ox,
                            oy,
                            ox2,
                            oy2,
                            dark_ratio
                        )
                    )

            except Exception as error:

                print(
                    f"[PROOF] OCR fallback error "
                    f"on card {card_index}: {error}"
                )

            if not candidates:

                print(
                    f"[PROOF] Card {card_index}: "
                    f"no username candidate."
                )

                continue

            # -----------------------------------------------------
            # MERGE NEIGHBOURING PIECES
            # -----------------------------------------------------

            candidates.sort(
                key=lambda item: (
                    item[1],
                    item[0]
                )
            )

            merged = []

            for (
                cx1,
                cy1,
                cx2,
                cy2,
                score
            ) in candidates:

                found = False

                for j, current in enumerate(
                    merged
                ):

                    mx1, my1, mx2, my2 = current

                    horizontal_gap = max(
                        0,
                        max(
                            mx1 - cx2,
                            cx1 - mx2
                        )
                    )

                    vertical_gap = max(
                        0,
                        max(
                            my1 - cy2,
                            cy1 - my2
                        )
                    )

                    if (
                        horizontal_gap <= 16
                        and vertical_gap <= 9
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
                        (
                            cx1,
                            cy1,
                            cx2,
                            cy2
                        )
                    )

            # -----------------------------------------------------
            # CHOOSE MOST USERNAME-LIKE LINE
            # -----------------------------------------------------

            best = None
            best_score = -1

            for (
                mx1,
                my1,
                mx2,
                my2
            ) in merged:

                mw = mx2 - mx1
                mh = my2 - my1

                if mw < 18 or mh < 5:
                    continue

                if mw / max(
                    mh,
                    1
                ) < 1.5:
                    continue

                full_y = (
                    band_top
                    + my1
                )

                if full_y > y + 58:
                    continue

                check = gray[
                    max(
                        0,
                        band_top + my1
                    ):
                    min(
                        height,
                        band_top + my2
                    ),
                    max(
                        0,
                        band_left + mx1
                    ):
                    min(
                        width,
                        band_left + mx2
                    )
                ]

                if check.size == 0:
                    continue

                darkness = float(
                    np.mean(
                        check <= 140
                    )
                )

                if darkness < 0.02:
                    continue

                score = (
                    mw
                    + darkness * 100
                    - (my1 * 0.5)
                )

                if score > best_score:

                    best_score = score

                    best = (
                        band_left + mx1,
                        band_top + my1,
                        band_left + mx2,
                        band_top + my2
                    )

            if best is not None:

                username_regions.append(
                    best
                )

                print(
                    f"[PROOF] Card {card_index}: "
                    f"username region {best}"
                )

        print(
            f"[PROOF] Username regions found: "
            f"{len(username_regions)}"
        )

        if not username_regions:

            print(
                "[PROOF] No username regions found; "
                "returning original."
            )

            return image_data

        # =========================================================
        # 3. BLUR ONLY THE DETECTED USERNAME REGIONS
        # =========================================================

        result = original.copy()

        for (
            x1,
            y1,
            x2,
            y2
        ) in username_regions:

            rw = x2 - x1
            rh = y2 - y1

            pad_x = max(
                5,
                int(rw * 0.08)
            )

            pad_y = max(
                4,
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

            crop = result.crop(
                (
                    bx1,
                    by1,
                    bx2,
                    by2
                )
            )

            crop = crop.filter(
                ImageFilter.GaussianBlur(
                    radius=12
                )
            )

            result.paste(
                crop,
                (
                    bx1,
                    by1
                )
            )

        # =========================================================
        # 4. SAVE
        # =========================================================

        output = io.BytesIO()

        result.save(
            output,
            format="PNG"
        )

        output.seek(0)

        print(
            "[PROOF] Updated username-only blur complete."
        )

        return output.getvalue()

    except Exception as error:

        print(
            f"Proof processing error: {error}"
        )

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

        # =====================================================
        # GET THE EARLIEST / OLDEST MESSAGES FIRST
        # =====================================================

        messages = []

        async for message in interaction.channel.history(
            limit=amount,
            oldest_first=True
        ):

            messages.append(
                message
            )

            if len(messages) >= amount:
                break

        if not messages:

            return await interaction.followup.send(

                "❌ There are no messages to delete.",

                ephemeral=True
            )

        # =====================================================
        # DELETE THE SELECTED OLDEST MESSAGES
        # =====================================================

        deleted_count = 0

        # Discord bulk deletion only works for messages
        # newer than 14 days. Older messages must be deleted
        # individually.
        bulk_messages = []

        for message in messages:

            age = (
                discord.utils.utcnow()
                - message.created_at
            )

            if age.days < 14:

                bulk_messages.append(
                    message
                )

            else:

                try:

                    await message.delete()

                    deleted_count += 1

                except discord.NotFound:

                    pass

                except discord.Forbidden:

                    pass

                except discord.HTTPException as error:

                    print(
                        f"Old message delete error: {error}"
                    )

        # =====================================================
        # BULK DELETE NEWER MESSAGES
        # =====================================================

        if bulk_messages:

            try:

                deleted = (
                    await interaction.channel.delete_messages(
                        bulk_messages
                    )
                )

                deleted_count += len(
                    deleted
                )

            except discord.HTTPException:

                # Fallback to individual deletion
                # if bulk deletion fails.
                for message in bulk_messages:

                    try:

                        await message.delete()

                        deleted_count += 1

                    except discord.NotFound:

                        pass

                    except discord.Forbidden:

                        pass

                    except discord.HTTPException as error:

                        print(
                            f"Message delete error: {error}"
                        )

        # =====================================================
        # RESULT
        # =====================================================

        await interaction.followup.send(

            f"🗑️ Deleted **{deleted_count}** "
            f"earliest message(s).",

            ephemeral=True
        )

    except discord.Forbidden:

        await interaction.followup.send(

            "❌ I don't have permission "
            "to delete messages.",

            ephemeral=True
        )

    except discord.HTTPException as error:

        print(
            f"Clear command error: {error}"
        )

        await interaction.followup.send(

            "❌ Discord returned an error "
            "while deleting messages.",

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

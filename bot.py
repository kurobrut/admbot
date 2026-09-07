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
from PIL import Image, ImageFilter, ImageDraw

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

# Render and other cloud hosts may use an ephemeral filesystem.  These
# environment variables are therefore the persistent source of truth for
# server/channel/role IDs.  Set them once in the hosting dashboard and they
# survive future code updates/redeploys.
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


# Environment variables win over config.json so settings survive cloud redeploys.
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


# =========================================================
# WATERMARK
# =========================================================

# By default the bot looks for watermark.png in the same folder as bot.py.
# You can optionally override this with the WATERMARK_PATH environment variable.
WATERMARK_PATH = os.getenv(
    "WATERMARK_PATH",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "watermark.png"
    )
)

# Pink privacy-blur settings. These are intentionally configurable so the
# blur can match pastel/pink proof screenshots like the example you provided.
BLUR_TINT = (255, 150, 215)
BLUR_TINT_ALPHA = 105
BLUR_RADIUS = 13


def apply_pink_blur(
    image,
    x1,
    y1,
    x2,
    y2,
    radius=BLUR_RADIUS
):
    """
    Apply a soft pink privacy blur.

    The blur is deliberately broad enough to make the text unreadable,
    while the mask is feathered so it looks like a soft privacy haze
    instead of a hard rectangular block.
    """
    width, height = image.size

    x1 = max(0, min(width, int(x1)))
    y1 = max(0, min(height, int(y1)))
    x2 = max(0, min(width, int(x2)))
    y2 = max(0, min(height, int(y2)))

    if x2 <= x1 or y2 <= y1:
        return

    # Extra room allows the Gaussian blur to spread naturally.
    feather = max(7, int(radius * 1.4))
    ex1 = max(0, x1 - feather)
    ey1 = max(0, y1 - feather)
    ex2 = min(width, x2 + feather)
    ey2 = min(height, y2 + feather)

    base_crop = image.crop((ex1, ey1, ex2, ey2)).convert("RGBA")

    # Strong blur so black text and colored text cannot remain readable.
    blurred = base_crop.filter(
        ImageFilter.GaussianBlur(
            radius=max(8, int(radius))
        )
    )

    # Pink-tinted blurred layer.
    pink_layer = Image.new(
        "RGBA",
        blurred.size,
        BLUR_TINT + (170,)
    )

    processed = Image.alpha_composite(
        blurred,
        pink_layer
    )

    # Soft capsule/rounded privacy area.
    mask = Image.new(
        "L",
        processed.size,
        0
    )

    draw = ImageDraw.Draw(mask)

    ix1 = x1 - ex1
    iy1 = y1 - ey1
    ix2 = x2 - ex1
    iy2 = y2 - ey1

    box_h = max(1, iy2 - iy1)

    draw.rounded_rectangle(
        (ix1, iy1, ix2, iy2),
        radius=max(8, box_h // 2),
        fill=255
    )

    # Feather the outside edge.
    mask = mask.filter(
        ImageFilter.GaussianBlur(
            radius=max(4, int(radius * 0.55))
        )
    )

    # Keep the center of the username area fully opaque.
    inner = Image.new(
        "L",
        processed.size,
        0
    )

    inner_draw = ImageDraw.Draw(inner)

    inner_draw.rounded_rectangle(
        (
            ix1 + 2,
            iy1 + 2,
            ix2 - 2,
            iy2 - 2
        ),
        radius=max(7, (box_h // 2) - 2),
        fill=255
    )

    # Composite a solid center into the feathered mask. This prevents
    # dark/pink letters from remaining readable in the middle.
    mask = Image.composite(
        Image.new(
            "L",
            processed.size,
            255
        ),
        mask,
        inner
    )

    blended = Image.composite(
        processed,
        base_crop,
        mask
    )

    image.paste(
        blended.convert("RGB"),
        (ex1, ey1)
    )


def apply_proof_watermark(image_data: bytes) -> bytes:
    """Apply watermark.png to the CENTER of a processed proof."""

    try:
        if not os.path.isfile(WATERMARK_PATH):
            print(
                f"[PROOF] Watermark not found: {WATERMARK_PATH}. "
                "Sending proof without watermark."
            )
            return image_data

        base = Image.open(
            io.BytesIO(image_data)
        ).convert("RGBA")

        watermark = Image.open(
            WATERMARK_PATH
        ).convert("RGBA")

        # Remove transparent padding around the supplied 500x500 template.
        alpha = watermark.getchannel("A")
        bbox = alpha.getbbox()

        if bbox:
            watermark = watermark.crop(bbox)

        if watermark.width <= 0 or watermark.height <= 0:
            print("[PROOF] Watermark image has no visible content.")
            return image_data

        # Center watermark. The logo is kept large enough to be visible but
        # not so large that it completely hides the proof.
        max_width = max(80, int(base.width * 0.16))
        max_height = max(40, int(base.height * 0.10))

        watermark.thumbnail(
            (max_width, max_height),
            Image.Resampling.LANCZOS
        )

        x = max(
            0,
            (base.width - watermark.width) // 2
        )

        y = max(
            0,
            (base.height - watermark.height) // 2
        )

        # Keep the original transparency and logo colors.
        base.alpha_composite(
            watermark,
            (x, y)
        )

        output = io.BytesIO()
        base.convert("RGB").save(
            output,
            format="PNG"
        )
        output.seek(0)

        print(
            f"[PROOF] Center watermark applied from {WATERMARK_PATH} "
            f"at ({x}, {y}), size={watermark.width}x{watermark.height}."
        )

        return output.getvalue()

    except Exception as error:
        print(
            f"[PROOF] Watermark error: {error}"
        )
        traceback.print_exc()
        return image_data


def blur_proof_text(
    image_data: bytes,
    blur_everything: bool = True
) -> bytes:
    """
    Robust proof privacy processor.

    Every proof-card row is inspected independently. The detector finds the
    FIRST actual text line inside the card (the username line), then covers
    ALL text pieces on that line. It supports black/dark usernames and
    pink/pastel-pink usernames.

    A card-wide username fallback is used only when the text detector cannot
    find a line, so an OCR/color failure cannot leave a username exposed.
    """
    try:
        print("[PROOF] Starting robust username protection...")

        original = Image.open(
            io.BytesIO(image_data)
        ).convert("RGB")

        width, height = original.size

        if width <= 0 or height <= 0:
            return apply_proof_watermark(image_data)

        rgb = np.array(original)
        gray = cv2.cvtColor(
            rgb,
            cv2.COLOR_RGB2GRAY
        )

        # =========================================================
        # 1. FIND CARD ROWS
        # =========================================================

        # Proof cards are on the left side.
        left_limit = min(
            width,
            max(
                260,
                int(width * 0.72)
            )
        )

        left_gray = gray[:, :left_limit]

        # Only use this mask to find the horizontal card rows.
        light = cv2.inRange(
            left_gray,
            190,
            255
        )

        row_density = (
            light > 0
        ).mean(axis=1)

        row_runs = []
        run_start = None

        for yy, density in enumerate(
            row_density
        ):

            active = density >= 0.50

            if active and run_start is None:
                run_start = yy

            elif (
                not active
                and run_start is not None
            ):

                if yy - run_start >= 35:
                    row_runs.append(
                        (
                            run_start,
                            yy
                        )
                    )

                run_start = None

        if (
            run_start is not None
            and height - run_start >= 35
        ):
            row_runs.append(
                (
                    run_start,
                    height
                )
            )

        # Fallback contour detection if the projection finds nothing.
        if not row_runs:

            contour_mask = cv2.morphologyEx(
                light,
                cv2.MORPH_CLOSE,
                cv2.getStructuringElement(
                    cv2.MORPH_RECT,
                    (9, 5)
                ),
                iterations=1
            )

            contours, _ = cv2.findContours(
                contour_mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:

                x, y, w, h = cv2.boundingRect(
                    contour
                )

                if (
                    w >= int(width * 0.35)
                    and h >= 40
                ):
                    row_runs.append(
                        (
                            y,
                            min(
                                height,
                                y + h
                            )
                        )
                    )

        # Only merge actual overlapping runs.
        row_runs.sort(
            key=lambda r: r[0]
        )

        clean_runs = []

        for y1, y2 in row_runs:

            if not clean_runs:
                clean_runs.append(
                    [y1, y2]
                )
                continue

            py1, py2 = clean_runs[-1]

            if y1 <= py2:
                clean_runs[-1][1] = max(
                    py2,
                    y2
                )
            else:
                clean_runs.append(
                    [y1, y2]
                )

        cards = [
            (
                0,
                y1,
                left_limit,
                y2 - y1
            )
            for y1, y2 in clean_runs
            if y2 - y1 >= 35
        ]

        print(
            f"[PROOF] Card rows detected: {len(cards)}"
        )

        # =========================================================
        # 2. BLACK + PINK TEXT MASK
        # =========================================================

        hsv = cv2.cvtColor(
            rgb,
            cv2.COLOR_RGB2HSV
        )

        hue = hsv[:, :, 0]
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]

        r = rgb[:, :, 0].astype(np.int16)
        g = rgb[:, :, 1].astype(np.int16)
        b = rgb[:, :, 2].astype(np.int16)

        # Dark/black/gray text.
        dark = (
            (value <= 180)
            & (saturation <= 150)
        ).astype(
            np.uint8
        ) * 255

        # Pink/magenta/pastel-pink text.
        pink = (
            (
                (
                    (
                        (hue >= 130)
                        & (hue <= 179)
                    )
                    |
                    (
                        (hue >= 0)
                        & (hue <= 20)
                    )
                )
                & (saturation >= 25)
                & (value >= 95)
                & (r >= g + 40)
            )
            |
            (
                (r >= 190)
                & (r >= g + 40)
                & (r >= b - 30)
                & (value >= 95)
            )
        ).astype(
            np.uint8
        ) * 255

        text_mask = cv2.bitwise_or(
            dark,
            pink
        )

        text_mask = cv2.morphologyEx(
            text_mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (2, 2)
            )
        )

        # Connect characters into words.
        text_mask = cv2.dilate(
            text_mask,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (3, 2)
            ),
            iterations=1
        )

        text_mask = cv2.morphologyEx(
            text_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (9, 3)
            ),
            iterations=1
        )

        # =========================================================
        # 3. FIND THE USERNAME LINE IN EVERY CARD
        # =========================================================

        regions = []

        # Use the strong color mask for finding the actual text.
        # Background pastel-pink is deliberately excluded by the
        # relatively high red-vs-green threshold above.
        strong_text = cv2.bitwise_or(
            dark,
            pink
        )

        for card_index, (
            cx,
            cy,
            cw,
            ch
        ) in enumerate(
            cards,
            1
        ):

            card_right = min(
                width,
                cx + cw
            )

            # Start a few pixels below the row edge. This avoids the
            # rounded card border / pink background being mistaken for
            # the username.
            search_y1 = min(
                height,
                cy + 5
            )

            search_y2 = min(
                height,
                cy + min(
                    70,
                    max(
                        45,
                        int(ch * 0.48)
                    )
                )
            )

            search_x1 = max(
                0,
                cx + 3
            )

            search_x2 = min(
                card_right - 3,
                cx + max(
                    180,
                    int(cw * 0.50)
                )
            )

            roi = strong_text[
                search_y1:search_y2,
                search_x1:search_x2
            ]

            # -----------------------------------------------------
            # Find horizontal text lines from pixel density.
            #
            # This is more reliable than one giant contour because
            # the username can consist of several disconnected
            # characters and the date is a separate line.
            # -----------------------------------------------------

            line_regions = []

            if roi.size:

                row_counts = (
                    roi > 0
                ).sum(axis=1)

                active_rows = (
                    row_counts >= 3
                )

                runs = []
                s = None

                for ry, active in enumerate(
                    active_rows
                ):

                    if active and s is None:
                        s = ry

                    elif (
                        not active
                        and s is not None
                    ):

                        if ry - s >= 2:
                            runs.append(
                                (
                                    s,
                                    ry - 1
                                )
                            )

                        s = None

                if (
                    s is not None
                    and len(active_rows) - s >= 2
                ):
                    runs.append(
                        (
                            s,
                            len(active_rows) - 1
                        )
                    )

                # The FIRST meaningful text run is the username.
                if runs:

                    first_start, first_end = runs[0]

                    # Include nearby anti-aliased rows.
                    first_start = max(
                        0,
                        first_start - 2
                    )

                    first_end = min(
                        roi.shape[0] - 1,
                        first_end + 2
                    )

                    line = roi[
                        first_start:first_end + 1
                    ]

                    xs = np.where(
                        line.any(axis=0)
                    )[0]

                    if xs.size:

                        line_x1 = (
                            search_x1
                            + int(xs.min())
                        )

                        line_x2 = (
                            search_x1
                            + int(xs.max())
                            + 1
                        )

                        line_y1 = (
                            search_y1
                            + first_start
                        )

                        line_y2 = (
                            search_y1
                            + first_end
                            + 1
                        )

                        # Make sure this is actually on the left
                        # username side, not the time field.
                        if (
                            line_x1
                            < cx + int(cw * 0.50)
                        ):

                            line_regions.append(
                                (
                                    line_x1,
                                    line_y1,
                                    line_x2,
                                    line_y2
                                )
                            )

            # -----------------------------------------------------
            # OCR fallback.
            # -----------------------------------------------------

            if not line_regions:

                try:

                    crop = rgb[
                        search_y1:search_y2,
                        search_x1:search_x2
                    ]

                    enlarged = cv2.resize(
                        crop,
                        None,
                        fx=4,
                        fy=4,
                        interpolation=cv2.INTER_CUBIC
                    )

                    data = pytesseract.image_to_data(
                        enlarged,
                        config="--oem 3 --psm 11",
                        output_type=pytesseract.Output.DICT
                    )

                    ocr_boxes = []

                    for i, raw_text in enumerate(
                        data.get(
                            "text",
                            []
                        )
                    ):

                        detected_text = str(
                            raw_text
                        ).strip()

                        if not detected_text:
                            continue

                        if is_date_or_time(
                            detected_text
                        ):
                            continue

                        if is_button_text(
                            detected_text
                        ):
                            continue

                        try:
                            confidence = float(
                                data["conf"][i]
                            )
                        except Exception:
                            confidence = 0

                        if confidence < 5:
                            continue

                        tx = int(
                            data["left"][i] / 4
                        )

                        ty = int(
                            data["top"][i] / 4
                        )

                        tw = int(
                            data["width"][i] / 4
                        )

                        th = int(
                            data["height"][i] / 4
                        )

                        if (
                            tw < 8
                            or th < 3
                            or th > 35
                        ):
                            continue

                        ax1 = (
                            search_x1
                            + tx
                        )

                        ay1 = (
                            search_y1
                            + ty
                        )

                        ax2 = min(
                            width,
                            ax1 + tw
                        )

                        ay2 = min(
                            height,
                            ay1 + th
                        )

                        if (
                            ax1
                            < cx + int(cw * 0.50)
                            and ay1
                            < search_y1 + 38
                        ):
                            ocr_boxes.append(
                                (
                                    ax1,
                                    ay1,
                                    ax2,
                                    ay2
                                )
                            )

                    if ocr_boxes:

                        # Use the uppermost OCR line, but keep ALL
                        # boxes on that line.
                        top_y = min(
                            box[1]
                            for box in ocr_boxes
                        )

                        same_line = [
                            box
                            for box in ocr_boxes
                            if abs(
                                box[1] - top_y
                            ) <= 10
                        ]

                        if same_line:

                            line_regions.append(
                                (
                                    min(
                                        box[0]
                                        for box in same_line
                                    ),
                                    max(
                                        cy,
                                        min(
                                            box[1]
                                            for box in same_line
                                        ) - 3
                                    ),
                                    max(
                                        box[2]
                                        for box in same_line
                                    ),
                                    max(
                                        box[3]
                                        for box in same_line
                                    ) + 3
                                )
                            )

                except Exception as error:

                    print(
                        f"[PROOF] Card {card_index} "
                        f"OCR error: {error}"
                    )

            # -----------------------------------------------------
            # Add detected username line.
            # -----------------------------------------------------

            if line_regions:

                x1, y1, x2, y2 = line_regions[0]

                # Small expansion around the actual username.
                # Do NOT expand all the way to the date line.
                x1 = max(
                    cx + 3,
                    x1 - 6
                )

                x2 = min(
                    card_right - 5,
                    x2 + 6
                )

                y1 = max(
                    cy + 3,
                    y1 - 5
                )

                y2 = min(
                    height,
                    y2 + 5
                )

                regions.append(
                    (
                        x1,
                        y1,
                        x2,
                        y2
                    )
                )

                print(
                    f"[PROOF] Card {card_index}: "
                    f"username detected at "
                    f"({x1}, {y1}, {x2}, {y2})"
                )

            else:

                # -------------------------------------------------
                # Last-resort fallback.
                #
                # Compact enough to avoid the date, but wide enough
                # to protect long usernames.
                # -------------------------------------------------

                fallback_x1 = max(
                    0,
                    cx + 5
                )

                fallback_x2 = min(
                    card_right - 5,
                    cx + max(
                        150,
                        int(cw * 0.55)
                    )
                )

                fallback_y1 = min(
                    height,
                    cy + 12
                )

                fallback_y2 = min(
                    height,
                    cy + 40
                )

                if (
                    fallback_x2 > fallback_x1
                    and fallback_y2 > fallback_y1
                ):

                    regions.append(
                        (
                            fallback_x1,
                            fallback_y1,
                            fallback_x2,
                            fallback_y2
                        )
                    )

                    print(
                        f"[PROOF] Card {card_index}: "
                        "using fallback username protection"
                    )

        # =========================================================
        # 4. MERGE ONLY OVERLAPPING REGIONS
        # =========================================================

        regions.sort(
            key=lambda r: (
                r[1],
                r[0]
            )
        )

        merged_regions = []

        for region in regions:

            x1, y1, x2, y2 = region

            merged = False

            for i, old in enumerate(
                merged_regions
            ):

                ox1, oy1, ox2, oy2 = old

                ix = (
                    min(x2, ox2)
                    - max(x1, ox1)
                )

                iy = (
                    min(y2, oy2)
                    - max(y1, oy1)
                )

                if (
                    ix > 0
                    and iy > 0
                ):

                    merged_regions[i] = (
                        min(x1, ox1),
                        min(y1, oy1),
                        max(x2, ox2),
                        max(y2, oy2)
                    )

                    merged = True
                    break

            if not merged:
                merged_regions.append(
                    region
                )

        print(
            f"[PROOF] FINAL username regions: "
            f"{len(merged_regions)}"
        )

        # =========================================================
        # 5. BLUR EVERY USERNAME
        # =========================================================

        result = original.copy()

        for index, (
            x1,
            y1,
            x2,
            y2
        ) in enumerate(
            merged_regions,
            1
        ):

            # Small safety padding around the detected letters.
            pad_x = max(
                5,
                int(
                    (x2 - x1) * 0.04
                )
            )

            pad_y = max(
                3,
                int(
                    (y2 - y1) * 0.16
                )
            )

            apply_pink_blur(
                result,
                x1 - pad_x,
                y1 - pad_y,
                x2 + pad_x,
                y2 + pad_y,
                radius=BLUR_RADIUS
            )

            print(
                f"[PROOF] Blurred username "
                f"{index}/{len(merged_regions)}"
            )

        # =========================================================
        # 6. WATERMARK LAST
        # =========================================================

        output = io.BytesIO()

        result.save(
            output,
            format="PNG"
        )

        output.seek(0)

        return apply_proof_watermark(
            output.getvalue()
        )

    except Exception as error:

        print(
            f"[PROOF] Processing error: "
            f"{error}"
        )

        traceback.print_exc()

        return apply_proof_watermark(
            image_data
        )


# =========================================================
# PERMISSION / ERROR HELPERS
# =========================================================

def is_staff(interaction: discord.Interaction):
    """Return True for administrators or the configured staff role."""
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.guild_permissions.administrator:
        return True

    staff_role_id = config.get("staff_role_id")
    if staff_role_id:
        return any(role.id == staff_role_id for role in interaction.user.roles)

    # If no staff role is configured, fall back to Manage Channels.
    return interaction.user.guild_permissions.manage_channels


def missing_bot_permissions(channel, *permissions):
    """Return human-readable bot permissions missing in a channel."""
    guild = getattr(channel, "guild", None)
    if not guild:
        return list(permissions)
    me = guild.me
    if me is None:
        return list(permissions)
    perms = channel.permissions_for(me)
    return [name for name, attr in permissions if not getattr(perms, attr, False)]


def member_hierarchy_error(interaction: discord.Interaction, target: discord.Member):
    """Check whether the invoking staff member may moderate target."""
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
    """Safely send an interaction response without passing ``view=None`` to discord.py."""
    try:
        kwargs = {
            "content": content,
            "embed": embed,
            "ephemeral": ephemeral,
        }
        # discord.py expects the view argument to be omitted when there is no view.
        # Passing view=None can cause ``None.is_finished()`` errors in some versions.
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
    """Process queued channel renames while respecting Discord rate limits."""
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

    # Keep the embed narrow and stacked so it reads cleanly on both
    # Discord mobile and desktop/Windows without awkward line wrapping.
    embed = discord.Embed(
        title="🌸 ୨୧ welcome to ali's adm house! ♡",
        description=(
            f"Welcome {member.mention}! We're so happy to have you here! ♡\n\n"
            "✦ **Getting Started**\n"
            "• Check out our products and shop listings.\n"
            "• Open a support ticket for custom orders or questions.\n"
            "• Feel free to chat and enjoy the community! ♡"
        ),
        color=PINK
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🌸 Customer", value=member.mention, inline=False)
    embed.add_field(name="⭐ Members", value=f"`{member.guild.member_count}`", inline=False)
    embed.set_footer(text="୨୧ ali's adm house • Welcome ♡")
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

    # Compact, stacked layout for consistent rendering on mobile and desktop.
    embed = discord.Embed(
        title="💔 ୨୧ goodbye, see you soon! ♡",
        description=(
            f"**{member.name}** has left **ali's adm house**... 💔\n\n"
            "We're sad to see you leave, but we hope to see you back again soon! ♡"
        ),
        color=GRAY
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👋 Member", value=f"`{member.name}`", inline=False)
    embed.set_footer(text="୨୧ ali's adm house • Goodbye ♡")
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

        # Reuse an existing ticket if one exists.
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

            embed = discord.Embed(
                title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
                description=(f"Welcome {interaction.user.mention}! ♡\n\n"
                             "Thank you for contacting **ali's adm house**!\n\n"
                             "Please tell us what you need help with.\n\n"
                             "୨୧ **House:**\n୨୧ **Build type:**\n\n"
                             "A staff member will be with you shortly. ♡"),
                color=PINK
            )
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

        bot_commands_channel = discord.utils.get(guild.text_channels, name="₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼")
        commands_mention = bot_commands_channel.mention if bot_commands_channel else "`#₊˚⊹♡-𝓫𝓸𝓽-𝓬𝓸𝓶𝓶𝓪𝓷𝓭𝓼`"
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

    embed = discord.Embed(
        title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
        description="Need help with an order?\nWant to ask about one of our houses?\n\nClick **🎫 Open Ticket** below to create a private ticket with our staff! ♡",
        color=PINK
    )
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
        me = interaction.guild.me
        if me and (customer_role.is_default() or customer_role.managed or customer_role >= me.top_role):
            return await interaction.response.send_message(
                "❌ I cannot automatically give that customer role because it is managed or too high for my role.",
                ephemeral=True
            )
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

@bot.tree.command(name="ticketpanel", description="Send a ticket panel.")
async def ticketpanel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_staff(interaction):
        return await safe_send(interaction, "❌ You need staff permissions.", ephemeral=True)
    missing = missing_bot_permissions(channel, ("View Channel", "view_channel"), ("Send Messages", "send_messages"), ("Embed Links", "embed_links"))
    if missing:
        return await safe_send(interaction, "❌ I am missing " + ", ".join(f"**{x}**" for x in missing) + " in that channel.", ephemeral=True)

    embed = discord.Embed(
        title="୨୧・𝘴𝘶𝘱𝘱𝘰𝘳𝘵 𝘵𝘪𝘤𝘬𝘦𝘵𝘴 ♡",
        description="Need help? ♡\n\nClick **🎫 Open Ticket** below to create a private ticket.",
        color=PINK
    )
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
        # Validate that Discord actually delivered a readable image before OCR/PIL work.
        with Image.open(io.BytesIO(image_data)) as check:
            check.verify()

        blurred_data = blur_proof_text(
            image_data,
            blur_everything=bool(config.get("blur_everything", True))
        )
        file = discord.File(io.BytesIO(blurred_data), filename="proof.png")
        await proof_channel.send(
            content=f"♡ **New Proof!**\nThank you so much! ♡\nSubmitted by {interaction.user.mention}",
            file=file,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user])
        )
        await interaction.followup.send("♡ Your proof has been submitted!", ephemeral=True)
    except (OSError, ValueError):
        await interaction.followup.send("❌ That image could not be read. Please upload a valid PNG/JPG/WEBP image.", ephemeral=True)
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

    embed = discord.Embed(
        title="୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡",
        description=f"**{discord.utils.escape_markdown(message)}**\n\n୨୧ **𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳**\n{interaction.user.mention}\n\nThank you so much! ♡",
        color=PINK
    )
    embed.set_author(name="୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡")

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
        async for msg in channel.history(limit=None):
            if msg.author == bot.user and any(
                embed.title == "୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡" for embed in msg.embeds
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

    states = {
        "available": ("🟢・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘢𝘷𝘢𝘪𝘭𝘢𝘣𝘭𝘦", "Our shop is currently **OPEN** for new orders! ♡", GREEN, "🟢-available"),
        "busy": ("🔴・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘣𝘶𝘴𝘺", "Our shop is currently **BUSY**! ♡\nOrders may take a little longer.", RED, "🔴-busy"),
        "closed": ("⚪・𝘰𝘳𝘥𝘦𝘳𝘴 𝘢𝘳𝘦 𝘤𝘭𝘰𝘴𝘦𝘥", "Our shop is currently **CLOSED**! ♡", GRAY, "⚪-closed")
    }
    title, description, color, channel_name = states.get(state.value, states["closed"])
    embed = discord.Embed(title=title, description=description, color=color)
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

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        # Remove roles belonging to this dropdown
        role_ids = {
            role.id
            for role in self.roles
        }

        self.selected_roles[:] = [
            role
            for role in self.selected_roles
            if role.id not in role_ids
        ]

        # Add newly selected roles
        for value in self.values:

            role = interaction.guild.get_role(
                int(value)
            )

            if role:
                self.selected_roles.append(role)

        await interaction.response.defer()


class SayRoleView(discord.ui.View):

    def __init__(
        self,
        interaction,
        channel,
        message
    ):

        super().__init__(timeout=120)

        self.original_user = interaction.user
        self.channel = channel
        self.message = message

        self.selected_roles = []

        guild = interaction.guild
        me = guild.me

        # Only roles the bot can actually mention/manage
        roles = [
            role
            for role in guild.roles
            if not role.is_default()
            and (not me or role < me.top_role)
        ]

        # Discord allows a maximum of 25 options
        # per select menu.
        for i in range(0, len(roles), 25):

            chunk = roles[i:i + 25]

            self.add_item(
                SayRoleSelect(
                    chunk,
                    self.selected_roles
                )
            )

            # Discord views support max 5 action rows.
            if len(self.children) >= 5:
                break

        # Send button
        self.add_item(
            SaySendButton(self)
        )


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
        embed = discord.Embed(
            title="୨୧・♡ 𝒶𝓃𝓃𝑜𝓊𝓃𝒸𝑒𝓂𝑒𝓃𝓉 ♡・୨୧",
            description="╭・₊˚⊹ **hello everyone!** ⊹˚₊・╮\n\n" + view.message + "\n\n╰・₊˚⊹ ♡ ⊹˚₊・╯",
            color=PINK
        )
        embed.set_footer(text="♡ thank you for being part of our community ♡")
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
    # Five component rows means at most four dropdowns plus the send button.
    if len(manageable_roles) > 100:
        return await safe_send(interaction, "❌ There are too many manageable roles for this announcement menu. Please reduce the number of roles or mention roles manually.", ephemeral=True)

    try:
        view = SayRoleView(interaction, channel, message)
        await interaction.response.send_message(
            "୨୧・♡ **Choose the role(s) to mention** ♡・୨୧\n\nYou can select multiple roles, then press **Send Announcement ♡**.",
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
        embed = discord.Embed(title="⚠️ You have been warned", description=f"Reason: **{discord.utils.escape_markdown(reason)}**", color=RED)
        embed.set_footer(text="ali's adm house")
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
    """Parse durations such as 10m, 1h, 2d, or 1w."""
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

    # Discord timeouts have a maximum of 28 days.
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
        # Try to notify the user before removing them from the server.
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

    embed = discord.Embed(
        title="୨୧・𝘯𝘦𝘸 𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳 𝘷𝘰𝘶𝘤𝘩 ♡",
        description=f"**{discord.utils.escape_markdown(message)}**\n\n୨୧ **𝘤𝘶𝘴𝘵𝘰𝘮𝘦𝘳**\n{ctx.author.mention}\n\nThank you so much! ♡",
        color=PINK
    )
    embed.set_author(name="୨୧ 𝘢𝘭𝘪'𝘴 𝘢𝘥𝘮 𝘩𝘰𝘶𝘴𝘦 ♡")
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

TOKEN = os.getenv(
    "DISCORD_TOKEN"
)

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN is not set."
    )


keep_alive()

bot.run(TOKEN)

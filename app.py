import base64
import io
import os

import requests
from flask import Flask, request, jsonify
from PIL import Image, ImageDraw, ImageFont, ImageFilter

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HELSA = os.path.join(BASE_DIR, "HelsaDisplay-Regular.otf")
EXMOUTH = os.path.join(BASE_DIR, "exmouth_.ttf")
SAUDAGAR = os.path.join(BASE_DIR, "Saudagar.ttf")

HANDLE_TEXT = "@rodi.club"
HANDLE_FONT_SIZE = 34
HANDLE_BOTTOM_MARGIN = 90

MAX_TEXT_WIDTH_RATIO = 0.76
FONT_SIZE = 134
EXMOUTH_SIZE = 216
LINE_SPACING = 0.98
SPACE_WIDTH_RATIO = 0.30
MAX_CHARS = 50
EXMOUTH_OVERLAP = 60

TARGET_W, TARGET_H = 1024, 1365  # 3:4 ("4:3") post ratio - all posts/carousel images are cropped to this


def fit_to_target(img, target_w=TARGET_W, target_h=TARGET_H):
    # Center-crop (after a cover-resize) so every image lands on the same 4:3 canvas,
    # regardless of what size the AI generator actually returned (1024x1024, 1024x1536, etc).
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # source is relatively wider - scale to match height, crop sides
        new_h = target_h
        new_w = int(src_w * (target_h / src_h))
    else:
        # source is relatively taller - scale to match width, crop top/bottom
        new_w = target_w
        new_h = int(src_h * (target_w / src_w))

    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def compose(bg_img, quote_text):
    quote_text = quote_text.strip()
    if len(quote_text) > MAX_CHARS:
        quote_text = quote_text[:MAX_CHARS].rsplit(" ", 1)[0]

    bg_img = fit_to_target(bg_img)
    canvas_w, canvas_h = bg_img.size
    bg = bg_img.convert("RGBA")
    draw = ImageDraw.Draw(bg)

    helsa = ImageFont.truetype(HELSA, FONT_SIZE)
    binggo = ImageFont.truetype(EXMOUTH, EXMOUTH_SIZE)
    max_width = canvas_w * MAX_TEXT_WIDTH_RATIO
    space_w = FONT_SIZE * SPACE_WIDTH_RATIO

    words = quote_text.split(" ")
    last_word_raw = words[-1] if words else ""
    last_word_display = (last_word_raw[:1].upper() + last_word_raw[1:]) if last_word_raw else last_word_raw
    body_words = [w.upper() for w in words[:-1]]

    lines = []
    current, current_w = [], 0
    for word in body_words:
        w = draw.textlength(word, font=helsa)
        add_w = w + (space_w if current else 0)
        if current_w + add_w > max_width and current:
            lines.append(current)
            current, current_w = [], 0
            add_w = w
        current.append((word, w))
        current_w += add_w
    if current:
        lines.append(current)

    last_word_w = draw.textlength(last_word_display, font=binggo)

    body_line_height = int(FONT_SIZE * LINE_SPACING)
    last_line_height = int(EXMOUTH_SIZE * LINE_SPACING)
    block_height = body_line_height * len(lines) + last_line_height - EXMOUTH_OVERLAP
    start_y = (canvas_h - block_height) // 2

    scrim = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)
    scrim_draw.rectangle(
        [
            (canvas_w - max_width) / 2 - 60,
            start_y - 60,
            (canvas_w + max_width) / 2 + 60,
            start_y + block_height + 60,
        ],
        fill=(0, 0, 0, 70),
    )
    scrim = scrim.filter(ImageFilter.GaussianBlur(40))
    bg = Image.alpha_composite(bg, scrim)
    draw = ImageDraw.Draw(bg)

    helsa_ascent, _ = helsa.getmetrics()
    binggo_ascent, _ = binggo.getmetrics()

    y = start_y
    for line in lines:
        line_w = sum(w for _, w in line) + space_w * (len(line) - 1)
        x = (canvas_w - line_w) / 2
        baseline_y = y + helsa_ascent
        for word, w in line:
            draw.text((x + 2, baseline_y - helsa_ascent + 2), word, font=helsa, fill=(0, 0, 0, 120))
            draw.text((x, baseline_y - helsa_ascent), word, font=helsa, fill=(255, 255, 255, 255))
            x += w + space_w
        y += body_line_height

    x = (canvas_w - last_word_w) / 2
    baseline_y = y - EXMOUTH_OVERLAP + binggo_ascent
    draw.text((x + 2, baseline_y - binggo_ascent + 2), last_word_display, font=binggo, fill=(0, 0, 0, 120))
    draw.text((x, baseline_y - binggo_ascent), last_word_display, font=binggo, fill=(232, 200, 150, 255))

    saudagar = ImageFont.truetype(SAUDAGAR, HANDLE_FONT_SIZE)
    handle_w = draw.textlength(HANDLE_TEXT, font=saudagar)
    handle_x = (canvas_w - handle_w) / 2
    handle_y = canvas_h - HANDLE_BOTTOM_MARGIN
    draw.text((handle_x + 1, handle_y + 1), HANDLE_TEXT, font=saudagar, fill=(0, 0, 0, 110))
    draw.text((handle_x, handle_y), HANDLE_TEXT, font=saudagar, fill=(255, 255, 255, 235))

    return bg.convert("RGB")


def add_watermark_only(bg_img):
    bg_img = fit_to_target(bg_img)
    canvas_w, canvas_h = bg_img.size
    bg = bg_img.convert("RGBA")
    draw = ImageDraw.Draw(bg)
    saudagar = ImageFont.truetype(SAUDAGAR, HANDLE_FONT_SIZE)
    handle_w = draw.textlength(HANDLE_TEXT, font=saudagar)
    handle_x = (canvas_w - handle_w) / 2
    handle_y = canvas_h - HANDLE_BOTTOM_MARGIN
    draw.text((handle_x + 1, handle_y + 1), HANDLE_TEXT, font=saudagar, fill=(0, 0, 0, 110))
    draw.text((handle_x, handle_y), HANDLE_TEXT, font=saudagar, fill=(255, 255, 255, 235))
    return bg.convert("RGB")


def load_image_from_url(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/compose-quote", methods=["POST"])
def compose_quote():
    data = request.get_json(force=True)
    image_url = data.get("image_url")
    quote = data.get("quote", "")
    if not image_url or not quote:
        return jsonify({"error": "image_url and quote are required"}), 400

    bg_img = load_image_from_url(image_url)
    result = compose(bg_img, quote)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return jsonify({"image_base64": b64})


@app.route("/watermark", methods=["POST"])
def watermark():
    data = request.get_json(force=True)
    image_url = data.get("image_url")
    if not image_url:
        return jsonify({"error": "image_url is required"}), 400

    bg_img = load_image_from_url(image_url)
    result = add_watermark_only(bg_img)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return jsonify({"image_base64": b64})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

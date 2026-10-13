"""SPEC-016 limited, human-confirmed diagram recognition."""

import hashlib
import json
import os
import uuid
from pathlib import Path

import cv2
import numpy as np
from flask import Blueprint, current_app, request
from werkzeug.utils import secure_filename

from backend.shared.api import ApiError, audit, body, result, stamp
from backend.shared.auth import course_access, require_user
from backend.shared.db import write

bp = Blueprint("recognition", __name__)
VERSION = "recognition-template-v1-provisional"
SYMBOLS = ("NOT", "AND", "OR", "XOR")
LABELS = ("A", "B", "Y", "D", "Q", "CLK", "RESET", "EN", "PC", "ACC", "IR")
MAX_BYTES = 5 * 1024 * 1024


def gate_mask(symbol):
    canvas = np.zeros((64, 64), np.uint8)
    if symbol == "NOT":
        cv2.polylines(canvas, [np.array([[7, 7], [7, 57], [52, 32]], np.int32)], True, 255, 2)
        cv2.circle(canvas, (57, 32), 4, 255, 2)
    elif symbol == "AND":
        cv2.line(canvas, (9, 7), (31, 7), 255, 2)
        cv2.line(canvas, (9, 57), (31, 57), 255, 2)
        cv2.line(canvas, (9, 7), (9, 57), 255, 2)
        cv2.ellipse(canvas, (31, 32), (25, 25), 0, -90, 90, 255, 2)
    else:
        points = np.array([[8, 7], [25, 7], [42, 12], [55, 32], [42, 52], [25, 57], [8, 57]], np.int32)
        cv2.polylines(canvas, [points], False, 255, 2)
        cv2.ellipse(canvas, (-12, 32), (30, 25), 0, -65, 65, 255, 2)
        if symbol == "XOR":
            cv2.ellipse(canvas, (-18, 32), (30, 25), 0, -65, 65, 255, 2)
    return canvas


def label_mask(label):
    canvas = np.zeros((64, max(64, len(label) * 32)), np.uint8)
    cv2.putText(canvas, label, (2, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 255, 2, cv2.LINE_AA)
    return canvas


TEMPLATES = {**{key: gate_mask(key) for key in SYMBOLS}, **{key: label_mask(key) for key in LABELS}}
TEMPLATE_SHA = hashlib.sha256(b"gray<128;crop;nearest;64x64" + b"".join(
    key.encode() + TEMPLATES[key].tobytes() for key in sorted(TEMPLATES))).hexdigest()


def normalized(mask):
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    cropped = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return cv2.resize(cropped, (64, 64), interpolation=cv2.INTER_NEAREST) > 0


NORMALIZED = {key: normalized(value) for key, value in TEMPLATES.items()}


def confidence_band(score):
    if score < 0.55:
        return None
    return "low" if score < 0.85 else "high"


def match(mask, candidates):
    target = normalized(mask)
    if target is None:
        return None, 0.0
    scores = []
    for key in candidates:
        template = NORMALIZED[key]
        intersection = np.logical_and(target, template).sum()
        union = np.logical_or(target, template).sum()
        scores.append((float(intersection / union) if union else 0.0, key))
    best = min(scores, key=lambda item: (-item[0], item[1]))
    return best[1], best[0]


def dimensions(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return "image/png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 4 < len(data):
            if data[pos] != 0xFF:
                break
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            length = int.from_bytes(data[pos:pos + 2], "big")
            if length < 2 or pos + length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3) and length >= 7:
                return "image/jpeg", int.from_bytes(data[pos + 3:pos + 5], "big"), int.from_bytes(data[pos + 5:pos + 7], "big")
            pos += length
    raise ApiError(415, "UNSUPPORTED_IMAGE", "PNG or JPEG required")


def validate_image(data):
    if len(data) > MAX_BYTES:
        raise ApiError(413, "IMAGE_TOO_LARGE", "Image exceeds 5 MiB")
    media_type, width, height = dimensions(data)
    if not 0 < width <= 4096 or not 0 < height <= 4096:
        raise ApiError(413, "IMAGE_TOO_LARGE", "Image dimensions exceed 4096 pixels")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or image.shape != (height, width):
        raise ApiError(415, "UNSUPPORTED_IMAGE", "Invalid image")
    return media_type, image


def recognize(image):
    foreground = (image < 128).astype(np.uint8) * 255
    if not np.any(foreground):
        return []
    # ponytail: fixed morphology handles printed diagrams; revisit after F01-F05 fixture QA.
    joined = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, np.ones((3, 5), np.uint8))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    gates = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < 9 or height < 9:
            continue
        region = foreground[y:y + height, x:x + width]
        if width >= 40 and height >= 30:
            symbol, score = match(region, SYMBOLS)
            if confidence_band(score):
                template = TEMPLATES[symbol]
                ty, tx = np.where(template > 0)
                template_width, template_height = int(tx.max() - tx.min() + 1), int(ty.max() - ty.min() + 1)
                full_width = round(width * 64 / template_width)
                full_height = round(height * 64 / template_height)
                full_x = round(x - tx.min() * width / template_width)
                full_y = round(y - ty.min() * height / template_height)
                full_x, full_y = max(0, full_x), max(0, full_y)
                box = [full_x, full_y, min(full_width, image.shape[1] - full_x),
                       min(full_height, image.shape[0] - full_y)]
                gates.append({"symbol": symbol, "bbox": box, "tight_bbox": [x, y, width, height],
                              "confidence": round(score, 6), "confidence_band": confidence_band(score),
                              "label": None, "label_status": "unknown"})
    letters = foreground.copy()
    for gate in gates:
        x, y, width, height = gate.pop("tight_bbox")
        letters[y:y + height, x:x + width] = 0
    label_regions = cv2.morphologyEx(letters, cv2.MORPH_CLOSE, np.ones((3, 15), np.uint8))
    label_contours, _ = cv2.findContours(label_regions, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    labels = []
    for contour in label_contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < 9 or not 12 <= height <= 50 or width > 150:
            continue
        label, score = match(letters[y:y + height, x:x + width], LABELS)
        if confidence_band(score):
            labels.append((x + width / 2, y + height / 2, label, score))
    for gate in gates:
        x, y, width, height = gate["bbox"]
        nearby = sorted(labels, key=lambda item: ((item[0] - (x + width / 2)) ** 2 +
                                                   (item[1] - (y + height / 2)) ** 2, item[2]))
        if nearby and nearby[0][3] >= 0.55:
            gate["label"], gate["label_status"] = nearby[0][2], "recognized"
    return sorted(gates, key=lambda item: (item["bbox"][1], item["bbox"][0]))


def storage_root():
    root = Path(current_app.config.get("UPLOAD_ROOT") or os.environ.get("UPLOAD_ROOT", "instance/uploads"))
    root.mkdir(parents=True, exist_ok=True)
    return root


@bp.post("/courses/<int:course_id>/recognitions")
def create_recognition(course_id):
    user = require_user()
    course_access(course_id)
    if set(request.files) != {"image"} or set(request.form):
        raise ApiError(400, "VALIDATION_ERROR", "Exactly one image file required")
    file = request.files["image"]
    data = file.stream.read(MAX_BYTES + 1)
    media_type, image = validate_image(data)
    items = recognize(image)
    status = "recognized" if items else "unrecognized"
    key = uuid.uuid4().hex + (".png" if media_type == "image/png" else ".jpg")
    root = storage_root()
    pending = root / (key + ".tmp")
    destination = root / key
    try:
        with pending.open("xb") as handle:
            handle.write(data)
        os.replace(pending, destination)
        with write() as db:
            course_access(course_id)
            timestamp = stamp()
            stored = db.execute("INSERT INTO file_object(owner_id,storage_key,original_name,media_type,"
                                "size_bytes,sha256,purpose,created_at) VALUES(?,?,?,?,?,?,?,?)",
                                (user["id"], key, secure_filename(file.filename or "diagram"), media_type,
                                 len(data), hashlib.sha256(data).hexdigest(), "recognition", timestamp))
            cursor = db.execute("INSERT INTO recognition(course_id,user_id,image_file_id,status,items_json,"
                                "algorithm_version,template_set_sha256,created_at,updated_at) "
                                "VALUES(?,?,?,?,?,?,?,?,?)",
                                (course_id, user["id"], stored.lastrowid, status,
                                 json.dumps(items, ensure_ascii=False), VERSION, TEMPLATE_SHA, timestamp, timestamp))
            audit("recognition.create", "recognition", cursor.lastrowid, after={"status": status})
            recognition_id = cursor.lastrowid
    except BaseException:
        pending.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    return result({"id": recognition_id, "status": status, "items": items,
                   "requires_confirmation": True, "algorithm_version": VERSION,
                   "template_set_sha256": TEMPLATE_SHA}, 201)


@bp.post("/recognitions/<int:recognition_id>/confirm")
def confirm(recognition_id):
    user = require_user()
    data = body(("items",))
    if not isinstance(data["items"], list) or len(data["items"]) > 100:
        raise ApiError(400, "VALIDATION_ERROR", "items must be an array of up to 100 symbols")
    with write() as db:
        row = db.execute("SELECT r.*,f.storage_key FROM recognition r JOIN file_object f "
                         "ON f.id=r.image_file_id WHERE r.id=? AND r.user_id=?",
                         (recognition_id, user["id"])).fetchone()
        if not row:
            raise ApiError(404, "NOT_FOUND", "Recognition not found")
        course_access(row["course_id"])
        if row["status"] == "confirmed":
            raise ApiError(409, "STATE_CONFLICT", "Recognition already confirmed")
        key = row["storage_key"]
        if Path(key).name != key:
            raise ApiError(500, "INTERNAL_ERROR", "Invalid stored image key")
        _, width, height = dimensions((storage_root() / key).read_bytes())
        originals = json.loads(row["items_json"])
        items = []
        for item in data["items"]:
            if not isinstance(item, dict) or set(item) - {"symbol", "bbox", "label"} or not {"symbol", "bbox"} <= set(item):
                raise ApiError(400, "VALIDATION_ERROR", "Invalid confirmation item")
            symbol, bbox, label = item["symbol"], item["bbox"], item.get("label")
            if symbol not in SYMBOLS or label not in (*LABELS, None):
                raise ApiError(400, "VALIDATION_ERROR", "Unsupported symbol or label")
            if (not isinstance(bbox, list) or len(bbox) != 4 or
                    any(not isinstance(value, int) or isinstance(value, bool) for value in bbox)):
                raise ApiError(400, "VALIDATION_ERROR", "bbox must have four integers")
            x, y, w, h = bbox
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
                raise ApiError(400, "VALIDATION_ERROR", "bbox outside image")
            if label is None and any(original["symbol"] == symbol and original["bbox"] == bbox and
                                     original["label_status"] == "unknown" for original in originals):
                raise ApiError(400, "VALIDATION_ERROR", "Unknown label must be corrected or item removed")
            items.append({"symbol": symbol, "bbox": bbox, "label": label})
        db.execute("UPDATE recognition SET status='confirmed',confirmed_items_json=?,updated_at=? WHERE id=?",
                   (json.dumps(items, ensure_ascii=False), stamp(), recognition_id))
        audit("recognition.confirm", "recognition", recognition_id, after={"item_count": len(items)})
    return result({"id": recognition_id, "status": "confirmed", "confirmed_items": items,
                   "algorithm_version": row["algorithm_version"], "template_set_sha256": row["template_set_sha256"]})

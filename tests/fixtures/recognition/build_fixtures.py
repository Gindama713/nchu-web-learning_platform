"""Regenerate SPEC-016 v2 PNGs and compare the resulting SHA manifest before use."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from backend.apis.recognition import gate_mask

ROOT = Path(__file__).parent


def diagram(symbols=(), labels=()):
    image = np.full((240, 640), 255, np.uint8)
    for symbol, (x, y, width, height) in symbols:
        image[y:y + height, x:x + width] = 255 - cv2.resize(
            gate_mask(symbol), (width, height), interpolation=cv2.INTER_NEAREST)
    for word, x, y in labels:
        cv2.putText(image, word, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 0, 2)
    return image


def images():
    and_box = ("AND", (80, 60, 160, 120))
    standard = diagram((and_box, ("NOT", (350, 60, 180, 120))),
                       (("A", 45, 130), ("Y", 540, 130)))
    damaged = standard.copy()
    damaged[65:100, 190:235] = 255
    resistor = diagram()
    cv2.polylines(resistor, [np.array([[80, 120], [100, 120], [120, 80], [140, 160],
                                       [160, 80], [180, 160], [200, 120], [240, 120]], np.int32)],
                  False, 0, 3)
    return {
        "F01-standard.png": standard,
        "F02-low-quality.png": damaged,
        "F03-unsupported.png": resistor,
        "F04-unknown-label.png": diagram((and_box,), (("XYZ", 250, 130),)),
        "F05-blank.png": diagram(),
    }


if __name__ == "__main__":
    manifest = {}
    for name, image in images().items():
        encoded = cv2.imencode(".png", image)[1].tobytes()
        (ROOT / name).write_bytes(encoded)
        manifest[name] = hashlib.sha256(encoded).hexdigest()
    (ROOT / "sha256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))

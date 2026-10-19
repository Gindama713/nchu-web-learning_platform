"""Fixed F01-F05 bytes, shape, threshold and recognition bounds checks."""

import hashlib
import json
from pathlib import Path
from unittest import TestCase

import cv2
import numpy as np

from backend.apis.recognition import (
    TEMPLATE_SHA,
    VERSION,
    confidence_band,
    gate_mask,
    recognize,
)

FIXTURES = Path(__file__).parent / "fixtures" / "recognition"


def diagram(symbols=(), labels=()):
    image = np.full((240, 640), 255, np.uint8)
    for symbol, box in symbols:
        x, y, width, height = box
        image[y:y + height, x:x + width] = 255 - cv2.resize(
            gate_mask(symbol), (width, height), interpolation=cv2.INTER_NEAREST)
    for word, x, y in labels:
        cv2.putText(image, word, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 0, 2)
    return image


class RecognitionTest(TestCase):
    def test_fixed_v2_png_inputs_and_hashes(self):
        self.assertEqual(VERSION, "recognition-template-v1")
        self.assertEqual(TEMPLATE_SHA, "e5fad902074d5401cb207932a72b539cdf2647f3fffcd29b65b42fe0bd016a49")
        manifest = json.loads((FIXTURES / "sha256.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest), 5)
        outputs = {}
        for name, expected_hash in manifest.items():
            data = (FIXTURES / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected_hash)
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
            self.assertEqual(image.shape, (240, 640))
            outputs[name] = recognize(image)
        standard = outputs["F01-standard.png"]
        self.assertEqual([(item["symbol"], item["label"], item["confidence_band"])
                          for item in standard], [("AND", "A", "high"), ("NOT", "Y", "high")])
        for item, target in zip(standard, ((80, 60, 160, 120), (350, 60, 180, 120)), strict=True):
            self.assertTrue(all(abs(actual - expected) <= 8 for actual, expected
                                in zip(item["bbox"], target, strict=True)))
        for item, target in zip(standard, ((45, 106, 21, 26), (540, 106, 21, 26)), strict=True):
            self.assertTrue(all(abs(actual - expected) <= 4 for actual, expected
                                in zip(item["label_bbox"], target, strict=True)))
        damaged = outputs["F02-low-quality.png"]
        self.assertEqual([(item["symbol"], item["label"], item["confidence_band"]) for item in damaged],
                         [("AND", "A", "low"), ("NOT", "Y", "high")])
        self.assertTrue(all(abs(actual - expected) <= 12 for actual, expected
                            in zip(damaged[0]["bbox"], (80, 60, 160, 120), strict=True)))
        self.assertEqual(outputs["F03-unsupported.png"], [])
        unknown = outputs["F04-unknown-label.png"]
        self.assertEqual([(item["symbol"], item["confidence_band"], item["label_status"])
                          for item in unknown], [("AND", "high", "unknown")])
        self.assertIsNone(unknown[0]["label_bbox"])
        self.assertEqual(outputs["F05-blank.png"], [])

    def test_threshold_boundaries(self):
        self.assertIsNone(confidence_band(0.549999))
        self.assertEqual(confidence_band(0.55), "low")
        self.assertEqual(confidence_band(0.849999), "low")
        self.assertEqual(confidence_band(0.85), "high")

    def test_standard_symbols_labels_and_boxes(self):
        image = diagram((("AND", (80, 60, 160, 120)), ("NOT", (350, 60, 180, 120))),
                        (("A", 45, 130), ("Y", 540, 130)))
        items = recognize(image)
        self.assertEqual([(item["symbol"], item["label"], item["confidence_band"]) for item in items],
                         [("AND", "A", "high"), ("NOT", "Y", "high")])
        for item, target in zip(items, ((80, 60, 160, 120), (350, 60, 180, 120)), strict=True):
            self.assertTrue(all(abs(a - b) <= 8 for a, b in zip(item["bbox"], target, strict=True)))

    def test_or_and_xor_contours_are_joined_before_matching(self):
        image = diagram((("OR", (80, 60, 160, 120)), ("XOR", (350, 60, 180, 120))))
        items = recognize(image)
        self.assertEqual([(item["symbol"], item["confidence_band"]) for item in items],
                         [("OR", "high"), ("XOR", "high")])

    def test_damage_unknown_label_resistor_and_blank(self):
        damaged = diagram((("AND", (80, 60, 160, 120)),))
        damaged[65:100, 190:235] = 255
        self.assertEqual(recognize(damaged)[0]["confidence_band"], "low")
        unknown = diagram((("AND", (80, 60, 160, 120)),), (("XYZ", 250, 130),))
        self.assertEqual(recognize(unknown)[0]["label_status"], "unknown")
        resistor = diagram()
        cv2.polylines(resistor, [np.array([[80, 120], [100, 120], [120, 80], [140, 160],
                                           [160, 80], [180, 160], [200, 120], [240, 120]], np.int32)],
                      False, 0, 3)
        self.assertEqual(recognize(resistor), [])
        self.assertEqual(recognize(diagram()), [])

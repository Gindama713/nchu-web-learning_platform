"""Synthetic shape checks; official F01-F05 PNGs are still required for TV-03."""

from unittest import TestCase

import cv2
import numpy as np

from backend.apis.recognition import confidence_band, gate_mask, recognize


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

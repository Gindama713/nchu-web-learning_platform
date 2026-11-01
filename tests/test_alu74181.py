"""SPEC-019: the 74181 experiment must agree with plain 4-bit arithmetic."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from backend.apis.alu import MASK, evaluate
from backend.app import create_app
from backend.shared.db import migrate


class Alu74181Test(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_every_combination_matches_arithmetic(self):
        for op in ("add", "sub"):
            for a in range(MASK + 1):
                for b in range(MASK + 1):
                    row = evaluate(a, b, op)
                    expected = a + b if op == "add" else a - b
                    self.assertEqual(row["decimal_result"], expected)
                    self.assertEqual(row["f"], expected & MASK, (op, a, b))
                    self.assertEqual(row["zero"], 1 if expected & MASK == 0 else 0)
                    self.assertEqual(row["equal"], 1 if a == b else 0)

    def test_carry_and_borrow_use_active_low_cn4(self):
        overflow = evaluate(15, 1, "add")
        self.assertEqual((overflow["carry"], overflow["cn4"]), (1, 0))
        quiet = evaluate(3, 5, "add")
        self.assertEqual((quiet["carry"], quiet["cn4"]), (0, 1))
        # 减法走 A + B̄ + 1：A >= B 时最高位有进位，Cn+4（低有效）输出 0；
        # A < B 时没有进位，Cn+4 变高，即借位。
        underflow = evaluate(1, 15, "sub")
        self.assertEqual((underflow["borrow"], underflow["cn4"]), (1, 1))
        fine = evaluate(9, 4, "sub")
        self.assertEqual((fine["borrow"], fine["cn4"]), (0, 0))

    def test_control_bits_follow_the_two_datasheet_rows(self):
        add = evaluate(6, 3, "add")
        self.assertEqual((add["s3s2s1s0"], add["m"], add["cn_bar"]), ("1001", 0, 1))
        self.assertEqual(add["operand_b"], 3)
        sub = evaluate(6, 3, "sub")
        self.assertEqual((sub["s3s2s1s0"], sub["m"], sub["cn_bar"]), ("0110", 0, 0))
        self.assertEqual(sub["operand_b"], (~3) & MASK)
        self.assertEqual(sub["carry_in"], 1)

    def test_compute_rejects_bad_operands(self):
        for query in ("a=16&b=0&op=add", "a=0&b=-1&op=add",
                      "a=0&b=0&op=mul", "a=x&b=0&op=add", "b=0&op=add"):
            response = self.client.get(f"/api/v1/alu74181/compute?{query}")
            self.assertEqual(response.status_code, 400, query)
            self.assertEqual(response.json["error"]["code"], "VALIDATION_ERROR")

    def test_compute_and_table_answer_without_login(self):
        single = self.client.get("/api/v1/alu74181/compute?a=9&b=4&op=sub")
        self.assertEqual(single.status_code, 200)
        self.assertEqual(single.json["data"]["f"], 5)
        self.assertEqual(single.json["data"]["f_bits"], "0101")

        table = self.client.get("/api/v1/alu74181/table")
        self.assertEqual(table.status_code, 200)
        self.assertEqual(table.json["data"]["count"], 2 * 16 * 16)
        rows = table.json["data"]["rows"]
        self.assertEqual(len(rows), table.json["data"]["count"])
        self.assertEqual({row["op"] for row in rows}, {"add", "sub"})

        spec = self.client.get("/api/v1/alu74181/spec")
        self.assertEqual(spec.status_code, 200)
        self.assertEqual(spec.json["data"]["operations"]["sub"]["s3s2s1s0"], "0110")

import unittest

from core.analysis import analyze_inventory_text, parse_inventory


SAMPLE_EXPORT = """Location\tName\tID\tCount\tSlots
Inventory\tBronze Sword +2\t1001\t1\t0
Bank\tBronze Sword +0\t1001\t1\t0
Hoard\tEmpty\t0\t0\t0
KeyRing\tType\tName\tID
Equipment\tBronze Sword +1\t1001
Augmentation\tSome Gem (Exaltation)\t1001
"""


class TestCoreAnalysis(unittest.TestCase):
    def test_parse_inventory_ignores_empty_and_non_equipment_keyring(self):
        records = parse_inventory(SAMPLE_EXPORT)
        self.assertEqual(len(records), 3)
        self.assertTrue(any(r["source"] == "Equipment KeyRing" for r in records))

    def test_analyze_inventory_text_returns_confirmed_group(self):
        payload = analyze_inventory_text(SAMPLE_EXPORT, filename="sample.txt")
        self.assertEqual(payload["meta"]["confirmed_count"], 1)
        self.assertEqual(payload["meta"]["possible_count"], 0)
        self.assertEqual(payload["confirmed"][0]["item_id"], 1001)


if __name__ == "__main__":
    unittest.main()

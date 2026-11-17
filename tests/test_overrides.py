import json
import tempfile
import unittest
from pathlib import Path

from nbl import build


class FibaOverridesTest(unittest.TestCase):
    def test_override_sets_fiba_id_and_links(self):
        with tempfile.TemporaryDirectory() as d:
            sdir = Path(d)
            (sdir / "fiba_overrides.json").write_text(json.dumps({"544612": 2943577}))
            fixtures = [
                {"nblId": 544612, "fibaId": None, "datetime": "2026-11-15T17:00:00+01:00",
                 "home": "Sršni Photomate Písek", "away": "SLUNETA Ústí nad Labem", "round": "12. kolo"},
                {"nblId": 544614, "fibaId": None, "datetime": "2026-11-15T17:00:00+01:00",
                 "home": "SK Slavia Praha ERA NBK", "away": "USK Praha", "round": "12. kolo"},
            ]
            self.assertEqual(build.apply_fiba_overrides(sdir, fixtures), 1)
            self.assertEqual(fixtures[0]["fibaId"], 2943577)
            self.assertIn("2943577", fixtures[0]["links"]["fibaData"])
            self.assertIsNone(fixtures[1]["fibaId"])
            # podruhé už nic nemění
            self.assertEqual(build.apply_fiba_overrides(sdir, fixtures), 0)

    def test_missing_file_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(build.apply_fiba_overrides(Path(d), [{"nblId": 1}]), 0)


if __name__ == "__main__":
    unittest.main()

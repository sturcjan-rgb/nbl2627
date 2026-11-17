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



class ProbeTest(unittest.TestCase):
    def test_finds_neighbour_ids_by_teams(self):
        from datetime import datetime, timezone
        from nbl import schedule
        fx = [
            {"nblId": 1, "fibaId": 2943577, "datetime": "2026-11-15T17:00:00+01:00",
             "home": "Sršni Photomate Písek", "away": "SLUNETA Ústí nad Labem", "round": "12. kolo"},
            {"nblId": 2, "fibaId": None, "datetime": "2026-11-15T17:00:00+01:00",
             "home": "SK Slavia Praha ERA NBK", "away": "USK Praha", "round": "12. kolo"},
            {"nblId": 3, "fibaId": None, "datetime": "2026-11-14T18:00:00+01:00",
             "home": "BK ARMEX ENERGY Děčín", "away": "BK Loko BaliMania Plzeň", "round": "12. kolo"},
            {"nblId": 4, "fibaId": None, "datetime": "2026-12-14T18:00:00+01:00",  # budoucí: nehledat
             "home": "USK Praha", "away": "BK Opava", "round": "15. kolo"},
        ]
        for f in fx:
            schedule.finalize(f)
        fake = {
            2943575: ("BK ARMEX ENERGY Děčín", "BK Loko BaliMania Plzeň"),
            2943578: ("SK Slavia Praha ERA NBK", "USK Praha"),
            2943579: ("USK Praha", "BK Opava"),
        }
        calls = []

        def fetch(fid):
            calls.append(fid)
            if fid not in fake:
                return None
            h, a = fake[fid]
            return {"tm": {"1": {"name": h}, "2": {"name": a}}}

        now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
        self.assertEqual(build.probe_fiba_ids(fx, fetch, now), 2)
        self.assertEqual(fx[1]["fibaId"], 2943578)
        self.assertEqual(fx[2]["fibaId"], 2943575)
        self.assertIsNone(fx[3]["fibaId"])
        self.assertLess(len(calls), 40)
        self.assertEqual(build.probe_fiba_ids(fx, fetch, now), 0)


if __name__ == "__main__":
    unittest.main()

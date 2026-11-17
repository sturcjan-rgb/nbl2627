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



class CandidatesTest(unittest.TestCase):
    def test_assigns_by_teams(self):
        from datetime import datetime, timezone
        from nbl import schedule
        with tempfile.TemporaryDirectory() as d:
            sdir = Path(d)
            (sdir / "fiba_candidates.json").write_text("[11, 12, 13]")
            fx = [
                {"nblId": 2, "fibaId": None, "datetime": "2026-11-15T17:00:00+01:00",
                 "home": "SK Slavia Praha ERA NBK", "away": "USK Praha"},
                {"nblId": 5, "fibaId": None, "datetime": "2027-02-15T17:00:00+01:00",  # odveta, budoucí
                 "home": "USK Praha", "away": "SK Slavia Praha ERA NBK"},
            ]
            for f in fx:
                schedule.finalize(f)
            raws = {11: ("SK Slavia Praha ERA NBK", "USK Praha"), 12: ("Iowa", "Illinois")}
            fetch = lambda fid: {"tm": {"1": {"name": raws[fid][0]}, "2": {"name": raws[fid][1]}}} if fid in raws else None
            now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
            self.assertEqual(build.assign_fiba_candidates(sdir, fx, fetch, now), 1)
            self.assertEqual(fx[0]["fibaId"], 11)
            self.assertIsNone(fx[1]["fibaId"])
            self.assertEqual(json.loads((sdir / "fiba_overrides.json").read_text()), {"2": 11})
            self.assertEqual(json.loads((sdir / "fiba_candidates.json").read_text()), [12, 13])

    def test_skips_reserve_team(self):
        from datetime import datetime, timezone
        from nbl import schedule
        with tempfile.TemporaryDirectory() as d:
            sdir = Path(d)
            (sdir / "fiba_candidates.json").write_text("[21]")
            fx = [{"nblId": 3, "fibaId": None, "datetime": "2026-11-14T17:00:00+01:00",
                   "home": "NH Ostrava", "away": "BK Opava"}]
            schedule.finalize(fx[0])
            fetch = lambda fid: {"tm": {"1": {"name": "MS Academy Ostrava"}, "2": {"name": 'BK Opava "B"'}}}
            now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
            self.assertEqual(build.assign_fiba_candidates(sdir, fx, fetch, now), 0)
            self.assertIsNone(fx[0]["fibaId"])


class MirrorTest(unittest.TestCase):
    def test_falls_back_to_mirror_after_403(self):
        from nbl import schedule
        f = schedule.Fetcher.__new__(schedule.Fetcher)
        f.blocked, calls = set(), []

        def get(url, params=None):
            calls.append(url)
            if url.startswith(schedule.BASE):
                f.blocked.add(schedule.BASE)
                return None
            return "<html/>"
        f.get = get
        self.assertEqual(f.site("/zapas/1"), ("<html/>", schedule.MIRROR))
        self.assertEqual(f.site("/zapas/2"), ("<html/>", schedule.MIRROR))
        self.assertEqual(calls, [schedule.BASE + "/zapas/1", schedule.MIRROR + "/zapas/1", schedule.MIRROR + "/zapas/2"])


if __name__ == "__main__":
    unittest.main()

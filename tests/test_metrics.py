"""Testy rozboru zápasu nad skutečnými FIBA daty (tests/fixtures/*.json.gz, bez sítě)."""
import copy
import gzip
import json
import unittest
from pathlib import Path

from nbl.metrics import (abs_period, advanced, analyze_game, blank_box, is_finished, possessions,
                         public, zone_of)

FIX = Path(__file__).parent / "fixtures"


def load(fid):
    with gzip.open(FIX / f"{fid}.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)


class MatchAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = load(2892252)          # Písek – Pardubice 82:92, 2026/27
        cls.g = analyze_game(cls.raw)

    def test_final_and_score(self):
        self.assertTrue(is_finished(self.raw))
        self.assertEqual(self.g["status"], "final")
        self.assertEqual((self.g["home"]["score"], self.g["away"]["score"]), (82, 92))
        self.assertEqual(self.g["winner"], "away")

    def test_quarters_sum_to_score(self):
        for side in ("home", "away"):
            self.assertEqual(sum(q[side] for q in self.g["quarters"]), self.g[side]["score"])

    def test_team_slugs(self):
        self.assertEqual(self.g["home"]["slug"], "pisek")
        self.assertEqual(self.g["away"]["slug"], "pardubice")

    def test_box_matches_official_totals(self):
        T = self.raw["tm"]["1"]
        b = self.g["home"]["box"]
        self.assertEqual(b["fga"], T["tot_sFieldGoalsAttempted"])
        self.assertEqual(b["oreb"], T["tot_sReboundsOffensive"])
        self.assertEqual(b["to"], T["tot_sTurnovers"])

    def test_possessions_and_ratings(self):
        h, a = self.g["home"], self.g["away"]
        self.assertAlmostEqual(h["adv"]["poss"], possessions(h["box"]), places=1)
        self.assertAlmostEqual(h["adv"]["ortg"], a["adv"]["drtg"], places=1)
        self.assertAlmostEqual(h["adv"]["net"], -a["adv"]["net"], places=1)
        self.assertEqual(self.g["minutes"], 40)

    def test_minutes_on_court_sum_to_200(self):
        for side in ("home", "away"):
            self.assertAlmostEqual(sum(p["on"]["min"] for p in self.g[side]["players"]), 200, delta=1)

    def test_on_court_plus_minus_matches_official(self):
        for side in ("home", "away"):
            for p in self.g[side]["players"]:
                self.assertEqual(p["on"]["pf"] - p["on"]["pa"], p["pm"], p["name"])

    def test_lineups_cover_whole_game(self):
        h = self.g["home"]
        fives_min = sum(v["secs"] for _n, v in h["_agg"]["fives"]) / 60
        self.assertAlmostEqual(fives_min, 40, delta=0.5)
        self.assertTrue(h["lineups"]["fives"])
        self.assertTrue(all(len(r["players"]) == 5 for r in h["lineups"]["fives"]))

    def test_attack_bands_sum_to_points(self):
        for side in ("home", "away"):
            at = self.g[side]["attack"]
            self.assertEqual(sum(at["team"]) + at["unassigned"], self.g[side]["score"])

    def test_zones_cover_all_shots(self):
        for side in ("home", "away"):
            self.assertEqual(sum(z["a"] for z in self.g[side]["zones"].values()), self.g[side]["box"]["fga"])

    def test_public_strips_internal(self):
        p = public(self.g)
        self.assertNotIn("_agg", p["home"])
        json.dumps(p)  # serializovatelné

    def test_flow(self):
        f = self.g["flow"]
        self.assertGreaterEqual(f["leadChanges"], 1)
        self.assertTrue(all(r["pts"] >= 8 for r in f["runs"]))
        self.assertEqual(f["timeline"][-1][1], 82 - 92)


class LiveAnalysis(unittest.TestCase):
    def test_partial_game_has_live_block(self):
        raw = copy.deepcopy(load(2892252))
        raw["pbp"] = [e for e in raw["pbp"] if e["period"] <= 2]
        raw["period"], raw["clock"] = 3, "10:00"
        g = analyze_game(raw)
        self.assertEqual(g["status"], "live")
        live = g["live"]
        self.assertEqual(len(live["onCourt"]["home"]), 5)
        self.assertEqual(len(live["onCourt"]["away"]), 5)
        self.assertIn("home", live["teamFoulsPeriod"])
        self.assertAlmostEqual(g["minutes"], 20, delta=0.1)

    def test_empty_pbp(self):
        raw = copy.deepcopy(load(2892252))
        raw["pbp"] = []
        g = analyze_game(raw)
        self.assertEqual(g["status"], "scheduled")


class Overtime(unittest.TestCase):
    def test_abs_period(self):
        self.assertEqual(abs_period(1, "OVERTIME"), 5)
        self.assertEqual(abs_period(2, "OVERTIME"), 6)
        self.assertEqual(abs_period(4, "REGULAR"), 4)

    def test_overtime_game(self):
        """Syntetické prodloužení: posunout poslední akce do OT (period=1, periodType=OVERTIME)."""
        raw = copy.deepcopy(load(2705709))
        for e in raw["pbp"]:
            if e["period"] == 4 and e["actionType"] == "game":
                e["period"], e["periodType"], e["gt"] = 1, "OVERTIME", "00:00"
        raw["pbp"].append({"actionType": "period", "subType": "start", "period": 1, "periodType": "OVERTIME",
                           "gt": "05:00", "tno": 0, "pno": 0, "actionNumber": 99999, "success": 1})
        g = analyze_game(raw)
        self.assertEqual(g["minutes"], 45)


class Formulas(unittest.TestCase):
    def test_four_factors(self):
        b = blank_box(); o = blank_box()
        b.update(pts=80, fgm=30, fga=70, tpm=8, tpa=24, ftm=12, fta=16, oreb=10, dreb=25, to=12, ast=18, twopa=46, twopm=22)
        o.update(pts=75, fgm=28, fga=68, tpm=7, tpa=20, ftm=12, fta=15, oreb=9, dreb=30, to=14, twopa=48, twopm=21)
        a = advanced(b, o, 40)
        self.assertAlmostEqual(a["efg"], 100 * (30 + 4) / 70, places=1)
        self.assertAlmostEqual(a["poss"], 70 - 10 + 12 + 0.44 * 16, places=1)
        self.assertAlmostEqual(a["orb"], 100 * 10 / (10 + 30), places=1)
        self.assertAlmostEqual(a["ftr"], 100 * 12 / 70, places=1)

    def test_zones(self):
        self.assertEqual(zone_of(5.2, 50, False), "paint")
        self.assertEqual(zone_of(30, 50, False), "mid")
        self.assertEqual(zone_of(5, 95, True), "corner3")
        self.assertEqual(zone_of(30, 50, True), "above3")


if __name__ == "__main__":
    unittest.main()

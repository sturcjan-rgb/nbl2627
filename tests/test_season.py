"""Sezónní agregace a tabulka (bez sítě)."""
import gzip
import json
import unittest
from pathlib import Path

from nbl.metrics import analyze_game
from nbl.season import leaders, players, standings, team_seasons

FIX = Path(__file__).parent / "fixtures"


def fake(home, away, hs, as_, date):
    return {"home": {"slug": home, "name": home, "label": home, "score": hs},
            "away": {"slug": away, "name": away, "label": away, "score": as_},
            "fixture": {"datetime": date}, "period": 4}


class Standings(unittest.TestCase):
    def test_record_fields(self):
        games = [fake("a", "b", 80, 70, "2026-10-01"), fake("c", "a", 60, 100, "2026-10-02"),
                 fake("b", "a", 90, 85, "2026-10-08")]
        a = next(r for r in standings(games) if r["slug"] == "a")
        self.assertEqual((a["w"], a["l"], a["home"], a["away"]), (2, 1, "1-0", "1-1"))
        self.assertEqual((a["streak"], a["last5"], a["diff"]), ("L1", "WWL", 10 + 40 - 5))

    def test_mini_league_order(self):
        # a, b, c všichni 1-1; vzájemný rozdíl skóre: a +10, c 0, b −10
        games = [fake("a", "b", 90, 70, "2026-10-01"), fake("b", "c", 80, 70, "2026-10-02"),
                 fake("c", "a", 80, 70, "2026-10-03")]
        self.assertEqual([r["slug"] for r in standings(games)], ["a", "c", "b"])

    def test_head_to_head_beats_point_diff(self):
        # a i b 2-1; b má lepší celkové skóre, ale a vyhrál vzájemný zápas
        games = [fake("a", "b", 71, 70, "2026-10-01"), fake("b", "c", 120, 60, "2026-10-02"),
                 fake("c", "a", 80, 70, "2026-10-03"), fake("a", "d", 80, 79, "2026-10-04"),
                 fake("d", "b", 70, 80, "2026-10-05")]
        order = [r["slug"] for r in standings(games)]
        self.assertLess(order.index("a"), order.index("b"))


class SeasonFromRealGames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.games = []
        for fid in (2705709, 2892252):
            with gzip.open(FIX / f"{fid}.json.gz", "rt", encoding="utf-8") as f:
                g = analyze_game(json.load(f), {"fibaId": fid, "datetime": f"2026-0{fid % 3 + 1}-01T18:00:00+01:00"})
                g["fibaId"] = fid
                cls.games.append(g)

    def test_team_season(self):
        teams = team_seasons(self.games)
        p = teams["pisek"]
        self.assertEqual(p["games"], 2)
        self.assertEqual(p["totals"]["pts"], 84 + 82)
        self.assertEqual(p["oppTotals"]["pts"], 77 + 92)
        self.assertIn("ortg", p["ranks"])
        self.assertEqual(p["ranks"]["of"], 3)
        self.assertEqual(len(p["log"]), 2)

    def test_players_and_leaders(self):
        pl = players(self.games)
        self.assertTrue(pl)
        ids = [p["id"] for p in pl]
        self.assertEqual(len(ids), len(set(ids)))
        two = [p for p in pl if p["gp"] == 2]
        self.assertTrue(two)  # hráči Písku hráli oba zápasy
        L = leaders(pl, {"pisek": 2, "ostrava": 1, "pardubice": 1})
        self.assertTrue(L["pts"]["rows"])


if __name__ == "__main__":
    unittest.main()

"""Parsování rozpisu z nbl.basketball na syntetickém HTML (struktura podle srsni-data/srsni-truth)."""
import unittest

try:
    import bs4  # noqa: F401
    HAVE_BS4 = True
except ImportError:
    HAVE_BS4 = False

from nbl import schedule

TEAM_PAGE = """<html><body><main>
<h2>Zápasy 2026/27</h2>
<table>
<tr><th>Kolo</th><th>Datum</th><th>Domácí / hosté</th><th>Skóre</th><th>Čtvrtiny</th><th>Fáze</th></tr>
<tr><td>1. kolo</td><td>20. 9. 2026 18:00</td><td>SLUNETA Ústí nad Labem Sršni Photomate Písek</td>
<td><a href="/zapas/544546">78 : 80</a></td><td>20:18 40:41 61:60</td><td>Základní část</td>
<td><a href="https://www.fibalivestats.com/webcast/CBFFE/2890467/">LiveStats</a></td></tr>
<tr><td>5. kolo</td><td>3. 10. 2026 17:30</td><td>USK Praha Sršni Photomate Písek</td>
<td><a href="/zapas/544570#tab-pane-two">náhled</a></td><td></td><td>Základní část</td></tr>
</table>
<table><tr><td><a href="/tym/usk-praha">USK Praha</a></td></tr></table>
</main></body></html>"""

ZAPASY = """<html><body><main><form><select name="c"><option value="0">Všechny</option>
<option value="421">Sršni Photomate Písek</option><option value="77">USK Praha</option></select></form>
<table><tbody>
<tr><td>3</td><td>x</td><td data-sort="2026-09-27-17-00">27. 9. 2026 17:00</td>
<td><div><div>BK Opava</div><div>NH Ostrava</div></div></td>
<td><a href="/zapas/544559#tab-pane-one">88:81</a></td></tr>
</tbody></table></main></body></html>"""


@unittest.skipUnless(HAVE_BS4, "beautifulsoup4 není nainstalované")
class Parse(unittest.TestCase):
    def test_team_page(self):
        rows = {r["nblId"]: r for r in schedule.parse_rows(TEAM_PAGE, schedule.KNOWN_TEAMS)}
        a = rows[544546]
        self.assertEqual((a["home"], a["away"]), ("SLUNETA Ústí nad Labem", "Sršni Photomate Písek"))
        self.assertEqual(a["score"], {"home": 78, "away": 80})
        self.assertEqual(a["fibaId"], 2890467)
        self.assertEqual(a["datetime"], "2026-09-20T18:00:00+02:00")
        self.assertEqual([q["home"] for q in a["quarters"]], [20, 20, 21, 17])
        b = rows[544570]
        self.assertIsNone(b["score"])
        self.assertEqual(b["home"], "USK Praha")
        self.assertEqual(schedule.season_heading(TEAM_PAGE), "2026/27")
        self.assertIn("usk-praha", schedule.team_links(TEAM_PAGE))

    def test_zapasy_page(self):
        rows = schedule.parse_rows(ZAPASY, schedule.KNOWN_TEAMS)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["home"], r["away"]), ("BK Opava", "NH Ostrava"))
        self.assertEqual(r["score"], {"home": 88, "away": 81})
        self.assertEqual(r["datetime"], "2026-09-27T17:00:00+02:00")
        self.assertEqual(schedule.team_select_options(ZAPASY), {"421": "Sršni Photomate Písek", "77": "USK Praha"})

    def test_finalize(self):
        f = schedule.finalize({"nblId": 1, "fibaId": 5, "round": "3. kolo", "datetime": "2026-09-27T17:00:00+02:00",
                               "home": "BK Opava", "away": "NH Ostrava", "score": {"home": 1, "away": 0}})
        self.assertEqual((f["homeSlug"], f["awaySlug"], f["roundNum"], f["status"]), ("opava", "ostrava", 3, "final"))
        self.assertTrue(f["links"]["fibaData"].endswith("/5/data.json"))


class Pure(unittest.TestCase):
    def test_merge_keeps_known_values(self):
        m = schedule.merge_fixture({"nblId": 1, "fibaId": 9, "score": {"home": 1, "away": 2}}, {"nblId": 1, "fibaId": None, "score": None})
        self.assertEqual(m["fibaId"], 9)
        self.assertEqual(m["score"], {"home": 1, "away": 2})

    def test_quarters_from(self):
        self.assertEqual(schedule.quarters_from([20, 18, 40, 41, 61, 60], 78, 80),
                         [{"home": 20, "away": 18}, {"home": 20, "away": 23}, {"home": 21, "away": 19}, {"home": 17, "away": 20}])

    def test_current_season(self):
        from datetime import datetime, timezone
        self.assertEqual(schedule.current_season(datetime(2026, 10, 1, tzinfo=timezone.utc)), "2026/27")
        self.assertEqual(schedule.current_season(datetime(2027, 3, 1, tzinfo=timezone.utc)), "2026/27")


if __name__ == "__main__":
    unittest.main()

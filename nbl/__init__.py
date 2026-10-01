"""nbl2627 — statistiky celé Maxa NBL (sezóna 2026/27) z FIBA LiveStats.

Moduly:
  teams     – kanonické identity týmů (slug, krátké jméno) napříč NBL webem a FIBA
  schedule  – rozpis celé ligy z nbl.basketball (+ dohledání FIBA ID)
  fiba      – stažení a archiv data.json z FIBA LiveStats
  metrics   – rozbor jednoho zápasu (box score, four factors, ratingy, pětky, …)
  season    – sezónní agregace: tabulka, týmy, hráči, ligové žebříčky
  build     – zapíše všechny JSONy do data/<sezóna>/
  live      – živé statistiky právě hraných zápasů
"""

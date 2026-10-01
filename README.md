# nbl2627 — statistiky celé Maxa NBL 2026/27

Ligová nadstavba nad tím, co pro Sršně dělají [srsni-data](https://github.com/sturcjan-rgb/srsni-data)
(live rozbor, highlights) a [srsni-truth](https://github.com/sturcjan-rgb/srsni-truth) (SQLite, sezónní
agregace). Tady se totéž počítá **pro všechny týmy a všechny zápasy**: JSON soubory pro každý tým,
každý zápas, hráče, tabulku a žebříčky, plus **živé statistiky** právě hraných zápasů.

Čistý Python (3.11+), jediné závislosti jsou `requests`, `beautifulsoup4`, `lxml` (jen pro scraper
rozpisu; samotné metriky jsou bez závislostí).

## Web

`index.html` + `assets/` je statický frontend (bez buildu) nad JSONy v `data/` a živou větví `live`:

- **Přehled** — tabulka, dnešní živé zápasy (obnovuje se samo), nejbližší zápasy, poslední výsledky, lídři ligy
- **Zápasy** — všechna kola, filtr podle týmu a stavu
- **Týmy** — srovnání všech týmů (útok/obrana, four factors, střelba, průměry, clutch a čas útoku) s pořadím v lize a ligovým průměrem, řazení kliknutím na sloupec
- **Hráči** — všichni hráči ligy (na zápas, pokročilé, součty, na 40 min), hledání a filtry
- **Žebříčky**
- **Tým** — ratingy s pořadím, four factors vs. liga, čtvrtiny, hráči, zóny, čas útoku, pětky/trojice/dvojice, asistence, zápasy
- **Zápas** — skóre, průběh (graf rozdílu), four factors, body podle typu, série, clutch, box score s TS/USG/EFF/on-off, střelecká mapa, čas útoku, sestavy, asistence; u běžícího zápasu se každých 5 s obnovuje z větve `live` (kdo je na hřišti, fauly, série)

Zveřejnění: **Settings → Pages → Build and deployment → Deploy from a branch → výchozí větev, složka `/ (root)`**.
Web pak běží na `https://sturcjan-rgb.github.io/nbl2627/` a data čte relativně. Lokálně:
`python3 -m http.server` a otevřít `http://localhost:8000/`.

## Jak to běží

| Workflow | Kdy | Co dělá |
|---|---|---|
| `league.yml` | každé 2 h + večer po zápasech, ručně | rozpis celé ligy → FIBA data dohraných zápasů → přepočet všech JSONů → commit do `data/` |
| `live.yml` | každých 15 min odpoledne/večer (+ spouští ho `league.yml`, když se blíží zápas) | každých ~10 s stáhne všechny zápasy v živém okně, spočítá rozbor, force-pushne větev `live`; dohraný zápas archivuje a přepočítá sezónu |

Lokálně:

```bash
pip install -r requirements.txt
python -m nbl.build                     # rozpis + FIBA + přepočet (sezóna podle data)
python -m nbl.build --offline           # jen přepočet z archivu data/<sezóna>/raw (bez sítě)
python -m nbl.build --debug             # vypíše ukázky HTML rozpisu (ladění scraperu)
python -m nbl.live --out live-out       # živé statistiky do adresáře live-out/
python -m unittest discover -s tests -t .
```

## Data

Vše v `data/2026-27/` (čti přes `https://raw.githubusercontent.com/sturcjan-rgb/nbl2627/<větev>/data/2026-27/...`):

| Soubor | Obsah |
|---|---|
| `index.json` | manifest: počty, seznam týmů (slug, jméno, logo), seznam zápasů se skóre, šablony cest |
| `schedule.json` | rozpis celé ligy — odehrané i budoucí zápasy, `nblId`, `fibaId`, kolo, datum, skóre, odkazy (NBL, LiveStats, FIBA JSON, `matches/<fibaId>.json`) |
| `standings.json` | tabulka: V/P, %, skóre, doma/venku, těsné zápasy (≤ 5 b.), prodloužení, série, forma |
| `league.json` | ligové průměry + srovnávací tabulka týmů (ratingy, four factors, clutch, čas útoku, **pořadí v lize u každé metriky**) |
| `leaders.json` | žebříčky hráčů (body, doskoky, asistence, EFF, Game Score, TS%, eFG%, USG%, +/−, on/off, double-double…) |
| `players.json` | všichni hráči ligy — součty, průměry, na 40 min, pokročilé metriky |
| `teams/<slug>.json` | sezóna týmu: box + soupeři, ratingy, four factors (útok i obrana), zóny střelby, čas útoku, clutch, čtvrtiny, průběh, pětky/trojice/dvojice, asistenční dvojice, hráči s deníkem zápasů, rozpis týmu |
| `matches/<fibaId>.json` | rozbor jednoho zápasu (viz níže) |
| `raw/<fibaId>.json.gz` | archiv surového FIBA `data.json` — zdroj pravdy, všechno se z něj dá kdykoliv přepočítat (FIBA starší zápasy časem maže) |

Slugy týmů: `pisek`, `hradec`, `pardubice`, `ostrava`, `opava`, `olomoucko`, `plzen`, `brno`, `decin`,
`slavia`, `usk`, `usti`, `nymburk` (podle klíčového slova ve jméně, takže změna sponzorského názvu nevadí —
viz `nbl/teams.py`).

### Živá data (větev `live`)

| Soubor | Obsah |
|---|---|
| `index.json` | dnešní zápasy ligy: stav, skóre, perioda, čas, kdo vede, aktuální série |
| `<fibaId>.json` | plný živý rozbor zápasu (stejná struktura jako `matches/`, navíc blok `live`) |
| `index/<epoch/5>.json`, `<fibaId>/<epoch/5>.json` | totéž po 5s oknech — `raw.githubusercontent.com` drží soubory 5 min v cache a parametry v URL ignoruje, nové jméno souboru = vždy čerstvá data (stejný trik jako `live-relay` v srsni-data). Klient zkusí okna `now/5 − 2 … − 5`, fallback `<fibaId>.json`. |

Blok `live`: kdo je právě na hřišti, aktuální série bez odpovědi, týmové fauly v periodě, oddechové
časy, hráči ve faulových potížích (≥ 4, v 1. poločase ≥ 3), rozdíl skóre za posledních 5 minut.

## Metriky (ala srsni-data)

Rozbor zápasu — `nbl/metrics.py`, pro oba týmy:

- **Box score** z oficiálních součtů FIBA (`tot_*` — včetně týmových doskoků a ztrát), body z paintu,
  z protiútoků, druhých šancí, lavičky a po ztrátách soupeře.
- **Držení** = FGA − ORB + TO + 0,44·FTA, **pace** = průměr držení obou týmů na 40 minut,
  **ORtg / DRtg / Net** = body na 100 držení.
- **Four Factors**: eFG% = (FGM + 0,5·3PM)/FGA, TOV% = TO/(FGA + 0,44·FTA + TO),
  ORB% = ORB/(ORB + soupeřovy DRB), FT rate = FTM/FGA — pro útok i obranu.
- Dále TS%, 3PAr, FTA rate, AST% (asistované koše), AST/TO, STL% (na držení soupeře), BLK% (na 2PA soupeře).
- **Hráči**: minuty, střelba, TS%, eFG%, USG%, EFF (jako v highlights-engine), Hollingerův Game Score,
  +/−, ±/40, **on/off net rating** (ratingy týmu s hráčem na hřišti a bez něj).
- **Pětky, trojice, dvojice** (rekonstrukce z play-by-play podle střídání, jako lineup analýza
  v srsni-data): čas spolu, skóre, ORtg/DRtg/Net, eFG my/soupeř.
- **Asistenční dvojice** nahrávač → střelec (jako srsni-truth `lineups.py`).
- **Zóny střelby**: dvojka v paintu, střední dvojka, trojka z rohu, trojka z oblouku + souřadnice všech střel.
- **Body podle času útoku** (0–5 / 5–10 / 10–15 / 15–20 / 20+ s) — rekonstrukce držení z pbp
  (port `attackPoints` ze srsni-data, varianta „doskok v útoku pokračuje v témže útoku“).
- **Průběh**: série bez odpovědi (≥ 8 b.), největší vedení, střídání vedení, vyrovnání,
  čas ve vedení, časová osa rozdílu skóre.
- **Clutch**: posledních 5 minut Q4/prodloužení při rozdílu ≤ 5 b. (body, střelba, ztráty, kdo skóroval).

Sezóna — `nbl/season.py`: pokročilé metriky se počítají **ze součtů** (ne průměrem procent),
USG% a on/off hráčů taky ze součtů přes zápasy, pětky se sčítají podle jmen hráčů
(FIBA `pno` platí jen v rámci jednoho zápasu — stejná poznámka jako v srsni-truth). Sezónní
pětky/trojice/dvojice jen s aspoň 5/10/15 minutami pohromadě.

Tabulka: % výher → vzájemné zápasy týmů se shodou (výhry, pak rozdíl skóre v minitabulce) →
celkový rozdíl skóre → dané body. Je to zjednodušení pravidel NBL.

## Zdroje a poznámky k datům

- **Rozpis**: týmové stránky `nbl.basketball/tym/<slug>` (jako `season-scraper.mjs` v srsni-data —
  dávají i FIBA ID blízkých zápasů a čtvrtiny) + ligový rozpis `nbl.basketball/zapasy?y=<rok>&c=<tým>`
  (jako `discovery.py` v srsni-truth). Slugy týmů se sbírají z odkazů na stránkách. Výsledky se slučují
  podle `nblId` a nic už zjištěného se nepřepisuje prázdnou hodnotou.
- **FIBA ID**: z řádku rozpisu, ze stránky detailu zápasu (`/zapas/<id>`) a z pole `othermatches`
  v FIBA `data.json` (FIBA posílá i souběžné zápasy soutěže).
- **Prodloužení**: FIBA čísluje prodloužení znovu od 1 (`period: 1, periodType: "OVERTIME"`),
  `ot_score` je součet všech prodloužení. Engine to převádí na periody 5, 6, …
- **Ověření**: na 42 zápasech sezóny 2025/26 sedí rekonstruované on-court +/− s oficiálním
  `sPlusMinusPoints` u 96 % hráčů přesně; zbytek jsou ±1–2 body u střídání ve stejné sekundě
  jako trestné hody. Body po čtvrtinách a čas útoku sedí na konečné skóre.
- **Akce zapsané zpětně** (vyšší `actionNumber`, starý herní čas) se řadí podle herního času,
  stejně jako v highlights-engine.

## Struktura

```
nbl/teams.py      identita týmů (slug, krátké jméno)
nbl/schedule.py   rozpis celé ligy z nbl.basketball, dohledání FIBA ID
nbl/fiba.py       stažení FIBA data.json (+ oprava mojibake), othermatches
nbl/metrics.py    rozbor zápasu (dohraného i živého)
nbl/season.py     tabulka, sezóny týmů, hráči, žebříčky, pořadí v lize
nbl/build.py      orchestrátor -> data/<sezóna>/
nbl/live.py       živé statistiky -> větev live
scripts/commit_data.sh   commit/push dat s ochranou proti souběhu workflowů
tests/            testy nad skutečnými FIBA daty (tests/fixtures), bez sítě
```

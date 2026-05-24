# Copenhell 2026 — AI Band Anbefaler

💀 AI-drevet anbefalingsværktøj til Copenhell 2026.

**Live:** [jaisper.github.io/CopenHell](https://jaisper.github.io/CopenHell/)

## Features

- 💀 **85+ bands** — komplet lineup inkl. Boneyard bands
- 📅 **Dag-opdeling** — Onsdag til Lørdag (24-27 juni)
- 🎤 **4 scener** — Helvíti, Hades, Pandæmonium, Gehenna (+ Boneyard)
- 🕐 **Tidsplan-visning** — toggle mellem listevisning og tidslinje-grid
  - Helvíti-bands: 90 min bokse, øvrige scener: 60 min
  - Sticky scene-headers og tid-kolonne
- 🤖 **AI-anbefalinger** — op til 20 personlige anbefalinger baseret på:
  - Valgte favorit-bands fra programmet
  - Foretrukne genrer (Heavy Metal (Trad), Hard Rock, Thrash, Dødsmetal, Black, Doom, Power, Glam, Gothic, Alternativ, Progressiv, Speed Metal)
  - Egne favorit-kunstnere (fritekst, max 3)
- 🎧 **Spotify-links** — direkte søgning for hvert band
- 🔗 **Band-links** — direkte til copenhell.dk kunstnerside
- 📱 **Responsivt** — tilpasset desktop, iPad og mobil
- ⏰ **Spilletider** — hentes fra danske kunstnersider (korrekt 24h format)
- 🟡 **AI-farver** — guld ramme på top 1-10, grøn på 11-20 anbefalinger
- 🔄 **Live scraping** — opdaterer automatisk fra copenhell.dk ved sideload, merger med hardcoded data

## AI Modeller (via Groq)

|Model          |Beskrivelse                                 |
|---------------|--------------------------------------------|
|🧠 GPT-OSS 120B |Anbefalet — bedst til korrekte beskrivelser |
|⚡ Llama 3.3 70B|Hurtig, kan hallucinere om ukendte bands    |
|🔍 Compound Beta|Web search — langsom, rammer ofte rate limit|
|💨 Llama 3.1 8B |Ultra-hurtig, lavere kvalitet               |

Auto-fallback: GPT-OSS → Llama 3.3 ved rate limit/token overflow.

## Arkitektur

- **Single-file HTML** — ingen build process, ingen dependencies
- **CACHED_LINEUP** — 85 bands hardcoded med dag, scene og slug
- **Live scraping** — henter programside fra copenhell.dk via CORS proxy, merger med cache
- **Enrichment** — henter spilletider fra danske kunstnersider (`copenhell.dk/artist/`) i baggrunden
- **sessionStorage cache** — spilletider gemmes pr. session
- **Groq API** — gratis AI via brugerens egen API-nøgle
- **GitHub Pages** — deployment via Actions workflow
- **GitHub Actions monitor** — daglig scraping der sender email ved nye bands

## Brug

1. Åbn [jaisper.github.io/CopenHell](https://jaisper.github.io/CopenHell/)
1. Vælg favorit-bands (💀 ikon) og/eller genrer
1. (Valgfrit) Tilføj egne favorit-kunstnere i fritekstfeltet
1. Indtast Groq API-nøgle (⚙ AI Indstillinger)
1. Tryk “Find anbefalinger”
1. Brug 🕐 Tidsplan knappen for tidslinje-visning

## Opdatering

Programdata opdateres automatisk via live scraping fra copenhell.dk.
Hardcoded fallback i `CACHED_LINEUP` opdateres manuelt ved behov.
Spilletider hentes fra `copenhell.dk/artist/{slug}/` (danske sider, 24h format).

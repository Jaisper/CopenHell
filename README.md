# ROS 2026 — AI Kunstner Anbefaler

🎪 AI-drevet anbefalingsværktøj til Roskilde Festival 2026.

**Live:** [jaisper.github.io/Roskilde](https://jaisper.github.io/Roskilde/)

## Features

- 🎵 **178 kunstnere** — komplet lineup inkl. First Days (28-30 juni) og Final Days (1-4 juli)
- 📅 **Dag-opdeling** — Søndag/Mandag/Tirsdag (First Days) + Onsdag til Lørdag (Final Days)
- 🎤 **7 scener** — Orange, Arena, Gloria, Eos, Fauna, Lagune, Platform
- 🕐 **Tidsplan-visning** — toggle mellem listevisning og tidslinje-grid med sticky headers
- 🤖 **AI-anbefalinger** — op til 20 personlige anbefalinger baseret på:
  - Valgte favorit-kunstnere fra programmet
  - Foretrukne genrer (Pop, Rock, R&B, Indie Rock, Hip-hop/Rap, Elektronisk, Punk, Heavy, Singer-songwriter, Folk/Traditional, Latin, Global/Afro, Eksperimentel)
  - Egne favorit-kunstnere (fritekst, max 3)
- 🎧 **Spotify-links** — direkte søgning for hver kunstner
- 🔗 **Kunstner-links** — direkte til roskilde-festival.dk kunstnerside
- 📱 **Responsivt** — tilpasset desktop, iPad og mobil
- ⏰ **Spilletider** — vises i guld, sorteret efter starttid. Hentes progressivt fra kunstnersider
- 🟢 **AI-farver** — grøn ramme på top 1-10, guld på 11-20 anbefalinger
- 💾 **Offline-klar** — komplet hardcoded lineup, enrichment kun for spilletider

## AI Modeller (via Groq)

| Model | Beskrivelse |
|-------|-------------|
| 🧠 GPT-OSS 120B | Anbefalet — bedst til korrekte beskrivelser |
| ⚡ Llama 3.3 70B | Hurtig, kan hallucinere om ukendte kunstnere |
| 🔍 Compound Beta | Web search — langsom, rammer ofte rate limit |
| 💨 Llama 3.1 8B | Ultra-hurtig, lavere kvalitet |

Auto-fallback: GPT-OSS → Llama 3.3 ved rate limit/token overflow.

## Arkitektur

- **Single-file HTML** — ingen build process, ingen dependencies
- **CACHED_LINEUP** — 178 kunstnere hardcoded med dag, scene og slug
- **Enrichment** — baggrunds-process der henter spilletider fra kunstnersider via CORS proxy
- **localStorage cache** — spilletider gemmes lokalt, hentes kun én gang
- **Groq API** — gratis AI via brugerens egen API-nøgle
- **GitHub Pages** — deployment via Actions workflow

## Brug

1. Åbn [jaisper.github.io/Roskilde](https://jaisper.github.io/Roskilde/)
2. Vælg favorit-kunstnere (🎵 ikon) og/eller genrer
3. (Valgfrit) Tilføj egne favorit-kunstnere i fritekstfeltet
4. Indtast Groq API-nøgle (⚙ AI Indstillinger)
5. Tryk "Find anbefalinger"
6. Brug 🕐 Tidsplan knappen for tidslinje-visning

## Opdatering

Programdata er hardcoded i `CACHED_LINEUP`. Ved ændringer:
1. Opdater `CACHED_LINEUP` i `index.html`
2. Brug "↻ Tving opdatering" linket for at rydde lokal cache

#!/usr/bin/env python3
"""
Copenhell Artist Monitor Agent
Checker dagligt for nye kunstnere og sender mail ved nye tilføjelser.
Bruger Last.fm til kunstnerbeskrivelser (gratis).
Alle hemmeligheder hentes fra environment variables / GitHub Secrets.
"""

import json
import os
import re
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── KONFIGURATION ────────────────────────────────────────────────────────────

CONFIG = {
    "recipient_email":       "jesper_lippert@hotmail.com",
    "smtp_host":             os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port":             int(os.getenv("SMTP_PORT", 587)),
    "smtp_user":             os.getenv("SMTP_USER"),
    "smtp_password":         os.getenv("SMTP_PASSWORD"),
    "spotify_client_id":     os.getenv("SPOTIFY_CLIENT_ID"),
    "spotify_client_secret": os.getenv("SPOTIFY_CLIENT_SECRET"),
    "lastfm_api_key":        os.getenv("LASTFM_API_KEY"),
    "state_file":            Path(__file__).parent / "known_artists.json",
    "copenhell_url":         "https://copenhell.dk/en/category/copenhell-2026-en/",
}

# ─── HJÆLPEFUNKTIONER ─────────────────────────────────────────────────────────

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def fetch_artists() -> set[str]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CopenhellBot/1.0)"}
    resp = requests.get(CONFIG["copenhell_url"], headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    artists = set()
    band_posts = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True).lower()
        if ("band" in title or "artist" in title or "lineup" in title) and "copenhell.dk" in href:
            band_posts.append(href)

    visited = set()
    for url in band_posts[:10]:
        if url in visited:
            continue
        visited.add(url)
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            post_soup = BeautifulSoup(r.text, "html.parser")
            content = post_soup.find("article") or post_soup.find("main") or post_soup
            text = content.get_text(separator="\n")
            matches = re.findall(r'\b([A-Z][A-Z0-9 &\.\-\']{1,40}[A-Z0-9])\b', text)
            for match in matches:
                name = match.strip()
                if name not in {"COPENHELL", "JUNE", "IRON", "NEW", "BANDS",
                                "THE", "AND", "FOR", "WITH", "FROM", "MORE",
                                "ALL", "STAGE", "TICKETS", "FESTIVAL"}:
                    artists.add(name)
            time.sleep(0.5)
        except Exception as e:
            print(f"[{now()}] Kunne ikke hente {url}: {e}")

    if not artists:
        text = soup.get_text(separator="\n")
        matches = re.findall(r'\b([A-Z][A-Z0-9 &\.\-\']{1,40}[A-Z0-9])\b', text)
        for match in matches:
            name = match.strip()
            if len(name) > 2 and name not in {"COPENHELL", "JUNE", "NEW", "THE",
                                               "AND", "FOR", "TICKETS", "FESTIVAL"}:
                artists.add(name)

    print(f"[{now()}] Fandt {len(artists)} kunstnere.")
    return artists

# ─── STATE ────────────────────────────────────────────────────────────────────

def load_known_artists() -> set[str]:
    p = CONFIG["state_file"]
    return set(json.load(open(p))) if p.exists() else set()

def save_known_artists(artists: set[str]):
    with open(CONFIG["state_file"], "w") as f:
        json.dump(sorted(artists), f, ensure_ascii=False, indent=2)

# ─── LAST.FM BESKRIVELSE ─────────────────────────────────────────────────────

def get_lastfm_description(artist_name: str) -> str:
    """Henter kunstnerbeskrivelse fra Last.fm (gratis API)."""
    if not CONFIG.get("lastfm_api_key"):
        print(f"[{now()}] LASTFM_API_KEY ikke sat - springer over.")
        return ""
    try:
        search_name = artist_name.title()
        resp = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method":  "artist.getinfo",
                "artist":  search_name,
                "api_key": CONFIG["lastfm_api_key"],
                "format":  "json",
                "lang":    "en",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        bio = data.get("artist", {}).get("bio", {}).get("content", "")
        if not bio:
            bio = data.get("artist", {}).get("bio", {}).get("summary", "")
        if bio:
            # Fjern Last.fm "Read more"-link i slutningen
            bio = bio.split("<a href")[0].strip()
            # Begræns til ~1200 tegn og klip ved punktum
            if len(bio) > 1200:
                bio = bio[:1200]
                last_period = bio.rfind(".")
                if last_period > 800:
                    bio = bio[:last_period + 1]
        return bio.strip()
    except Exception as e:
        print(f"[{now()}] Last.fm fejl for {artist_name}: {e}")
    return ""

# ─── SPOTIFY ──────────────────────────────────────────────────────────────────

def get_spotify_token() -> str | None:
    if not CONFIG["spotify_client_id"] or not CONFIG["spotify_client_secret"]:
        print(f"[{now()}] Spotify secrets ikke sat - springer over.")
        return None
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(CONFIG["spotify_client_id"], CONFIG["spotify_client_secret"]),
        timeout=10,
    )
    if resp.ok:
        return resp.json().get("access_token")
    print(f"[{now()}] Spotify token fejl: {resp.text}")
    return None

def get_spotify_info(artist_name: str, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        "https://api.spotify.com/v1/search",
        params={"q": artist_name.title(), "type": "artist", "limit": 1},
        headers=headers,
        timeout=10,
    )
    if not resp.ok:
        return {}
    items = resp.json().get("artists", {}).get("items", [])
    if not items:
        return {}
    a = items[0]
    return {
        "spotify_url": a.get("external_urls", {}).get("spotify", ""),
        "genres":      ", ".join(a.get("genres", [])[:3]) or "Ukendt genre",
        "followers":   f"{a.get('followers', {}).get('total', 0):,}".replace(",", "."),
        "popularity":  a.get("popularity", 0),
        "image":       (a.get("images") or [{}])[0].get("url", ""),
    }

# ─── EMAIL ────────────────────────────────────────────────────────────────────

def send_email(new_artists: list[str], spotify_data: dict, descriptions: dict):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Copenhell: {len(new_artists)} ny(e) kunstner(e) annonceret!"
    msg["From"]    = CONFIG["smtp_user"]
    msg["To"]      = CONFIG["recipient_email"]

    rows = ""
    for name in sorted(new_artists):
        info = spotify_data.get(name, {})
        description = descriptions.get(name, "")

        img = (f'<img src="{info["image"]}" width="90" '
               f'style="border-radius:8px;display:block;" />'
               if info.get("image") else "")

        btn = (f'<a href="{info["spotify_url"]}" '
               f'style="background:#1DB954;color:#fff;padding:7px 16px;'
               f'border-radius:20px;text-decoration:none;font-size:13px;display:inline-block;">'
               f'Abn i Spotify</a>'
               if info.get("spotify_url") else "")

        meta = ""
        if info:
            meta = (
                f'<p style="margin:4px 0 10px 0;color:#888;font-size:12px;">'
                f'Genre: {info.get("genres","?")} &nbsp;|&nbsp; '
                f'Followers: {info.get("followers","?")} &nbsp;|&nbsp; '
                f'Popularitet: {info.get("popularity","?")}/100</p>'
            )

        desc_html = ""
        if description:
            paragraphs = [p.strip() for p in description.split("\n") if p.strip()]
            desc_html = "".join(
                f'<p style="margin:6px 0;color:#333;font-size:14px;line-height:1.6;">{p}</p>'
                for p in paragraphs
            )
        else:
            desc_html = '<p style="color:#aaa;font-size:13px;font-style:italic;">Ingen Last.fm-beskrivelse fundet.</p>'

        rows += f"""
        <tr>
          <td style="padding:24px 0;border-bottom:2px solid #f0f0f0;vertical-align:top;">
            <table style="width:100%;border-collapse:collapse;">
              <tr>
                <td style="width:106px;vertical-align:top;padding-right:16px;">{img}</td>
                <td style="vertical-align:top;">
                  <h2 style="margin:0 0 2px 0;font-size:22px;color:#c0392b;">{name}</h2>
                  {meta}
                  {desc_html}
                  <div style="margin-top:14px;">{btn}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:24px;background:#fff;">
      <h1 style="color:#c0392b;border-bottom:3px solid #c0392b;padding-bottom:10px;">
        Nye Copenhell 2026 kunstnere!
      </h1>
      <p style="color:#555;font-size:15px;">
        {len(new_artists)} ny(e) kunstner(e) er netop annonceret til <strong>Copenhell 2026</strong>:
      </p>
      <table style="width:100%;border-collapse:collapse;">
        {rows}
      </table>
      <p style="color:#aaa;font-size:12px;margin-top:24px;">
        Beskrivelser fra Last.fm &nbsp;|&nbsp;
        <a href="{CONFIG['copenhell_url']}">Se alle nyheder pa Copenhell.dk</a>
      </p>
    </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP(CONFIG["smtp_host"], CONFIG["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(CONFIG["smtp_user"], CONFIG["smtp_password"])
        server.sendmail(CONFIG["smtp_user"], CONFIG["recipient_email"], msg.as_string())
    print(f"[{now()}] Mail sendt til {CONFIG['recipient_email']}.")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"[{now()}] Starter Copenhell monitor...")

    try:
        current = fetch_artists()
    except Exception as e:
        print(f"[{now()}] FEJL ved scraping: {e}")
        return

    if not current:
        print(f"[{now()}] Ingen kunstnere fundet - tjek fetch_artists()")
        return

    known = load_known_artists()
    new_artists = current - known

    if not new_artists:
        print(f"[{now()}] Ingen nye kunstnere. Total kendte: {len(known)}")
        save_known_artists(current)
        return

    print(f"[{now()}] {len(new_artists)} ny(e): {new_artists}")

    # Hent Spotify-info
    spotify_data = {}
    token = get_spotify_token()
    if token:
        for name in new_artists:
            spotify_data[name] = get_spotify_info(name, token)
            time.sleep(0.3)

    # Hent Last.fm-beskrivelser
    descriptions = {}
    for name in new_artists:
        print(f"[{now()}] Henter Last.fm-beskrivelse for {name}...")
        descriptions[name] = get_lastfm_description(name)
        time.sleep(0.5)

    try:
        send_email(list(new_artists), spotify_data, descriptions)
    except Exception as e:
        print(f"[{now()}] FEJL ved mail: {e}")
        return

    save_known_artists(current)
    print(f"[{now()}] Faerdig. State opdateret.")

if __name__ == "__main__":
    main()

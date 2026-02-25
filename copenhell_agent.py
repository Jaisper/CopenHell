#!/usr/bin/env python3
"""
Copenhell Artist Monitor Agent
Checker dagligt for nye kunstnere og sender mail ved nye tilføjelser.
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
    "state_file":            Path(__file__).parent / "known_artists.json",
    # Copenhell annoncerer nye bands via nyhedsposter på denne kategori-side
    "copenhell_url":         "https://copenhell.dk/en/category/copenhell-2026-en/",
}

# ─── HJÆLPEFUNKTIONER ─────────────────────────────────────────────────────────

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def fetch_artists() -> set[str]:
    """
    Henter kunstnernavne fra Copenhell's nyhedsposter om nye bands.
    Nye bands annonceres i titler som "13 NEW BANDS FOR COPENHELL 2026"
    og listes med STORE BOGSTAVER i brødteksten.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CopenhellBot/1.0)"}
    resp = requests.get(CONFIG["copenhell_url"], headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    artists = set()

    # Hent links til alle band-annonceringsposter
    band_posts = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True).lower()
        if ("band" in title or "artist" in title or "lineup" in title) and "copenhell.dk" in href:
            band_posts.append(href)

    # Besøg hver post og udtræk kunstnernavne (STORE BOGSTAVER = band)
    visited = set()
    for url in band_posts[:10]:  # Max 10 poster
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
                                "ALL", "STAGE", "TICKETS", "FESTIVAL", "BANDS"}:
                    artists.add(name)
            time.sleep(0.5)
        except Exception as e:
            print(f"[{now()}] Kunne ikke hente {url}: {e}")

    # Fallback: udtræk direkte fra forsiden
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
        params={"q": artist_name, "type": "artist", "limit": 1},
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

def send_email(new_artists: list[str], spotify_data: dict):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Copenhell: {len(new_artists)} ny(e) kunstner(e) annonceret!"
    msg["From"]    = CONFIG["smtp_user"]
    msg["To"]      = CONFIG["recipient_email"]

    rows = ""
    for name in sorted(new_artists):
        info = spotify_data.get(name, {})
        img = (f'<img src="{info["image"]}" width="80" '
               f'style="border-radius:50%;margin-right:12px;" />'
               if info.get("image") else "")
        btn = (f'<a href="{info["spotify_url"]}" '
               f'style="background:#1DB954;color:#fff;padding:6px 14px;'
               f'border-radius:20px;text-decoration:none;font-size:13px;">'
               f'Abn i Spotify</a>'
               if info.get("spotify_url") else "")
        rows += (
            f'<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:16px;vertical-align:top;width:80px;">{img}</td>'
            f'<td style="padding:16px;vertical-align:top;">'
            f'<strong style="font-size:18px;">{name}</strong><br/>'
            f'<span style="color:#666;font-size:13px;">Genre: {info.get("genres", "?")}</span><br/>'
            f'<span style="color:#666;font-size:13px;">'
            f'Followers: {info.get("followers", "?")} | '
            f'Popularitet: {info.get("popularity", "?")}/100</span><br/>'
            f'<div style="margin-top:10px;">{btn}</div>'
            f'</td></tr>'
        )

    html = (
        '<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;">'
        '<h1 style="color:#c0392b;">Nye Copenhell kunstnere!</h1>'
        '<p style="color:#555;">Folgende er netop annonceret til <strong>Copenhell</strong>:</p>'
        f'<table style="width:100%;border-collapse:collapse;">{rows}</table>'
        '<hr style="margin-top:30px;"/>'
        f'<p style="color:#aaa;font-size:12px;">Tjek lineup: '
        f'<a href="{CONFIG["copenhell_url"]}">{CONFIG["copenhell_url"]}</a></p>'
        '</body></html>'
    )

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

    spotify_data = {}
    token = get_spotify_token()
    if token:
        for name in new_artists:
            spotify_data[name] = get_spotify_info(name, token)
            time.sleep(0.3)

    try:
        send_email(list(new_artists), spotify_data)
    except Exception as e:
        print(f"[{now()}] FEJL ved mail: {e}")
        return

    save_known_artists(current)
    print(f"[{now()}] Faerdig. State opdateret.")

if __name__ == "__main__":
    main()

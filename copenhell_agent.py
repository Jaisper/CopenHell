#!/usr/bin/env python3
"""
Copenhell Artist Monitor Agent
================================
Checker dagligt for nye kunstnere på Copenhell og sender mail ved nye tilføjelser.

Opsætning:
  pip install requests beautifulsoup4 spotipy

Konfiguration:
  Sæt disse environment variables (eller rediger direkte i CONFIG nedenfor):
    SMTP_HOST       - f.eks. smtp.gmail.com
    SMTP_PORT       - f.eks. 587
    SMTP_USER       - din afsender-email
    SMTP_PASSWORD   - dit app-password (Gmail: https://myaccount.google.com/apppasswords)
    SPOTIFY_CLIENT_ID     - fra https://developer.spotify.com/dashboard
    SPOTIFY_CLIENT_SECRET - fra https://developer.spotify.com/dashboard

Kør manuelt:
  python copenhell_agent.py

Opsæt som daglig cron-job (kl. 08:00):
  crontab -e
  0 8 * * * /usr/bin/python3 /sti/til/copenhell_agent.py >> /sti/til/copenhell.log 2>&1
"""

import json
import os
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
    # Modtager
    "recipient_email": "jesper_lippert@hottmail.com",

    # Afsender (SMTP)
    "smtp_host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port":     int(os.getenv("SMTP_PORT", 587)),
    "smtp_user":     os.getenv("SMTP_USER", "DIN_EMAIL@gmail.com"),
    "smtp_password": os.getenv("SMTP_PASSWORD", "DIT_APP_PASSWORD"),

    # Spotify API (https://developer.spotify.com/dashboard)
    "spotify_client_id":     os.getenv("SPOTIFY_CLIENT_ID", "DIN_SPOTIFY_CLIENT_ID"),
    "spotify_client_secret": os.getenv("SPOTIFY_CLIENT_SECRET", "DIN_SPOTIFY_CLIENT_SECRET"),

    # Lokalt state-fil (gemmer kendte kunstnere)
    "state_file": Path(__file__).parent / "known_artists.json",

    # Copenhell URL
    "copenhell_url": "https://www.copenhell.dk/lineup/",
}

# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def fetch_artists() -> set[str]:
    """Henter aktuelle kunstnere fra Copenhell lineup-siden."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CopenhellBot/1.0)"}
    resp = requests.get(CONFIG["copenhell_url"], headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    artists = set()

    # Forsøg flere mulige HTML-strukturer (siden kan ændre sig)
    # Strategi 1: <h2> eller <h3> inde i artist-cards
    for tag in soup.find_all(["h2", "h3", "h4"], class_=lambda c: c and "artist" in c.lower()):
        name = tag.get_text(strip=True)
        if name:
            artists.add(name)

    # Strategi 2: <a> med artist i href eller class
    if not artists:
        for a in soup.find_all("a", href=True):
            if "/artist/" in a["href"] or "/lineup/" in a["href"]:
                name = a.get_text(strip=True)
                if name and len(name) > 1:
                    artists.add(name)

    # Strategi 3: Bred søgning efter tekst i div.artist eller article
    if not artists:
        for el in soup.select("div.artist, article.artist, .lineup-artist, .artist-name"):
            name = el.get_text(strip=True)
            if name and len(name) > 1:
                artists.add(name)

    print(f"[{now()}] Fandt {len(artists)} kunstnere på siden.")
    return artists


# ─── STATE ────────────────────────────────────────────────────────────────────

def load_known_artists() -> set[str]:
    path = CONFIG["state_file"]
    if path.exists():
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_known_artists(artists: set[str]):
    with open(CONFIG["state_file"], "w") as f:
        json.dump(sorted(artists), f, ensure_ascii=False, indent=2)


# ─── SPOTIFY ──────────────────────────────────────────────────────────────────

def get_spotify_token() -> str | None:
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
    """Returnerer Spotify URL og kort info om kunstneren."""
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

    artist = items[0]
    genres = ", ".join(artist.get("genres", [])[:3]) or "Ukendt genre"
    followers = artist.get("followers", {}).get("total", 0)
    spotify_url = artist.get("external_urls", {}).get("spotify", "")
    popularity = artist.get("popularity", 0)

    return {
        "spotify_url": spotify_url,
        "genres": genres,
        "followers": f"{followers:,}".replace(",", "."),
        "popularity": popularity,
        "image": (artist.get("images") or [{}])[0].get("url", ""),
    }


# ─── EMAIL ────────────────────────────────────────────────────────────────────

def send_email(new_artists: list[str], spotify_data: dict[str, dict]):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🤘 Copenhell: {len(new_artists)} ny(e) kunstner(e) annonceret!"
    msg["From"] = CONFIG["smtp_user"]
    msg["To"] = CONFIG["recipient_email"]

    # Byg HTML
    artist_rows = ""
    for name in sorted(new_artists):
        info = spotify_data.get(name, {})
        spotify_url = info.get("spotify_url", "")
        genres = info.get("genres", "Ukendt genre")
        followers = info.get("followers", "?")
        popularity = info.get("popularity", "?")

        img_html = ""
        if info.get("image"):
            img_html = f'<img src="{info["image"]}" width="80" style="border-radius:50%;margin-right:12px;" />'

        spotify_btn = ""
        if spotify_url:
            spotify_btn = (
                f'<a href="{spotify_url}" style="background:#1DB954;color:#fff;'
                f'padding:6px 14px;border-radius:20px;text-decoration:none;font-size:13px;">'
                f'🎧 Åbn i Spotify</a>'
            )

        artist_rows += f"""
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:16px;vertical-align:top;width:80px;">{img_html}</td>
          <td style="padding:16px;vertical-align:top;">
            <strong style="font-size:18px;">{name}</strong><br/>
            <span style="color:#666;font-size:13px;">Genre: {genres}</span><br/>
            <span style="color:#666;font-size:13px;">Followers: {followers} &nbsp;|&nbsp; Popularitet: {popularity}/100</span><br/>
            <div style="margin-top:10px;">{spotify_btn}</div>
          </td>
        </tr>
        """

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;">
      <h1 style="color:#c0392b;">🤘 Nye Copenhell kunstnere!</h1>
      <p style="color:#555;">Følgende kunstner(e) er netop blevet annonceret til <strong>Copenhell</strong>:</p>
      <table style="width:100%;border-collapse:collapse;">
        {artist_rows}
      </table>
      <hr style="margin-top:30px;"/>
      <p style="color:#aaa;font-size:12px;">
        Denne mail er sendt automatisk af Copenhell Monitor Agent.<br/>
        Tjek den fulde lineup på: <a href="{CONFIG['copenhell_url']}">{CONFIG['copenhell_url']}</a>
      </p>
    </body></html>
    """

    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(CONFIG["smtp_host"], CONFIG["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(CONFIG["smtp_user"], CONFIG["smtp_password"])
        server.sendmail(CONFIG["smtp_user"], CONFIG["recipient_email"], msg.as_string())

    print(f"[{now()}] Mail sendt til {CONFIG['recipient_email']} med {len(new_artists)} kunstner(e).")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    print(f"[{now()}] Starter Copenhell monitor...")

    # Hent nuværende kunstnere
    try:
        current_artists = fetch_artists()
    except Exception as e:
        print(f"[{now()}] FEJL ved scraping: {e}")
        return

    if not current_artists:
        print(f"[{now()}] Ingen kunstnere fundet – tjek selektorer i fetch_artists()")
        return

    # Sammenlign med kendte
    known = load_known_artists()
    new_artists = current_artists - known

    if not new_artists:
        print(f"[{now()}] Ingen nye kunstnere. Total kendte: {len(known)}")
        save_known_artists(current_artists)
        return

    print(f"[{now()}] {len(new_artists)} ny(e) kunstner(e): {new_artists}")

    # Hent Spotify-info
    spotify_data = {}
    token = get_spotify_token()
    if token:
        for name in new_artists:
            info = get_spotify_info(name, token)
            spotify_data[name] = info
            time.sleep(0.3)  # Respekter rate limits
    else:
        print(f"[{now()}] Springer Spotify over (ingen token).")

    # Send mail
    try:
        send_email(list(new_artists), spotify_data)
    except Exception as e:
        print(f"[{now()}] FEJL ved mail: {e}")
        return

    # Opdater state
    save_known_artists(current_artists)
    print(f"[{now()}] Færdig. State opdateret.")


if __name__ == "__main__":
    main()

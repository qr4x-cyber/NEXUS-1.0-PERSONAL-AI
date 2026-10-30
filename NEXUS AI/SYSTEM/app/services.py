"""Dis servisler: konum, hava durumu, RSS haberleri ve OpenStreetMap karolari."""

from __future__ import annotations

import math
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Iterable

import requests

UA = {"User-Agent": "NexusDesktopAI/1.0 (kisisel masaustu asistani)"}
TIMEOUT = 8

WMO = {
    0: ("Açık", "☀️"),
    1: ("Az bulutlu", "🌤️"),
    2: ("Parçalı bulutlu", "⛅"),
    3: ("Kapalı", "☁️"),
    45: ("Sisli", "🌫️"),
    48: ("Kırağılı sis", "🌫️"),
    51: ("Hafif çisenti", "🌦️"),
    53: ("Çisenti", "🌦️"),
    55: ("Yoğun çisenti", "🌧️"),
    56: ("Dondurucu çisenti", "🌧️"),
    57: ("Dondurucu çisenti", "🌧️"),
    61: ("Hafif yağmur", "🌦️"),
    63: ("Yağmur", "🌧️"),
    65: ("Şiddetli yağmur", "🌧️"),
    66: ("Dondurucu yağmur", "🌨️"),
    67: ("Dondurucu yağmur", "🌨️"),
    71: ("Hafif kar", "🌨️"),
    73: ("Kar", "❄️"),
    75: ("Yoğun kar", "❄️"),
    77: ("Kar taneleri", "❄️"),
    80: ("Sağanak", "🌦️"),
    81: ("Sağanak", "🌧️"),
    82: ("Şiddetli sağanak", "⛈️"),
    85: ("Kar sağanağı", "🌨️"),
    86: ("Yoğun kar sağanağı", "❄️"),
    95: ("Gök gürültülü", "⛈️"),
    96: ("Dolulu fırtına", "⛈️"),
    99: ("Dolulu fırtına", "⛈️"),
}


def describe_weather(code: int) -> tuple[str, str]:
    return WMO.get(int(code), ("Bilinmiyor", "🌡️"))


# --------------------------------------------------------------------- konum
def fetch_location() -> dict:
    """IP tabanli yaklasik konum. Hata olursa bos sozluk doner."""
    try:
        r = requests.get("https://ipwho.is/", timeout=TIMEOUT, headers=UA)
        data = r.json()
        if data.get("success") and data.get("latitude") is not None:
            return {
                "lat": float(data["latitude"]),
                "lon": float(data["longitude"]),
                "city": data.get("city") or data.get("region") or "",
                "region": data.get("region") or "",
                "country": data.get("country") or "",
            }
    except Exception:
        pass
    try:
        r = requests.get(
            "http://ip-api.com/json/?fields=status,city,regionName,country,lat,lon",
            timeout=TIMEOUT,
            headers=UA,
        )
        data = r.json()
        if data.get("status") == "success":
            return {
                "lat": float(data["lat"]),
                "lon": float(data["lon"]),
                "city": data.get("city") or "",
                "region": data.get("regionName") or "",
                "country": data.get("country") or "",
            }
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------- hava durumu
def fetch_weather(lat: float, lon: float) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min"
        "&timezone=auto&forecast_days=1"
    )
    r = requests.get(url, timeout=TIMEOUT, headers=UA)
    r.raise_for_status()
    data = r.json()
    cur = data.get("current", {})
    daily = data.get("daily", {})
    code = int(cur.get("weather_code", 0))
    label, icon = describe_weather(code)
    return {
        "temp": round(float(cur.get("temperature_2m", 0))),
        "feels": round(float(cur.get("apparent_temperature", 0))),
        "humidity": int(cur.get("relative_humidity_2m", 0)),
        "wind": round(float(cur.get("wind_speed_10m", 0))),
        "code": code,
        "label": label,
        "icon": icon,
        "tmax": round(float((daily.get("temperature_2m_max") or [0])[0])),
        "tmin": round(float((daily.get("temperature_2m_min") or [0])[0])),
    }


# --------------------------------------------------------------------- haber
def _strip_html(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def fetch_news(feeds: Iterable, limit: int = 24) -> list[dict]:
    """RSS/Atom akislarindan basliklari toplar, en yeniden eskiye siralar."""
    items: list[dict] = []
    for feed in feeds or []:
        try:
            name, url = feed[0], feed[1]
        except Exception:
            continue
        try:
            r = requests.get(url, timeout=TIMEOUT, headers=UA)
            if r.status_code >= 400:
                continue
            root = ET.fromstring(r.content)
            entries = root.findall(".//item") or root.findall(
                ".//{http://www.w3.org/2005/Atom}entry"
            )
            for entry in entries[:12]:
                title = (entry.findtext("title") or "").strip()
                if not title:
                    title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                link = (entry.findtext("link") or "").strip()
                if not link:
                    node = entry.find("{http://www.w3.org/2005/Atom}link")
                    link = node.get("href") if node is not None else ""
                pub = (
                    entry.findtext("pubDate")
                    or entry.findtext("{http://www.w3.org/2005/Atom}updated")
                    or ""
                )
                if name.lower().startswith("google"):
                    title = title.rsplit(" - ", 1)[0]
                items.append(
                    {
                        "title": _strip_html(title),
                        "link": link,
                        "source": name,
                        "published": pub,
                    }
                )
        except Exception:
            continue
    seen = set()
    unique = []
    for item in items:
        key = item["title"].lower()[:60]
        if not item["title"] or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:limit]


# ------------------------------------------------------------------------ harita
def lonlat_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


_tile_cache: dict[tuple, tuple[float, bytes]] = {}


def fetch_tile(x: int, y: int, zoom: int) -> bytes | None:
    key = (zoom, x, y)
    cached = _tile_cache.get(key)
    if cached and time.time() - cached[0] < 3600:
        return cached[1]
    sub = "abc"[(x + y) % 3]
    url = f"https://{sub}.tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    try:
        r = requests.get(url, timeout=TIMEOUT, headers=UA)
        if r.status_code == 200 and r.content:
            _tile_cache[key] = (time.time(), r.content)
            return r.content
    except Exception:
        return None
    return None


def fetch_map(lat: float, lon: float, zoom: int = 12, radius: int = 1) -> dict:
    """(2*radius+1)^2 karo indirir; cizim UI tarafinda yapilir."""
    cx, cy = lonlat_to_tile(lat, lon, zoom)
    tiles = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            data = fetch_tile(cx + dx, cy + dy, zoom)
            if data:
                tiles.append((dx + radius, dy + radius, data))
    return {
        "tiles": tiles,
        "count": (2 * radius + 1),
        "zoom": zoom,
        "lat": lat,
        "lon": lon,
        "map_url": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}",
    }


def fetch_search_news(query: str, limit: int = 6) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + requests.utils.quote(query)
        + "&hl=tr&gl=TR&ceid=TR:tr"
    )
    return fetch_news([("Google Haberler", url)], limit=limit)


def stamp(value: str) -> str:
    return value or datetime.now().isoformat(timespec="seconds")

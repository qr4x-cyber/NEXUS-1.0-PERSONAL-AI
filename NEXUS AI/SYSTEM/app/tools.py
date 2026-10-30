"""AI'nin PC uzerinde kullanabilecegi araclar (dosya acma, kapatma, hatirlatici...)."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from . import services
from .config import ACCENTS, Config

IS_WIN = os.name == "nt"
IS_MAC = platform.system() == "Darwin"

APP_ALIASES = {
    "not defteri": "notepad",
    "notepad": "notepad",
    "hesap makinesi": "calc",
    "hesap": "calc",
    "calculator": "calc",
    "paint": "mspaint",
    "boya": "mspaint",
    "explorer": "explorer",
    "dosya gezgini": "explorer",
    "cmd": "cmd",
    "komut istemi": "cmd",
    "powershell": "powershell",
    "terminal": "wt",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "spotify": "spotify",
    "vscode": "code",
    "visual studio code": "code",
    "discord": "discord",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "steam": "steam",
    "excel": "excel",
    "word": "winword",
    "powerpoint": "powerpnt",
    "ayarlar": "ms-settings:",
    "settings": "ms-settings:",
    "kamera": "microsoft.windows.camera:",
    "camera": "microsoft.windows.camera:",
}

DANGEROUS = {
    "shutdown_computer",
    "restart_computer",
    "close_application",
    "run_command",
    "sleep_computer",
}

SCHEMAS: list[dict] = [
    {
        "name": "open_path",
        "description": "Opens a file, folder or URL on the user's computer with the default application.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Absolute path, folder or URL."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "open_application",
        "description": "Launches a desktop application by name (e.g. chrome, spotify, not defteri, hesap makinesi).",
        "parameters": {
            "type": "OBJECT",
            "properties": {"name": {"type": "STRING", "description": "Application name."}},
            "required": ["name"],
        },
    },
    {
        "name": "close_application",
        "description": "Closes a running application by name. Destructive: confirm with user first.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"name": {"type": "STRING", "description": "Application / process name."}},
            "required": ["name"],
        },
    },
    {
        "name": "shutdown_computer",
        "description": "Shuts the computer down after the given number of minutes (0 = immediately).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "minutes": {
                    "type": "NUMBER",
                    "description": "Delay in minutes before shutdown. 0 means now.",
                }
            },
            "required": ["minutes"],
        },
    },
    {
        "name": "restart_computer",
        "description": "Restarts the computer after the given number of minutes (0 = immediately).",
        "parameters": {
            "type": "OBJECT",
            "properties": {"minutes": {"type": "NUMBER", "description": "Delay in minutes."}},
            "required": ["minutes"],
        },
    },
    {
        "name": "cancel_shutdown",
        "description": "Cancels a previously scheduled shutdown or restart.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "lock_screen",
        "description": "Locks the user's screen.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "sleep_computer",
        "description": "Puts the computer to sleep / suspend mode.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "set_volume",
        "description": "Sets the system output volume between 0 and 100.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"percent": {"type": "NUMBER", "description": "Target volume 0-100."}},
            "required": ["percent"],
        },
    },
    {
        "name": "take_screenshot",
        "description": "Takes a screenshot, saves it into the Pictures/Nexus folder and returns the path.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "run_command",
        "description": (
            "Runs a shell command on the user's computer and returns its output. "
            "Use only when no dedicated tool exists. The user must approve it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {"command": {"type": "STRING", "description": "Shell command."}},
            "required": ["command"],
        },
    },
    {
        "name": "list_directory",
        "description": "Lists files and folders inside a directory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Folder path. Defaults to home."}
            },
        },
    },
    {
        "name": "get_system_status",
        "description": "Returns CPU, memory, disk usage, battery and uptime information.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "create_reminder",
        "description": "Creates a reminder that will pop up after the given minutes.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING", "description": "What to remind."},
                "minutes": {
                    "type": "NUMBER",
                    "description": "Minutes from now. Use 0 for immediate.",
                },
            },
            "required": ["text", "minutes"],
        },
    },
    {
        "name": "list_reminders",
        "description": "Lists pending reminders of the user.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "add_note",
        "description": "Appends a line to the user's notes panel.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"text": {"type": "STRING", "description": "Note content."}},
            "required": ["text"],
        },
    },
    {
        "name": "read_notes",
        "description": "Reads the user's notes and reminders.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "remember",
        "description": "Stores a long-term fact about the user in persistent memory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"fact": {"type": "STRING", "description": "Fact to remember."}},
            "required": ["fact"],
        },
    },
    {
        "name": "get_weather",
        "description": "Current weather and daily min/max for a city or the user's location.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "Optional city name."}
            },
        },
    },
    {
        "name": "get_news",
        "description": "Latest headlines from the user's news feeds.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "count": {"type": "INTEGER", "description": "How many headlines (default 5)."}
            },
        },
    },
    {
        "name": "web_search",
        "description": "Searches the web via news sources and returns matching headlines.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"query": {"type": "STRING", "description": "Search query."}},
            "required": ["query"],
        },
    },
    {
        "name": "set_accent_color",
        "description": "Changes the interface accent colour. Accepts a hex code or a Turkish colour name.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "color": {"type": "STRING", "description": "e.g. #2f6bff, mavi, mor, turkuaz."}
            },
            "required": ["color"],
        },
    },
    {
        "name": "get_current_time",
        "description": "Returns current local date and time in Turkish format.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
]


class ToolRegistry:
    """Araclarin calistirilmasini, onay akisini ve arayuz kancalarini yonetir."""

    def __init__(self, config: Config, hooks: dict | None = None, confirm=None):
        self.config = config
        self.hooks = hooks or {}
        self.confirm = confirm  # callable(title, detail) -> bool
        self.log: list[str] = []

    # ------------------------------------------------------------------ tanimlar
    @staticmethod
    def declarations():
        from google.genai import types

        return [types.FunctionDeclaration(**schema) for schema in SCHEMAS]

    def _hook(self, name: str, *args):
        cb = self.hooks.get(name)
        if cb:
            try:
                cb(*args)
            except Exception:
                pass

    # ------------------------------------------------------------------- onay
    def _approved(self, name: str, detail: str) -> bool:
        if not self.config.confirm_dangerous:
            return True
        if not self.confirm:
            return True
        try:
            return bool(self.confirm(name, detail))
        except Exception:
            return False

    # ----------------------------------------------------------------- calistir
    def call(self, name: str, args: dict | None) -> dict:
        args = dict(args or {})
        try:
            handler = getattr(self, f"_t_{name}", None)
            if handler is None:
                return {"ok": False, "error": f"Bilinmeyen araç: {name}"}
            result = handler(**args)
            result = result if isinstance(result, dict) else {"ok": True, "result": result}
            self.log.append(f"{datetime.now():%H:%M:%S} {name} -> {result.get('result', result)}")
            return result
        except TypeError as exc:
            return {"ok": False, "error": f"Parametre hatası: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # --------------------------------------------------------------- araclar
    def _t_get_current_time(self):
        now = datetime.now()
        return {
            "ok": True,
            "result": now.strftime("%d.%m.%Y %H:%M:%S"),
            "weekday": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][
                now.weekday()
            ],
        }

    def _t_open_path(self, path: str):
        target = os.path.expandvars(os.path.expanduser(str(path).strip()))
        if target.startswith(("http://", "https://")):
            import webbrowser

            webbrowser.open(target)
            return {"ok": True, "result": f"{target} tarayıcıda açıldı."}
        if not os.path.exists(target):
            return {"ok": False, "error": f"Yol bulunamadı: {target}"}
        if IS_WIN:
            os.startfile(target)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return {"ok": True, "result": f"{target} açıldı."}

    def _t_open_application(self, name: str):
        key = str(name).strip().lower()
        target = APP_ALIASES.get(key, key)
        try:
            if IS_WIN:
                if target.startswith("ms-") or target.endswith(":"):
                    os.startfile(target)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(f'start "" "{target}"', shell=True)
            elif IS_MAC:
                subprocess.Popen(["open", "-a", target])
            else:
                subprocess.Popen([target])
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{name} başlatılamadı: {exc}"}
        return {"ok": True, "result": f"{name} başlatıldı."}

    def _t_close_application(self, name: str):
        if not self._approved("Uygulamayı kapat", f"'{name}' uygulaması kapatılacak."):
            return {"ok": False, "error": "Kullanıcı iptal etti."}
        key = str(name).strip().lower()
        exe = APP_ALIASES.get(key, key)
        if not exe.endswith(".exe"):
            exe += ".exe"
        try:
            if IS_WIN:
                subprocess.run(
                    ["taskkill", "/IM", exe, "/F"], capture_output=True, text=True, timeout=15
                )
            elif IS_MAC:
                subprocess.run(["pkill", "-f", key], timeout=15)
            else:
                subprocess.run(["pkill", "-f", key], timeout=15)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": f"{name} kapatıldı (çalışıyorsa)."}

    def _t_shutdown_computer(self, minutes: float = 0):
        minutes = max(0, float(minutes))
        when = f"{int(minutes)} dakika sonra" if minutes else "hemen"
        if not self._approved("Bilgisayarı kapat", f"Bilgisayar {when} kapatılacak."):
            return {"ok": False, "error": "Kullanıcı iptal etti."}
        try:
            if IS_WIN:
                subprocess.run(
                    ["shutdown", "/s", "/t", str(int(minutes * 60))], check=True, timeout=15
                )
            elif IS_MAC:
                script = (
                    f"tell application \"System Events\" to shut down in {int(minutes * 60)}"
                    if minutes
                    else 'tell application "System Events" to shut down'
                )
                subprocess.run(["osascript", "-e", script], check=True, timeout=15)
            else:
                subprocess.run(
                    ["shutdown", "-h", f"+{int(minutes)}" if minutes else "now"],
                    check=True,
                    timeout=15,
                )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Kapatma başlatılamadı: {exc}"}
        return {"ok": True, "result": f"Bilgisayar {when} kapanacak."}

    def _t_restart_computer(self, minutes: float = 0):
        minutes = max(0, float(minutes))
        when = f"{int(minutes)} dakika sonra" if minutes else "hemen"
        if not self._approved("Bilgisayarı yeniden başlat", f"Bilgisayar {when} yeniden başlayacak."):
            return {"ok": False, "error": "Kullanıcı iptal etti."}
        try:
            if IS_WIN:
                subprocess.run(
                    ["shutdown", "/r", "/t", str(int(minutes * 60))], check=True, timeout=15
                )
            elif IS_MAC:
                subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to restart'],
                    check=True,
                    timeout=15,
                )
            else:
                subprocess.run(["shutdown", "-r", f"+{int(minutes)}" if minutes else "now"], check=True)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Yeniden başlatma başlatılamadı: {exc}"}
        return {"ok": True, "result": f"Bilgisayar {when} yeniden başlayacak."}

    def _t_cancel_shutdown(self):
        try:
            if IS_WIN:
                subprocess.run(["shutdown", "/a"], capture_output=True, text=True, timeout=10)
            elif IS_MAC:
                subprocess.run(["killall", "shutdown"], capture_output=True, timeout=10)
            else:
                subprocess.run(["shutdown", "-c"], capture_output=True, text=True, timeout=10)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": "Zamanlanmış kapanma iptal edildi."}

    def _t_lock_screen(self):
        try:
            if IS_WIN:
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], timeout=10)
            elif IS_MAC:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to keystroke "q" using {command down, control down}',
                    ],
                    timeout=10,
                )
            else:
                subprocess.run(["loginctl", "lock-session"], timeout=10)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": "Ekran kilitlendi."}

    def _t_sleep_computer(self):
        if not self._approved("Uyku modu", "Bilgisayar uyku moduna alınacak."):
            return {"ok": False, "error": "Kullanıcı iptal etti."}
        try:
            if IS_WIN:
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], timeout=10)
            elif IS_MAC:
                subprocess.run(["pmset", "sleepnow"], timeout=10)
            else:
                subprocess.run(["systemctl", "suspend"], timeout=10)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": "Bilgisayar uyku moduna alınıyor."}

    def _t_set_volume(self, percent: float = 50):
        percent = max(0, min(100, float(percent)))
        try:
            if IS_WIN:
                try:
                    from ctypes import POINTER, cast

                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = cast(interface, POINTER(IAudioEndpointVolume))
                    volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
                except Exception:
                    script = (
                        "$o = New-Object -ComObject WScript.Shell; "
                        f"1..50 | ForEach-Object {{ $o.SendKeys([char]174) }}; "
                        f"1..{max(1, round(percent / 2))} | ForEach-Object {{ $o.SendKeys([char]175) }}"
                    )
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command", script],
                        capture_output=True,
                        timeout=20,
                    )
            elif IS_MAC:
                subprocess.run(["osascript", "-e", f"set volume output volume {int(percent)}"], timeout=10)
            else:
                subprocess.run(
                    ["amixer", "-D", "pulse", "sset", "Master", f"{int(percent)}%"], timeout=10
                )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": f"Ses %{int(percent)} yapıldı."}

    def _t_take_screenshot(self):
        try:
            from PIL import ImageGrab

            folder = Path.home() / "Pictures" / "Nexus"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"ekran-{datetime.now():%Y%m%d-%H%M%S}.png"
            ImageGrab.grab().save(path)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Ekran görüntüsü alınamadı: {exc}"}
        return {"ok": True, "result": f"Ekran görüntüsü kaydedildi: {path}"}

    def _t_run_command(self, command: str):
        command = str(command).strip()
        if not command:
            return {"ok": False, "error": "Komut boş."}
        if not self._approved("Komut çalıştır", command):
            return {"ok": False, "error": "Kullanıcı iptal etti."}
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=90,
                cwd=str(Path.home()),
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Komut 90 saniyede bitmedi."}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        out = (proc.stdout or "").strip()[:3000]
        err = (proc.stderr or "").strip()[:1500]
        return {
            "ok": proc.returncode == 0,
            "result": out or "(çıktı yok)",
            "stderr": err,
            "returncode": proc.returncode,
        }

    def _t_list_directory(self, path: str = ""):
        target = os.path.expanduser(path or "~")
        try:
            entries = []
            with os.scandir(target) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    entries.append(entry.name + ("/" if entry.is_dir() else ""))
                    if len(entries) >= 80:
                        break
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": entries, "path": target}

    def _t_get_system_status(self):
        info: dict = {
            "os": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "python": platform.python_version(),
        }
        try:
            import psutil

            info.update(
                {
                    "cpu_percent": psutil.cpu_percent(interval=0.3),
                    "ram_percent": psutil.virtual_memory().percent,
                    "ram_free_gb": round(psutil.virtual_memory().available / 1024**3, 1),
                    "disk_percent": psutil.disk_usage("/").percent,
                    "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
                }
            )
            battery = psutil.sensors_battery()
            if battery:
                info["battery_percent"] = round(battery.percent)
                info["charging"] = battery.power_plugged
        except Exception:
            total, used, free = shutil.disk_usage(str(Path.home()))
            info["disk_free_gb"] = round(free / 1024**3, 1)
        return {"ok": True, "result": info}

    def _t_create_reminder(self, text: str, minutes: float = 0):
        minutes = max(0.0, float(minutes))
        when = datetime.now() + timedelta(minutes=minutes)
        item = self.config.add_reminder(str(text).strip(), when.isoformat(timespec="seconds"))
        self._hook("on_reminder", item)
        return {
            "ok": True,
            "result": f"'{text}' için hatırlatıcı kuruldu: {when:%H:%M} ({int(minutes)} dk sonra).",
        }

    def _t_list_reminders(self):
        items = [r for r in self.config.reminders if not r.get("fired")]
        return {
            "ok": True,
            "result": [
                {"text": r.get("text"), "when": r.get("when")} for r in items[:20]
            ],
        }

    def _t_add_note(self, text: str):
        text = str(text).strip()
        if not text:
            return {"ok": False, "error": "Not boş."}
        self.config.notes = (self.config.notes + "\n" if self.config.notes else "") + text
        self.config.save()
        self._hook("on_notes_changed", self.config.notes)
        return {"ok": True, "result": "Not eklendi."}

    def _t_read_notes(self):
        return {
            "ok": True,
            "result": {
                "notes": self.config.notes[-4000:],
                "reminders": [r.get("text") for r in self.config.reminders if not r.get("fired")],
                "memories": self.config.memories[-20:],
            },
        }

    def _t_remember(self, fact: str):
        self.config.remember(str(fact))
        self._hook("on_memory_changed", self.config.memories)
        return {"ok": True, "result": f"Not edildi: {fact}"}

    def _t_get_weather(self, city: str = ""):
        lat = self.config.location.get("lat")
        lon = self.config.location.get("lon")
        label = self.config.location.get("city") or "konum"
        if city:
            try:
                geo = requests.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": city, "count": 1, "language": "tr"},
                    timeout=8,
                ).json()
                hit = (geo.get("results") or [None])[0]
                if hit:
                    lat, lon = hit["latitude"], hit["longitude"]
                    label = hit.get("name", city)
            except Exception:
                pass
        if lat is None or lon is None:
            return {"ok": False, "error": "Konum bilinmiyor."}
        try:
            data = services.fetch_weather(float(lat), float(lon))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Hava durumu alınamadı: {exc}"}
        return {"ok": True, "result": {**data, "city": label}}

    def _t_get_news(self, count: int = 5):
        try:
            items = services.fetch_news(self.config.feeds, limit=max(1, int(count)))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": [i["title"] for i in items[: int(count)]]}

    def _t_web_search(self, query: str):
        try:
            items = services.fetch_search_news(query, limit=6)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        if not items:
            return {"ok": True, "result": "Sonuç bulunamadı."}
        return {
            "ok": True,
            "result": [{"title": i["title"], "source": i["source"]} for i in items],
        }

    def _t_set_accent_color(self, color: str):
        value = str(color).strip()
        picked = None
        if value.startswith("#") and len(value) in (7, 4):
            picked = value
        else:
            for name, hexcode in ACCENTS.items():
                if value.lower() in name.lower() or name.lower() in value.lower():
                    picked = hexcode
                    break
            if not picked and value.lower() in {"blue", "mavi"}:
                picked = ACCENTS["Mavi"]
        if not picked:
            return {"ok": False, "error": "Renk anlaşılmadı. Hex kodu veya mavi/mor/turkuaz gibi bir ad ver."}
        self.config.accent = picked
        self.config.save()
        self._hook("on_accent", picked)
        return {"ok": True, "result": f"Arayüz rengi {picked} yapıldı."}

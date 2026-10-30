"""Gemini istemcisi: metin sohbeti, arac cagirma, seslendirme (TTS) ve transkripsiyon."""

from __future__ import annotations

import re
import threading
from datetime import datetime

from google import genai
from google.genai import types

from .config import LIVE_MODELS, TEXT_MODELS, TTS_MODELS, Config
from .tools import ToolRegistry
from .utils import turkish_date


def make_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key.strip())


def validate_key(api_key: str) -> tuple[bool, str]:
    try:
        client = make_client(api_key)
        for _ in client.models.list(config={"page_size": 1}):
            break
        return True, "API anahtarı geçerli."
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def build_system_prompt(config: Config, mode: str = "text") -> str:
    import platform

    now = datetime.now()
    personality = (config.user_about or "").strip()
    memories = "\n".join(f"- {m}" for m in config.memories[-20:]) or "- (henüz yok)"
    notes = (config.notes or "").strip()[-1200:] or "(boş)"
    pending = [r.get("text", "") for r in config.reminders if not r.get("fired")][-8:]
    reminders = "\n".join(f"- {r}" for r in pending) or "- (yok)"

    lines = [
        f"Senin adın {config.ai_name}. Kullanıcı sana bu adla sesleniyor; adını asla değiştirme.",
        "Sen kullanıcının kendi bilgisayarında çalışan, sesli konuşabilen ve sistemi yönetebilen kişisel yapay zekâ asistanısın.",
        "",
        "KİMLİK",
        f"- Kullanıcının adı: {config.user_name or 'bilinmiyor'}",
        f"- Kullanıcı hakkında: {personality or 'henüz bilgi yok'}",
        "- Kişiliğini bu bilgilere göre şekillendir: samimi, zeki, kısa ve net konuş. Gereksiz övgü ve dolgu cümle yok.",
        "",
        "KURALLAR",
        "- Her zaman Türkçe konuş (kullanıcı başka dilde yazarsa o dilde cevap ver).",
        "- Sesli modda cevapların kısa ve doğal olsun; en fazla 2-3 cümle. Uzun listeleri sesli modda okuma.",
        "- Bilmediğin bir şeyi uydurma; emin değilsen söyle veya `web_search` kullan.",
        "- Bilgisayarı etkileyen işlemlerde (kapatma, yeniden başlatma, uygulama kapatma, komut çalıştırma) önce tek cümleyle ne yapacağını söyle, sonra aracı çağır.",
        "- Kullanıcı bir şeyi hatırlamanı isterse `remember` aracını kullan.",
        "- `get_current_time` dışında tarih/saat uydurma; aşağıdaki güncel zamanı kullan.",
        "",
        "GÜNCEL BİLGİ",
        f"- Tarih/saat: {turkish_date(now)} {now:%H:%M}",
        f"- İşletim sistemi: {platform.system()} {platform.release()}",
        f"- Bekleyen hatırlatıcılar:\n{reminders}",
        f"- Kullanıcının notları (son kısım):\n{notes}",
        "",
        "UZUN SÜRELİ HATIRLADIKLARIN",
        memories,
    ]
    if mode == "live":
        lines += [
            "",
            "SESLİ MOD NOTU",
            "- Karşındaki kişi seninle mikrofonla konuşuyor; yazı yazmıyor. Kısa, akıcı, konuşma dilinde cevap ver.",
            "- Araç sonucu gelene kadar sessiz kal; 'bir saniye' gibi dolgu yapma.",
        ]
    return "\n".join(lines)


class GeminiBrain:
    """Metin sohbeti + arac dongusu + TTS + transkripsiyon."""

    def __init__(self, config: Config, tools: ToolRegistry):
        self.config = config
        self.tools = tools
        self.client = make_client(config.api_key) if config.api_key else None
        self.history: list[types.Content] = []
        self._lock = threading.Lock()
        self._resolved: dict[str, str] = {}
        self._names: set[str] | None = None

    # ------------------------------------------------------------------ modeller
    def _model_names(self) -> set[str]:
        """Hesapta erisilebilen model adlari (tek seferlik)."""
        if self._names is not None:
            return self._names
        names: set[str] = set()
        if self.client is not None:
            try:
                for model in self.client.models.list(config={"page_size": 200}):
                    if getattr(model, "name", None):
                        names.add(model.name.split("/")[-1])
            except Exception:
                names = set()
        self._names = names
        return names

    @staticmethod
    def _guess_model(kind: str, names: set[str]) -> str | None:
        if kind == "tts":
            matches = [n for n in names if "tts" in n]
        elif kind == "live":
            matches = [n for n in names if "live" in n and "translate" not in n]
        else:
            blocked = ("tts", "live", "image", "imagen", "embedding", "veo", "audio")
            matches = [n for n in names if "flash" in n and not any(b in n for b in blocked)]
        if not matches:
            return None
        matches.sort(key=lambda n: (("preview" in n) or ("exp" in n), len(n)))
        return matches[0]

    def resolve(self, kind: str) -> str:
        if kind in self._resolved:
            return self._resolved[kind]
        candidates = {
            "text": TEXT_MODELS,
            "live": LIVE_MODELS,
            "tts": TTS_MODELS,
        }[kind]
        preferred = {
            "text": self.config.text_model,
            "live": self.config.live_model,
            "tts": self.config.tts_model,
        }[kind]
        order = ([preferred] if preferred else []) + [m for m in candidates if m != preferred]
        chosen = order[0]
        names = self._model_names()
        if names:
            hit = next((model for model in order if model in names), None)
            chosen = hit or self._guess_model(kind, names) or order[0]
        elif self.client is not None:
            for model in order:
                try:
                    self.client.models.get(model=model)
                    chosen = model
                    break
                except Exception:
                    continue
        self._resolved[kind] = chosen
        field = {"text": "text_model", "live": "live_model", "tts": "tts_model"}[kind]
        if getattr(self.config, field) != chosen:
            setattr(self.config, field, chosen)
            self.config.save()
        return chosen

    def _tool_config(self) -> types.Tool:
        return types.Tool(function_declarations=ToolRegistry.declarations())

    def _gen_config(self, mode: str = "text") -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=build_system_prompt(self.config, mode),
            tools=[self._tool_config()],
            temperature=0.75,
        )

    # ------------------------------------------------------------------- sohbet
    def ask(self, text: str, image_jpeg: bytes | None = None) -> str:
        if self.client is None:
            raise RuntimeError("API anahtarı yok. Ayarlardan anahtarını gir.")
        parts: list[types.Part] = []
        if image_jpeg:
            parts.append(types.Part.from_bytes(data=image_jpeg, mime_type="image/jpeg"))
        parts.append(types.Part(text=text or "Kameradaki görüntüyü yorumla."))
        with self._lock:
            contents = list(self.history) + [types.Content(role="user", parts=parts)]
        model = self.resolve("text")
        config = self._gen_config("text")
        response = self.client.models.generate_content(
            model=model, contents=contents, config=config
        )

        for _ in range(5):
            calls = getattr(response, "function_calls", None) or []
            if not calls:
                break
            model_content = None
            try:
                model_content = response.candidates[0].content
            except Exception:
                model_content = None
            if model_content is not None:
                contents.append(model_content)
            fr_parts = []
            for call in calls:
                result = self.tools.call(call.name, dict(call.args or {}))
                fr_parts.append(self._function_response_part(call.name, result, getattr(call, "id", None)))
            contents.append(types.Content(role="user", parts=fr_parts))
            response = self.client.models.generate_content(
                model=model, contents=contents, config=config
            )

        try:
            answer = (response.text or "").strip()
        except Exception:
            answer = ""
        if not answer:
            answer = "Bir yanıt üretemedim, tekrar dener misin?"

        with self._lock:
            self.history = contents + [
                types.Content(role="model", parts=[types.Part(text=answer)])
            ]
            self.history = self.history[-24:]
        return answer

    @staticmethod
    def _function_response_part(name: str, result: dict, call_id: str | None):
        payload = {"result": result}
        try:
            return types.Part.from_function_response(
                name=name, response=payload, id=call_id
            )
        except TypeError:
            try:
                return types.Part.from_function_response(name=name, response=payload)
            except Exception:
                return types.Part(text=f"{name}: {result}")

    def reset(self) -> None:
        with self._lock:
            self.history = []

    # -------------------------------------------------------------- transkripsiyon
    def transcribe(self, wav_bytes: bytes, hint: str = "") -> str:
        if self.client is None:
            return ""
        model = self.resolve("text")
        prompt = (
            "Bu ses kaydında söyleneni sadece yaz. Açıklama, noktalama yorumu veya "
            "ek cümle ekleme. Hiç konuşma yoksa boş yanıt ver."
        )
        if hint:
            prompt += f" İpucu: kullanıcı '{hint}' adlı asistana sesleniyor olabilir."
        parts = [
            types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            types.Part(text=prompt),
        ]
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return (response.text or "").strip()
        except Exception:
            return ""

    # -------------------------------------------------------------------- TTS
    def synthesize(self, text: str) -> bytes | None:
        if self.client is None or not text.strip():
            return None
        clean = self._clean_for_speech(text)
        if not clean:
            return None
        model = self.resolve("tts")
        configs = [
            types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self.config.voice
                        )
                    )
                ),
            ),
            {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {"prebuilt_voice_config": {"voice_name": self.config.voice}}
                },
            },
            {"response_modalities": ["AUDIO"]},
        ]
        last_error = None
        for cfg in configs:
            try:
                response = self.client.models.generate_content(
                    model=model, contents=clean, config=cfg
                )
                for candidate in response.candidates or []:
                    for part in (candidate.content.parts if candidate.content else []) or []:
                        if part.inline_data and part.inline_data.data:
                            return part.inline_data.data
                raise RuntimeError("Ses verisi dönmedi.")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        if last_error:
            raise RuntimeError(f"Seslendirme hatası: {last_error}")
        return None

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        text = re.sub(r"[*_#>`]+", "", text)
        text = re.sub(r"https?://\S+", "bağlantı", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:800]

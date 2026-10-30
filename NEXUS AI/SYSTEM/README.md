# NEXUS · Gemini Tabanlı Kişisel Masaüstü Asistanı

Sesli‑sesli (speech‑to‑speech) ve yazı + ses (text‑to‑speech) modlarında çalışan,
bilgisayarını yönetebilen, reaktör çekirdekli bir masaüstü asistanı.

Python + PySide6 ile yazıldı. Tek komutla kurulur, `main.py` ile açılır.

---

## Özellikler

**Ses ve konuşma**
- **Sesli sohbet**: Gemini Live API ile kesintisiz, gerçek zamanlı mikrofon ↔ hoparlör görüşmesi. Araya girip sözünü kesebilirsin.
- **Yazı + ses**: yazdığın cevabı Gemini TTS ile seslendirir; mikrofonla dikte de edebilirsin.
- **Uyandırma**: reaktör çekirdeğine tıkla ya da ona verdiğin adı söyle (“Nexus!”) — uyanır. Tekrar tıkla → uyur.
- **Mikrofon / canlı kamera** düğmeleri üst ortadaki mod düğmesinin sağında ve solunda. Kamera açıkken 3 saniyede bir kare asistana gönderilir.

**Arayüz (açık gri tema, seçtiğin vurgu rengi)**
- Sağ üst: bulunduğun bölgenin haritası (OpenStreetMap, konum IP ile bulunur)
- Hemen altında: güncel haberler (RSS, 4’lü dönen liste)
- Sağ alt: saat (saat:dakika:saniye), altında tarih ve yıl
- Sol üst: hava durumu (Open‑Meteo)
- Altında: hatırlatıcılar · en solda: notlar
- Tam ortada: reaktör çekirdeği · en altta: konuşma dökümü + yazı kutusu

**PC kontrolü (araç çağırma)**
Dosya/klasör/URL açma, uygulama açma‑kapatma, belirli dakika sonra kapatma/yeniden başlatma,
zamanlanmış kapanmayı iptal etme, ekran kilitleme, uyku modu, ses seviyesi, ekran görüntüsü,
dizin listeleme, sistem durumu, kabuk komutu, hatırlatıcı, not, hafıza, web araması, arayüz rengi…

Tehlikeli işlemler (kapatma, uygulama kapatma, kabuk komutu, uyku) varsayılan olarak **onay penceresi** gösterir.
Ayarlardan kapatabilirsin.

---

## Gereksinimler

- Windows 10/11 (macOS ve Linux’ta da çalışır, komutlar uyarlanmıştır)
- Python **3.10+** (kurulumda “Add Python to PATH” işaretli olsun)
- İnternet bağlantısı
- Mikrofon + hoparlör/kulaklık
- [Google AI Studio](https://aistudio.google.com/apikey) üzerinden ücretsiz alınan **Gemini API anahtarı**

---

## Kurulum

1. Bu klasörü bilgisayarına koy (VS Code’da açabilirsin).
2. Terminalde klasörün içinde:

```bash
python setup.py
```

veya Windows’ta **`setup.bat`** dosyasına çift tıkla. Bu komut tüm paketleri kurar.

3. Uygulamayı başlat:

```bash
python main.py
```

veya **`baslat.bat`**.

> `python setup.py --run` ikisini birden yapar.

### İlk açılış sihirbazı
1. Gemini API anahtarını gir (istersen “Anahtarı doğrula” ile test et).
2. Adını ve senin hakkında bilmesi gerekenleri yaz.
3. Asistana bir ad ver (Nexus, Jarvis, Aria…).
4. Arayüz rengini seç → **Başla**.

Ayarlar: sol üstteki ⚙ veya `Ctrl+,`.

---

## Kullanım

| Ne | Nasıl |
|---|---|
| Uyandır / uyut | Ortadaki reaktöre tıkla veya adını söyle |
| Mod değiştir | Üst ortadaki **SESLİ SOHBET / YAZI + SES** düğmesi |
| Mikrofonu kapat | Mod düğmesinin sağındaki 🎤 |
| Canlı kamera | Mod düğmesinin solundaki 🎥 |
| Yazılı mesaj | Alttaki kutu → Enter |
| Hatırlatıcı | Sol paneldeki **+** veya “5 dakika sonra su içmemi hatırlat” |
| Not | Sol alttaki not alanı veya “notlarıma şunu ekle…” |

### Sesli komut örnekleri
- “Chrome’u aç.”
- “Şu dosyayı aç: C:\Users\…\Belgeler\rapor.pdf”
- “10 dakika sonra bilgisayarı kapat.”
- “Kapanmayı iptal et.”
- “Ekranı kilitle.”
- “Sesi 30’a düşür.”
- “Ekran görüntüsü al.”
- “Sistem durumum nasıl?”
- “Bugün hava nasıl?”
- “Son haberleri özetle.”
- “15 dakika sonra toplantıyı hatırlat.”
- “Arayüz rengini mor yap.”

---

## Yapılandırma ve veriler

Ayarlar, notlar, hatırlatıcılar ve hafıza şurada saklanır:

```
%APPDATA%\NexusAI\config.json      (Windows)
~/.config/nexus-ai/config.json     (macOS / Linux)
```

API anahtarı yalnızca bu dosyada tutulur; koda gömülmez, repoya gitmez (`.gitignore`).

**Model seçimi:** Model adları zamanla değiştiği için uygulama, hesabında erişilebilen modelleri listeler ve
çalışan modeli otomatik seçer (metin, canlı ses ve TTS için ayrı ayrı). Ayarlar → Gelişmiş bölümünden elle de
sabitlenebilir. Boş bırakırsan otomatik seçim kullanılır.

---

## EXE olarak paketleme

```bash
exe_olustur.bat
```

PyInstaller’ı kurar ve `dist\Nexus.exe` üretir. EXE ilk çalıştırmada yine API anahtarı sorar.

---

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| “Mikrofon açılamadı” | Windows Ayarlar → Gizlilik → Mikrofon iznini aç; başka uygulama mikrofonu tutuyor olabilir. |
| Asistan kendi sesini duyup kesiliyor | Kulaklık kullan veya hoparlör sesini kıs; yankı önleme için mikrofon, asistan konuşurken zayıf sesleri yok sayar. |
| Ses çıkmıyor | Ayarlar → Ses’ten çıkış cihazını kontrol et. TTS modeli için hesabında erişim olduğundan emin ol. |
| “API anahtarı geçersiz” | AI Studio’dan yeni anahtar oluştur; anahtarda boşluk olmasın. |
| “Kota sınırı” | Ücretsiz kota dolmuştur; bir süre bekle veya AI Studio’dan limitini kontrol et. |
| Canlı oturum hemen kapanıyor | Ayarlar → Gelişmiş’te canlı model adını boş bırak; uygulama uygun modeli kendisi bulur. |
| Harita/haber boş | İnternet veya RSS kaynağı erişilemiyor; birkaç dakika sonra kendini yeniler. |

---

## Dosya yapısı

```
main.py                 Uygulama girişi
setup.py / setup.bat    Kurulum
baslat.bat              Hızlı başlatma
exe_olustur.bat         PyInstaller ile EXE
requirements.txt
app/
  config.py             Kalıcı ayarlar
  theme.py              Açık gri tema + vurgu rengi
  audio.py              Mikrofon, hoparlör, VAD
  gemini.py             Metin sohbeti, araç döngüsü, TTS, transkripsiyon
  live.py               Gemini Live (sesli‑sesli) oturumu
  tools.py              PC kontrol araçları
  services.py           Hava, haber, harita, konum
  utils.py              Yardımcılar
  ui/
    main_window.py      Ana pencere ve akış
    reactor.py          Reaktör çekirdeği
    panels.py           Harita, haber, saat, hava, hatırlatıcı, not, kamera
    onboarding.py       İlk kurulum sihirbazı
    settings.py         Ayarlar
```

İyi kullanımlar. 🤖

# TerraSat — Sun'iy Yo'ldosh Yer Tahlil Platformasi
## Texnik Topshiriq (TZ)

---

## 1. LOYIHA HAQIDA UMUMIY MA'LUMOT

**Loyiha nomi:** TerraSat  
**Versiya:** 1.0  
**Maqsadi:** Qishloq xo'jaligi yerlarini sun'iy yo'ldosh ma'lumotlari asosida real vaqtda tahlil qiluvchi veb-platforma  
**Texnologiya steki:** Python / Django · REST API · SQLite · HTML/CSS/JS · Leaflet.js · Chart.js

---

## 2. MUAMMO VA YECHIM

### 2.1 Mavjud muammo

O'zbekiston qishloq xo'jaligida fermerlar va agronomlar yer holatini baholash uchun:
- Jismoniy dala tekshiruviga borishi kerak (vaqt va xarajat)
- Laboratoriyaga tuproq namunasi olib borishi kerak (1–2 hafta kutish)
- Ob-havo ma'lumotlari tarqoq manbalardan olinadi
- Quruqchilik xavfini oldindan bilish imkoni yo'q

### 2.2 TerraSat yechimi

Foydalanuvchi xaritada maydon belgilab, **30 soniyadan kam** vaqt ichida quyidagilarni oladi:

| Ma'lumot | Manba | Aniqlik |
|----------|-------|---------|
| O'simlik holati (NDVI) | Sentinel-2 sun'iy yo'ldoshi | 10 metr/piksel |
| Tuproq namligi (4 qatlam) | ERA5-Land reanaliz | Soatlik yangilanadi |
| Tuproq kimyosi (pH, loy, qum, azot) | SoilGrids ISRIC laboratoriyasi | Global, 250 metr |
| Ob-havo tarixi (12 oy) | Open-Meteo ERA5 | Kunlik |
| Shamol va namlik | ERA5 arxivi | O'rtacha oylik |
| Quruqchilik indeksi | Hisoblangan (yog'in − ET) | Standartlashtirilgan |
| Agronomik tavsiyalar | Groq LLaMA 3.3 70B | AI-asoslangan |

---

## 3. FUNKSIONAL TALABLAR

### 3.1 Asosiy funksiyalar

**F-01 — Hudud belgilash**
- Foydalanuvchi interaktiv xaritada polygon yoki marker qo'yadi
- Maydon avtomatik gektarda hisoblanadi
- Koordinatalar panelda ko'rsatiladi

**F-02 — Sun'iy yo'ldosh tahlili**
- Belgilangan hudud uchun 12 oylik NDVI tarixi
- Haqiqiy Sentinel-2 rasmidan olingan indekslar (formula emas)
- EVI (Enhanced Vegetation Index) ko'rsatkichi
- Quruqchilik indeksi (DI: −3 dan +3 gacha)

**F-03 — Tuproq tahlili**
- Hozirgi tuproq harorati (0, 6, 18 sm chuqurlik)
- Tuproq namligi (0–1, 1–3, 3–9, 9–27 sm qatlam)
- pH — kislota/ishqoriylik darajasi
- Loy, qum, lyoss foizi
- Azot va organik uglerod miqdori
- Tuproq teksturasi (Og'ir loy / Loy / Qumoq / Lyoss va boshqalar)

**F-04 — Ob-havo tarixi**
- 12 oylik harorat va yog'in grafigi
- Evapotranspiratsiya (ET) hisoblash
- Shamol tezligi o'rtachasi
- Havo namligi o'rtachasi

**F-05 — AI agronomik tahlil**
- O'simlik holati bahosi (5 daraja)
- Quruqchilik xavfi (past/o'rta/yuqori)
- Tuproq kimyosi asosida tavsiya etiladigan ekinlar (4 ta)
- Dehqonchilik maslahatlari (4 ta)
- Xavflar ro'yxati
- Ustuvor harakatlar
- Keyingi oy bashorati
- Umumiy xulosa

**F-06 — Tahlillarni saqlash va tarixi**
- Nomlab saqlash imkoniyati
- Barcha saqlangan tahlillar bo'yicha qidiruv
- Xaritada avvalgi tahlil poligonini qayta ko'rsatish
- Tahlilni JSON formatida yuklab olish
- Saqlangan tahlilni o'chirish

---

## 4. ARXITEKTURA

```
┌─────────────────────────────────────────────────┐
│                  BRAUZER (Frontend)             │
│  Leaflet.js xarita + Chart.js grafiklar         │
│  4 tab: NDVI · Tuproq · Ob-havo · AI tahlil     │
└──────────────────┬──────────────────────────────┘
                   │ HTTP / REST API
┌──────────────────▼──────────────────────────────┐
│              DJANGO BACKEND                     │
│                                                 │
│  POST /api/satellite/analyze/                   │
│  GET  /api/satellite/history/                   │
│  GET  /api/satellite/history/<id>/              │
│  DELETE /api/satellite/history/<id>/            │
└──┬──────────┬───────────┬────────────┬──────────┘
   │          │           │            │
   ▼          ▼           ▼            ▼
AgroMonit.  Open-Meteo  SoilGrids   Groq API
Sentinel-2  ERA5 arxivi ISRIC       LLaMA 3.3
NDVI tarixi Ob-havo     Tuproq      70B model
            Tuproq sens kimyosi     AI tahlil
                   │
                   ▼
            SQLite ma'lumotlar bazasi
            (saqlangan tahlillar)
```

---

## 5. MA'LUMOT MANBALARI

### 5.1 AgroMonitoring API (OpenWeather)
- **Nima beradi:** Sentinel-2 sun'iy yo'ldoshidan haqiqiy NDVI
- **Aniqlik:** 10 metr/piksel, 5 kunlik yangilanish
- **Qamrov:** Global
- **Narxi:** Bepul (kuniga 100 so'rov)
- **Texnik:** REST API, polygon asosida oylik o'rtacha

### 5.2 Open-Meteo ERA5 (ECMWF)
- **Nima beradi:** 12 oylik kunlik ob-havo ma'lumoti
- **O'zgaruvchilar:** Harorat, yog'in, ET, radiatsiya, shamol, namlik
- **Tuproq sensori:** 4 qatlamda namlik va 3 chuqurlikda harorat
- **Qamrov:** Global, 9 km tarmog'i
- **Narxi:** To'liq bepul, ro'yxat talab emas
- **Kechikish:** 5 kun (ERA5 qayta ishlash vaqti)

### 5.3 SoilGrids ISRIC v2.0
- **Nima beradi:** Global tuproq xususiyatlar xaritasi
- **O'zgaruvchilar:** pH, organik uglerod, loy, qum, azot, zichlik
- **Chuqurliklar:** 0–5, 5–15, 15–30 sm qatlamlari
- **Aniqlik:** 250 metr/piksel
- **Manba:** Dunyo bo'yicha 230,000+ laboratoriya namunasi
- **Narxi:** To'liq bepul, ro'yxat talab emas
- **Cheklov:** Shahar hududlari uchun ma'lumot yo'q (beton/asfalt)

### 5.4 Groq — LLaMA 3.3 70B
- **Nima beradi:** Barcha ma'lumotlar asosida o'zbek tilida agronomik tahlil
- **Kontekst:** NDVI, ob-havo, tuproq kimyosi, shamol, namlik
- **Tezlik:** ~1–2 soniya
- **Narxi:** Bepul tier mavjud

---

## 6. TEXNIK STEK

| Komponent | Texnologiya | Versiya |
|-----------|-------------|---------|
| Backend freymvork | Django | 4.2.13 |
| REST API | Django REST Framework | 3.15.2 |
| HTTP mijoz | httpx | 0.27.0 |
| AI SDK | Groq Python | 0.11.0 |
| Ma'lumotlar bazasi | SQLite | — |
| Frontend xarita | Leaflet.js | 1.9.4 |
| Grafiklar | Chart.js | 4.4.0 |
| Shrift | Space Grotesk + JetBrains Mono | — |
| CORS | django-cors-headers | 4.3.1 |
| Muhit | python-dotenv | 1.0.1 |

---

## 7. MA'LUMOTLAR MODELI

```
AnalysisResult
├── id                  — Birlamchi kalit
├── created_at          — Yaratilgan vaqt (avtomatik)
├── name                — Tahlil nomi (ixtiyoriy)
├── center_lat/lng      — Markaz koordinatasi
├── area_ha             — Maydon (gektar)
├── coordinates         — Polygon nuqtalari (JSON)
│
├── ndvi_current        — So'nggi NDVI qiymati
├── ndvi_change         — 12 oylik NDVI o'zgarishi
├── ndvi_monthly        — Oylik NDVI/EVI/manba ro'yxati (JSON)
├── drought_index       — Quruqchilik indeksi (-3..+3)
├── ndwi_current        — So'nggi NDWI (suv indeksi)
│
├── soil_data           — Open-Meteo tuproq sensori (JSON)
├── soil_properties     — SoilGrids kimyosi: pH, loy, qum... (JSON)
├── weather_data        — 12 oylik ob-havo ma'lumoti (JSON)
└── ai_analysis         — Groq AI tahlil matni (JSON)
```

---

## 8. API ENDPOINTLAR

### POST /api/satellite/analyze/
**So'rov:**
```json
{
  "coordinates": [{"lat": 41.29, "lng": 69.24}, ...],
  "area_ha": 5.2,
  "save": false,
  "name": "Mening dala"
}
```

**Javob:**
```json
{
  "location":  { "lat": 41.29, "lng": 69.24, "area_ha": 5.2 },
  "ndvi": {
    "current": 0.411,
    "change": 0.082,
    "drought_index": 0.39,
    "ndwi_current": null,
    "monthly": [
      { "month": "2025-05", "ndvi": 0.25, "evi": 0.22,
        "temp": 22.4, "precip": 28.4, "wind": 6.1,
        "humidity": 52.7, "ndvi_source": "sentinel-2" }
    ]
  },
  "soil": {
    "surface_temp": 28.5,
    "moisture_0_1cm": 42.3,
    "properties": {
      "ph": 7.57, "ph_label": "Ishqoriy",
      "texture_label": "Lyoss",
      "clay_pct": 3.1, "sand_pct": 2.4, "silt_pct": 94.5,
      "nitrogen_cg_kg": 1.64
    }
  },
  "weather": {
    "annual_precip": 380.2,
    "avg_temp": 15.3,
    "avg_wind": 5.8,
    "avg_humidity": 52.1,
    "monthly": [...]
  },
  "analysis": {
    "osimlik_holati": "O'rtacha",
    "tuproq_tahlili": "...",
    "tavsiya_ekinlar": ["Bug'doy", "Arpa", "Kartoshka", "Qovun"],
    "xulosa": "..."
  },
  "source": "Sentinel-2 NDVI (12/13 oy) + SoilGrids + Open-Meteo ERA5 + Groq LLaMA"
}
```

### GET /api/satellite/history/
Barcha saqlangan tahlillar ro'yxati (oxirgi 30 ta).

### GET /api/satellite/history/{id}/
Bitta tahlilning to'liq ma'lumoti.

### DELETE /api/satellite/history/{id}/
Tahlilni o'chirish.

---

## 9. FOYDALANISH STSENARIYSI

```
1. Fermer/agronom saytni ochadi
2. Xaritada o'z dalasining chegarasini polygon bilan belgilaydi
3. "Tahlil qilish" tugmasini bosadi
4. Tizim ~15–30 soniya ichida:
   - AgroMonitoring dan 12 oy NDVI ma'lumotini oladi
   - Open-Meteo dan ob-havo va tuproq sensorini oladi
   - SoilGrids dan tuproq kimyosini oladi
   - Groq AI ga barchasini yuboradi va tavsiya oladi
5. Natijalar 4 bo'limda ko'rsatiladi:
   NDVI tab   → NDVI grafiği, quruqchilik indeksi
   Tuproq tab → Namlik, harorat, pH, tekstura
   Ob-havo tab → 12 oylik harorat/yog'in/shamol grafigi
   AI tab     → Ekin tavsiyasi, maslahatlat, xavflar, xulosa
6. "Saqlash" tugmasi bilan natijani saqlash
7. Tarixdan saqlangan tahlilni qayta yuklash imkoni
```

---

## 10. XAVFSIZLIK VA CHEKLOVLAR

| Parametr | Qiymat |
|----------|--------|
| Ma'lumotlar bazasi | SQLite (lokal fayl) |
| Autentifikatsiya | Yo'q (ochiq platforma) |
| CORS | Barcha domenlar uchun ochiq |
| AgroMonitoring limit | 100 so'rov/kun (bepul tier) |
| SoilGrids limit | Cheklov yo'q |
| Open-Meteo limit | Cheklov yo'q |
| Groq limit | Bepul tier (daqiqada 30 so'rov) |

---

## 11. KELAJAK RIVOJLANISH YO'NALISHLARI

1. **NDWI (suv stresss indeksi)** — Sentinel Hub CDSE orqali real suv indeksi
2. **Avtomatik xabarnoma** — NDVI keskin tushganda SMS/email
3. **Taqqoslash funksiyasi** — Ikki davrni yonma-yon ko'rsatish
4. **Ko'p foydalanuvchi** — JWT autentifikatsiya, shaxsiy tahlil tarixi
5. **Mobil ilova** — Progressive Web App (PWA)
6. **Prognoz modeli** — ML asosida 30 kunlik o'simlik prognozi
7. **PostgreSQL** — Katta ma'lumot hajmi uchun migratsiya
8. **Ekspot** — PDF hisobot generatsiyasi

---

## 12. LOYIHA PAPKALARI TUZILMASI

```
terrasat_django/
├── config/
│   └── settings.py          — Django sozlamalari, API kalitlar
├── satellite/
│   ├── models.py             — AnalysisResult modeli
│   ├── views.py              — API endpointlar
│   ├── serializers.py        — JSON serializatsiya
│   ├── urls.py               — URL marshrutlash
│   └── services/
│       ├── agro_ndvi.py      — AgroMonitoring Sentinel-2 NDVI
│       ├── meteo.py          — Open-Meteo ERA5 ob-havo
│       ├── soil_grids.py     — SoilGrids tuproq kimyosi
│       ├── ndvi.py           — NDVI/EVI hisoblash va boyitish
│       ├── ai_service.py     — Groq LLaMA AI tahlil
│       └── satellite_ndvi.py — CDSE zaxira (Copernicus)
├── templates/
│   └── index.html            — To'liq frontend (1100+ qator)
├── .env                      — API kalitlar (gitga kirmaydi)
└── db.sqlite3                — Ma'lumotlar bazasi
```

---

*TerraSat — "Yerga qarang, osmonga ishoning"*  
*Barcha ma'lumotlar haqiqiy yer usti va kosmik o'lchovlarga asoslangan.*

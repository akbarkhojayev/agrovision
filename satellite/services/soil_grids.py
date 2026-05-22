"""
Tuproq tahlili — ikki manba:
  1. SoilGrids ISRIC v2.0  — pH, texture, azot, CEC, organik uglerod
     (ketma-ket so'rovlar, 15s timeout; kesh 12 soat)
  2. NASA POWER            — ko'p yillik o'rtacha tuproq namligi profili (ishonchli)

SoilGrids d_factor jadval (raw/d_factor = actual):
  phh2o    /10  → pH
  clay     /10  → %
  sand     /10  → %
  silt     /10  → %
  nitrogen /100 → g/kg
  bdod     /100 → kg/dm³  (bulk density)
  cec      /10  → cmol(c)/kg
  soc      /10  → g/kg    (organik uglerod miqdori)
  Note: ocs (t/ha stocks) va ece (dS/m) ISRIC da ishonchsiz — ishlatilmaydi
"""
import time
import httpx
from concurrent.futures import ThreadPoolExecutor

_SG_URL   = "https://rest.isric.org/soilgrids/v2.0/properties/query"
_NASA_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"
_DEPTHS   = ["0-5cm", "5-15cm", "15-30cm", "30-60cm"]

_PROP_META = {
    "phh2o":    10.0,
    "clay":     10.0,
    "sand":     10.0,
    "silt":     10.0,
    "nitrogen": 100.0,
    "bdod":     100.0,
    "cec":      10.0,
    "soc":      10.0,
}

_PROP_GROUPS = [
    ["phh2o", "clay", "sand"],
    ["silt",  "nitrogen", "bdod"],
    ["cec",   "soc"],
]

# Kesh: (lat2, lng2) → (timestamp, raw_dict)
_SG_CACHE: dict[tuple, tuple] = {}
_CACHE_TTL = 12 * 3600


# ── SoilGrids so'rovlari ──────────────────────────────────────────────────────

def _sg_request(lat: float, lng: float, props: list) -> dict:
    params = (
        [("lon", round(lng, 6)), ("lat", round(lat, 6))]
        + [("property", p) for p in props]
        + [("depth",    d) for d in _DEPTHS]
        + [("value", "mean")]
    )
    try:
        resp = httpx.get(_SG_URL, params=params, timeout=15)
        if resp.status_code != 200:
            return {}
        result = {}
        for layer in resp.json()["properties"]["layers"]:
            name     = layer["name"]
            d_factor = _PROP_META.get(name, 1.0)
            vals = {}
            for depth in layer.get("depths", []):
                raw = depth.get("values", {}).get("mean")
                if raw is not None:
                    vals[depth["label"]] = raw / d_factor
            if vals:
                result[name] = vals
        return result
    except Exception:
        return {}


def _fetch_soilgrids(lat: float, lng: float) -> dict:
    key = (round(lat, 2), round(lng, 2))
    cached = _SG_CACHE.get(key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    # Sequential with gap — ISRIC rate-limits concurrent requests
    combined: dict = {}
    for grp in _PROP_GROUPS:
        result = _sg_request(lat, lng, grp)
        combined.update(result)
        if result:
            time.sleep(0.3)

    if combined:
        _SG_CACHE[key] = (time.time(), combined)
    return combined


def _avg(raw: dict, prop: str) -> float | None:
    vals = [v for v in raw.get(prop, {}).values() if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


# ── NASA POWER ────────────────────────────────────────────────────────────────

def _fetch_nasa_soil(lat: float, lng: float) -> dict:
    try:
        resp = httpx.get(_NASA_URL, params={
            "parameters": "GWETTOP,GWETROOT,GWETPROF",
            "community":  "AG",
            "longitude":  round(lng, 4),
            "latitude":   round(lat, 4),
            "format":     "JSON",
        }, timeout=10)
        if resp.status_code != 200:
            return {}
        ann = {}
        for key, monthly in resp.json().get("properties", {}).get("parameter", {}).items():
            val = monthly.get("ANN")
            if val is not None and float(val) != -999.0:
                ann[key] = round(float(val), 3)
        return ann
    except Exception:
        return {}


# ── Labellar (to'g'ri birliklar bilan) ───────────────────────────────────────

def _ph_label(v):
    if v is None: return None
    if v < 4.5:   return "Juda kislotali — aksariyat ekinlar o'smaydi"
    if v < 5.5:   return "Kislotali — kislota sevuvchi ekinlarga mos"
    if v < 6.5:   return "Kuchsiz kislotali — ko'p ekinlar uchun qulay"
    if v < 7.0:   return "Neytralga yaqin — ideal holat"
    if v < 7.5:   return "Neytral — ko'pchilik ekinlar uchun ideal"
    if v < 8.0:   return "Kuchsiz ishqoriy — aksariyat ekinlar o'sadi"
    if v < 8.5:   return "Ishqoriy — ohak yoki gips bilan isloh tavsiya etiladi"
    return "Juda ishqoriy — faqat ba'zi ekinlar chidaydi"


def _texture_label(clay_pct, sand_pct):
    if clay_pct is None or sand_pct is None: return None
    silt_pct = max(0.0, 100 - clay_pct - sand_pct)
    if clay_pct >= 40:   return "Og'ir loysumon — suv sekin o'tadi, shudgor qiyin"
    if clay_pct >= 27:   return "Loysumon — nam yaxshi ushlanadi, ko'p ekin uchun yaxshi"
    if clay_pct >= 18 and sand_pct < 65:
                         return "O'rta qumoqli-loy — yaxshi suvdan tozalanadi"
    if sand_pct >= 70:   return "Qumloq — suv tez o'tib ketadi, ko'p sug'orish kerak"
    if sand_pct >= 50:   return "Qumoq — o'rtacha nam ushlanadi"
    if silt_pct >= 50:   return "Lyoss (changsimon) — yaxshi unumdor, lekin eroziyaga moyil"
    return "Aralash (qumoq-loysumon)"


def _nitrogen_label(g_kg):
    # nitrogen: g/kg birligida
    if g_kg is None: return None
    if g_kg >= 2.0:  return f"{g_kg:.2f} g/kg — Juda yuqori, qo'shimcha azot shart emas"
    if g_kg >= 1.0:  return f"{g_kg:.2f} g/kg — Yuqori, ozgina azot o'g'it yetarli"
    if g_kg >= 0.5:  return f"{g_kg:.2f} g/kg — O'rtacha, azotli o'g'it tavsiya etiladi"
    if g_kg >= 0.2:  return f"{g_kg:.2f} g/kg — Kam, azotli o'g'it (karbamid) zarur"
    return f"{g_kg:.2f} g/kg — Juda kam, tezkor azotli o'g'it bering"


def _cec_label(cmol_kg):
    # cec: cmol(c)/kg birligida
    if cmol_kg is None: return None
    if cmol_kg >= 30: return f"{cmol_kg:.1f} — Yuqori, oziqlanish yaxshi ushlanadi"
    if cmol_kg >= 15: return f"{cmol_kg:.1f} — O'rtacha, yaxshi holat"
    if cmol_kg >= 7:  return f"{cmol_kg:.1f} — Kichik, o'g'it tez yuviladi"
    return f"{cmol_kg:.1f} — Juda kichik, tuproq oziqni ushlab turolmaydi"


def _soc_label(g_kg):
    # soc: g/kg birligida (organik uglerod miqdori)
    if g_kg is None: return None
    if g_kg >= 30:  return f"{g_kg:.1f} g/kg — Juda yuqori, tuproq juda unumdor"
    if g_kg >= 15:  return f"{g_kg:.1f} g/kg — Yuqori, tuproq unumdor, go'ng shart emas"
    if g_kg >= 5:   return f"{g_kg:.1f} g/kg — O'rtacha, go'ng yoki kompost tavsiya etiladi"
    if g_kg >= 1:   return f"{g_kg:.1f} g/kg — Kuchsiz, go'ng shart"
    return f"{g_kg:.1f} g/kg — Juda kam, tuproq organik moddaga muhtoj"


def _nasa_wetness_label(v):
    if v is None: return None
    pct = round(v * 100)
    if v >= 0.7: return f"{pct}% — tuproq juda nam"
    if v >= 0.4: return f"{pct}% — tuproq yaxshi namlangan"
    if v >= 0.2: return f"{pct}% — tuproq o'rtacha nam"
    return f"{pct}% — tuproq quruq"


# ── Asosiy funksiya ───────────────────────────────────────────────────────────

def fetch_soil_properties(lat: float, lng: float) -> dict:
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_sg   = ex.submit(_fetch_soilgrids, lat, lng)
        f_nasa = ex.submit(_fetch_nasa_soil, lat, lng)
        sg   = f_sg.result()
        nasa = f_nasa.result()

    ph       = _avg(sg, "phh2o")      # pH
    clay_pct = _avg(sg, "clay")       # %
    sand_pct = _avg(sg, "sand")       # %
    silt_pct = _avg(sg, "silt")       # %
    nitrogen = _avg(sg, "nitrogen")   # g/kg
    bdod     = _avg(sg, "bdod")       # kg/dm³
    cec      = _avg(sg, "cec")        # cmol(c)/kg
    soc      = _avg(sg, "soc")        # g/kg

    # Silt ni clay+sand dan hisoblash (agar API qaytarmagan bo'lsa)
    if clay_pct and sand_pct and silt_pct is None:
        silt_pct = round(max(0.0, 100 - clay_pct - sand_pct), 1)

    return {
        # pH
        "ph":             ph,
        "ph_label":       _ph_label(ph),

        # Tarkib
        "clay_pct":       clay_pct,
        "sand_pct":       sand_pct,
        "silt_pct":       silt_pct,
        "texture":        _texture_label(clay_pct, sand_pct),

        # Kimyo
        "nitrogen_g_kg":  nitrogen,
        "nitrogen_label": _nitrogen_label(nitrogen),

        "cec_cmol_kg":    cec,
        "cec_label":      _cec_label(cec),

        "soc_g_kg":       soc,
        "soc_label":      _soc_label(soc),

        "bulk_density":   bdod,

        # NASA POWER ko'p yillik namligi
        "gwet_top":         nasa.get("GWETTOP"),
        "gwet_root":        nasa.get("GWETROOT"),
        "gwet_prof":        nasa.get("GWETPROF"),
        "gwet_top_label":   _nasa_wetness_label(nasa.get("GWETTOP")),
        "gwet_root_label":  _nasa_wetness_label(nasa.get("GWETROOT")),

        "soilgrids_ok":   bool(sg),
        "nasa_ok":        bool(nasa),

        # Orqaga moslik (eski kod uchun)
        "ph_h2o":   ph,
        "clay":     clay_pct,
        "sand":     sand_pct,
        "soc":      soc,
        "nitrogen": nitrogen,
    }

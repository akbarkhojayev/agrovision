"""
O'zbekiston suv manbalari — oflayn shapefile qidiruvi.
uzbek_area/gis_osm_waterways_free_1.shp  (daryolar, kanallar, ariqlar)
uzbek_area/gis_osm_water_a_free_1.shp    (ko'llar, suv omborlari, hovuzlar)

API kerak emas, internet kerak emas — tez va ishonchli.
"""
import math
from pathlib import Path

try:
    import shapefile as _sf_mod
    _SHP_OK = True
except ImportError:
    _SHP_OK = False

BASE_DIR   = Path(__file__).resolve().parent.parent.parent
UZBEK_AREA = BASE_DIR / "uzbek_area"

# fclass → o'zbek tiliga
TYPE_LABELS = {
    "river":      "Daryo",
    "canal":      "Kanal",
    "stream":     "Ariq / Soy",
    "drain":      "Zovur",
    "ditch":      "Ariq",
    "water":      "Ko'l / Hovuz",
    "reservoir":  "Suv ombori",
    "riverbank":  "Daryo qirg'og'i",
    "wetland":    "Botqoq",
    "dock":       "Port / Liman",
    "glacier":    "Muzlik",
    "lake":       "Ko'l",
    "pond":       "Hovuz",
}

IRRIGATION_SUITABLE = {
    "river", "canal", "stream", "water", "reservoir", "riverbank", "lake", "pond",
}

# Kesh — bir marta yuklanadi
_cache: list[dict] | None = None


# ── Geometriya yordamchilari ──────────────────────────────────────────────────

def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _direction(lat1: float, lng1: float, lat2: float, lng2: float) -> str:
    angle = math.degrees(math.atan2(lng2 - lng1, lat2 - lat1)) % 360
    dirs = [
        (22.5,  "Shimol"),
        (67.5,  "Shimoli-Sharq"),
        (112.5, "Sharq"),
        (157.5, "Janubi-Sharq"),
        (202.5, "Janub"),
        (247.5, "Janubi-G'arb"),
        (292.5, "G'arb"),
        (337.5, "Shimoli-G'arb"),
        (360.0, "Shimol"),
    ]
    for limit, label in dirs:
        if angle < limit:
            return label
    return "Shimol"


def _dist_text(km: float) -> str:
    if km < 0.5:
        return f"{int(km * 1000)} metr"
    return f"{km:.1f} km"


def _min_dist_to_pts(lat: float, lng: float, pts: list) -> tuple[float, float, float]:
    """Nuqtalar ro'yxatidan (lng,lat) eng yaqinini topadi. (dist_km, clat, clng) qaytaradi."""
    best = float("inf")
    clat = clng = 0.0
    for x, y in pts:  # x=lng, y=lat
        d = _haversine(lat, lng, y, x)
        if d < best:
            best = d
            clat, clng = y, x
    return best, clat, clng


# ── Shapefile keshi ───────────────────────────────────────────────────────────

def _load_cache() -> list[dict]:
    global _cache
    if _cache is not None:
        return _cache
    if not _SHP_OK:
        _cache = []
        return _cache

    features: list[dict] = []

    # 1. Suv yo'llari — chiziqlar
    ww_path = UZBEK_AREA / "gis_osm_waterways_free_1.shp"
    if ww_path.exists():
        sf   = _sf_mod.Reader(str(ww_path))
        flds = [f[0] for f in sf.fields[1:]]
        for sr in sf.iterShapeRecords():
            shp = sr.shape
            rec = sr.record
            r      = dict(zip(flds, rec))
            fclass = r.get("fclass", "")
            if fclass not in TYPE_LABELS:
                continue
            pts = shp.points
            if not pts:
                continue
            # Har 10-chi nuqtani olamiz (tez va yetarlicha aniq)
            step    = max(1, len(pts) // 20)
            sampled = pts[::step]
            if pts[-1] not in sampled:
                sampled.append(pts[-1])
            bbox = shp.bbox  # [xmin, ymin, xmax, ymax]
            features.append({
                "name":   r.get("name") or "",
                "fclass": fclass,
                "pts":    sampled,
                "bbox":   bbox,
                "area":   False,
            })

    # 2. Suv hududlari — poligonlar
    wa_path = UZBEK_AREA / "gis_osm_water_a_free_1.shp"
    if wa_path.exists():
        sf2   = _sf_mod.Reader(str(wa_path))
        flds2 = [f[0] for f in sf2.fields[1:]]
        for sr in sf2.iterShapeRecords():
            shp = sr.shape
            rec = sr.record
            r      = dict(zip(flds2, rec))
            fclass = r.get("fclass") or "water"
            if fclass not in TYPE_LABELS:
                continue
            bbox = shp.bbox
            # Markazni bbox dan hisoblaymiz
            cx = (bbox[0] + bbox[2]) / 2  # lng
            cy = (bbox[1] + bbox[3]) / 2  # lat
            features.append({
                "name":   r.get("name") or "",
                "fclass": fclass,
                "pts":    [(cx, cy)],
                "bbox":   bbox,
                "area":   True,
            })

    _cache = features
    return _cache


# ── Asosiy qidiruv ────────────────────────────────────────────────────────────

def fetch_water_sources(lat: float, lng: float, radius_km: float = 10.0) -> list[dict]:
    """
    Berilgan koordinatalar atrofida radius_km ichidagi suv manbalarini qaytaradi.
    O'zbekiston shapefile dan oflayn qidiradi — hech qanday API kerak emas.
    """
    features = _load_cache()
    if not features:
        return []

    # Bbox filtri uchun daraja ichida masofa
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / (111.0 * math.cos(math.radians(lat)))

    lat_min = lat - lat_delta
    lat_max = lat + lat_delta
    lng_min = lng - lng_delta
    lng_max = lng + lng_delta

    results:  list[dict] = []
    name_map: dict       = {}   # (name_lower, fclass) → eng yaqin yozuv

    for feat in features:
        bx = feat["bbox"]  # [xmin, ymin, xmax, ymax] = [lng_min, lat_min, lng_max, lat_max]
        # Bbox kesishmasini tekshirish
        if bx[2] < lng_min or bx[0] > lng_max:
            continue
        if bx[3] < lat_min or bx[1] > lat_max:
            continue

        dist, clat, clng = _min_dist_to_pts(lat, lng, feat["pts"])
        if dist > radius_km:
            continue

        fclass = feat["fclass"]
        name   = feat["name"]
        label  = TYPE_LABELS.get(fclass, "Suv manbai")

        # Bir xil nom va turning eng yaqin segmentini saqlaymiz
        key = (name.lower() if name else f"__noname_{fclass}_{round(clat,2)}_{round(clng,2)}",
               fclass)
        if key in name_map:
            if dist < name_map[key]["distance_km"]:
                name_map[key].update({
                    "distance_km":   round(dist, 2),
                    "distance_text": _dist_text(dist),
                    "direction":     _direction(lat, lng, clat, clng),
                    "lat":           round(clat, 6),
                    "lng":           round(clng, 6),
                })
            continue

        entry = {
            "name":          name or label,
            "type":          fclass,
            "type_uz":       label,
            "distance_km":   round(dist, 2),
            "distance_text": _dist_text(dist),
            "direction":     _direction(lat, lng, clat, clng),
            "irrigation_ok": fclass in IRRIGATION_SUITABLE,
            "lat":           round(clat, 6),
            "lng":           round(clng, 6),
        }
        name_map[key] = entry
        results.append(entry)

    results.sort(key=lambda x: x["distance_km"])
    return results[:15]


def summarize(sources: list[dict]) -> dict:
    if not sources:
        return {
            "closest_name":      None,
            "closest_dist_km":   None,
            "closest_dist_text": None,
            "irrigation_source": None,
            "total_found":       0,
            "plain_text": (
                "10 km radius ichida suv manbai topilmadi. "
                "Yomg'ir suvi yoki chuqur quduqdan foydalanishingiz kerak bo'ladi."
            ),
        }

    closest = sources[0]
    irr     = next((s for s in sources if s["irrigation_ok"]), None)

    parts = [
        f"Eng yaqin suv manbai: {closest['name']} — "
        f"{closest['distance_text']} {closest['direction']} tomonda."
    ]
    if irr:
        if irr["distance_km"] <= 2:
            parts.append(
                f"{irr['type_uz']} ({irr['name']}) {irr['distance_text']} uzoqlikda — "
                "sug'orish uchun qulay, kanal qazish mumkin."
            )
        elif irr["distance_km"] <= 5:
            parts.append(
                f"Eng yaqin sug'orish manbai {irr['name']} — {irr['distance_text']} uzoqda. "
                "Nasos bilan suv olish mumkin."
            )
        else:
            parts.append(
                f"Sug'orish uchun eng yaqin manba {irr['distance_text']} uzoqda. "
                "Yomg'ir suvi yig'ish yoki quduq qazishni ko'rib chiqing."
            )

    return {
        "closest_name":      closest["name"],
        "closest_type_uz":   closest["type_uz"],
        "closest_dist_km":   closest["distance_km"],
        "closest_dist_text": closest["distance_text"],
        "closest_direction": closest["direction"],
        "irrigation_source": irr,
        "total_found":       len(sources),
        "plain_text":        " ".join(parts),
    }

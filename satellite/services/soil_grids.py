"""SoilGrids ISRIC v2.0 — haqiqiy tuproq xususiyatlari (kalit kerak emas)."""
import httpx

_URL    = "https://rest.isric.org/soilgrids/v2.0/properties/query"
_PROPS  = "phh2o,ocd,clay,sand,nitrogen,bdod"
_DEPTHS = "0-5cm,5-15cm,15-30cm"


def fetch_soil_properties(lat: float, lng: float) -> dict:
    """
    SoilGrids dan haqiqiy tuproq xususiyatlarini qaytaradi.
    pH, organik uglerod, loy %, qum %, azot, zichlik.
    Xato bo'lsa bo'sh dict qaytaradi.
    """
    try:
        params = (
            [("lon", round(lng, 6)), ("lat", round(lat, 6))]
            + [("property", p) for p in _PROPS.split(",")]
            + [("depth",    d) for d in _DEPTHS.split(",")]
            + [("value", "mean")]
        )
        resp = httpx.get(_URL, params=params, timeout=20)
        resp.raise_for_status()
        layers = resp.json()["properties"]["layers"]
    except Exception:
        return {}

    raw: dict[str, dict] = {}
    for layer in layers:
        name     = layer["name"]
        d_factor = layer.get("unit_measure", {}).get("d_factor") or 1
        vals = {}
        for depth_entry in layer.get("depths", []):
            mean_val = depth_entry.get("values", {}).get("mean")
            if mean_val is not None:
                vals[depth_entry["label"]] = round(mean_val / d_factor, 2)
        if vals:
            raw[name] = vals

    return _summarize(raw)


def _avg(raw: dict, prop: str) -> float | None:
    vals = [v for v in raw.get(prop, {}).values() if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _summarize(raw: dict) -> dict:
    ph   = _avg(raw, "phh2o")
    clay = _avg(raw, "clay")    # g/kg
    sand = _avg(raw, "sand")    # g/kg
    silt = None
    if clay is not None and sand is not None:
        silt = round(max(0.0, 1000 - clay - sand) / 10, 1)  # %

    return {
        "ph":                   ph,
        "ph_label":             _ph_label(ph),
        "organic_carbon_kg_m3": _avg(raw, "ocd"),
        "clay_g_kg":            clay,
        "clay_pct":             round(clay / 10, 1) if clay else None,
        "sand_g_kg":            sand,
        "sand_pct":             round(sand / 10, 1) if sand else None,
        "silt_pct":             silt,
        "nitrogen_cg_kg":       _avg(raw, "nitrogen"),
        "bulk_density_cg_cm3":  _avg(raw, "bdod"),
        "texture_label":        _texture_label(clay, sand),
    }


def _ph_label(ph: float | None) -> str:
    if ph is None:  return "Noma'lum"
    if ph < 5.5:    return "Juda kislotali"
    if ph < 6.5:    return "Kislotali"
    if ph < 7.0:    return "Neytralga yaqin"
    if ph < 7.5:    return "Neytral"
    if ph < 8.0:    return "Ishqoriy"
    return "Juda ishqoriy"


def _texture_label(clay: float | None, sand: float | None) -> str:
    if clay is None or sand is None:
        return "Noma'lum"
    cp = clay / 10  # %
    sp = sand / 10  # %
    if cp >= 40:              return "Og'ir loy"
    if cp >= 27:              return "Loy"
    if cp >= 18 and sp < 65: return "Qumoq-loy"
    if sp >= 70:              return "Qumloq"
    if sp >= 50:              return "Qumoq"
    return "Lyoss"

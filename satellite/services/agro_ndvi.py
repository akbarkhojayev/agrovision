import httpx
from datetime import datetime, timedelta

_BASE = "http://api.agromonitoring.com/agro/1.0"


def _small_polygon(lat: float, lng: float) -> dict:
    d = 0.005  # ~500m radius ≈ 1 km²
    return {
        "name": f"ts_{lat:.4f}_{lng:.4f}",
        "geo_json": {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [lng-d, lat-d], [lng+d, lat-d],
                    [lng+d, lat+d], [lng-d, lat+d],
                    [lng-d, lat-d],
                ]],
            },
        },
    }


def fetch_indices(lat: float, lng: float, api_key: str) -> dict:
    p        = {"appid": api_key}
    end_ts   = int(datetime.utcnow().timestamp())
    start_ts = int((datetime.utcnow() - timedelta(days=365)).timestamp())

    with httpx.Client(timeout=20) as client:
        r = client.post(f"{_BASE}/polygons", params=p,
                        json=_small_polygon(lat, lng))
        r.raise_for_status()
        poly_id = r.json()["id"]

    try:
        r = httpx.get(
            f"{_BASE}/ndvi/history",
            params={"polyid": poly_id, "appid": api_key,
                    "start": start_ts, "end": end_ts},
            timeout=90,
        )
        r.raise_for_status()
        raw = r.json()
    finally:
        try:
            httpx.delete(f"{_BASE}/polygons/{poly_id}", params=p, timeout=10)
        except Exception:
            pass

    return _group_by_month(raw)


def _group_by_month(raw: list) -> dict:
    acc: dict[str, list[float]] = {}
    for entry in raw:
        mean_val = entry.get("data", {}).get("mean")
        if mean_val is None:
            continue
        fv = float(mean_val)
        if fv != fv:  # NaN tekshiruvi
            continue
        key = datetime.utcfromtimestamp(entry["dt"]).strftime("%Y-%m")
        acc.setdefault(key, []).append(fv)

    return {
        month: {
            "ndvi": round(sum(vals) / len(vals), 3),
            "evi":  round(sum(vals) / len(vals) * 0.87, 3),
            "ndwi": None,
        }
        for month, vals in acc.items()
    }


def fetch_monthly_ndvi(lat: float, lng: float, api_key: str) -> dict:
    return fetch_indices(lat, lng, api_key)

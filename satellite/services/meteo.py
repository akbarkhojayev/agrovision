"""Open-Meteo ERA5 API: tarixiy ob-havo va joriy tuproq ma'lumotlari."""
import httpx
from datetime import datetime, timedelta
from statistics import mean


def fetch_data(lat: float, lng: float) -> tuple[dict, dict]:
    end_dt   = datetime.now() - timedelta(days=5)   # ERA5 ~5 kunlik kechikish
    start_dt = end_dt - timedelta(days=365)

    with httpx.Client(timeout=40) as client:
        archive = client.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude":   lat,
                "longitude":  lng,
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date":   end_dt.strftime("%Y-%m-%d"),
                "daily": (
                    "temperature_2m_mean,precipitation_sum,"
                    "et0_fao_evapotranspiration,shortwave_radiation_sum,"
                    "wind_speed_10m_mean,relative_humidity_2m_mean"
                ),
                "timezone": "Asia/Tashkent",
            }
        ).json()

        soil = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":  lat,
                "longitude": lng,
                "hourly": (
                    "soil_temperature_0cm,soil_temperature_6cm,soil_temperature_18cm,"
                    "soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,"
                    "soil_moisture_3_to_9cm,soil_moisture_9_to_27cm,"
                    "relative_humidity_2m,wind_speed_10m"
                ),
                "forecast_days": 1,
                "timezone": "Asia/Tashkent",
            }
        ).json()

    return archive, soil


def process_monthly(archive: dict) -> list[dict]:
    """Kunlik ERA5 ma'lumotlarni oylar bo'yicha guruhlaydi."""
    daily   = archive.get("daily", {})
    times   = daily.get("time", [])
    temps   = daily.get("temperature_2m_mean", [])
    precips = daily.get("precipitation_sum", [])
    ets     = daily.get("et0_fao_evapotranspiration", [])
    rads    = daily.get("shortwave_radiation_sum", [])
    winds   = daily.get("wind_speed_10m_mean", [])
    humids  = daily.get("relative_humidity_2m_mean", [])

    raw: dict = {}
    for i, ds in enumerate(times):
        mk = ds[:7]
        if mk not in raw:
            raw[mk] = {"t": [], "p": [], "e": [], "r": [], "w": [], "h": []}
        if i < len(temps)   and temps[i]   is not None: raw[mk]["t"].append(temps[i])
        if i < len(precips) and precips[i] is not None: raw[mk]["p"].append(precips[i])
        if i < len(ets)     and ets[i]     is not None: raw[mk]["e"].append(ets[i])
        if i < len(rads)    and rads[i]    is not None: raw[mk]["r"].append(rads[i])
        if i < len(winds)   and winds[i]   is not None: raw[mk]["w"].append(winds[i])
        if i < len(humids)  and humids[i]  is not None: raw[mk]["h"].append(humids[i])

    result = []
    for mk in sorted(raw.keys()):
        m = raw[mk]
        result.append({
            "month":     mk,
            "temp":      round(mean(m["t"]), 1) if m["t"] else 0.0,
            "precip":    round(sum(m["p"]),  1) if m["p"] else 0.0,
            "et":        round(sum(m["e"]),  1) if m["e"] else 0.0,
            "radiation": round(mean(m["r"]), 1) if m["r"] else 0.0,
            "wind":      round(mean(m["w"]), 1) if m["w"] else 0.0,
            "humidity":  round(mean(m["h"]), 1) if m["h"] else 0.0,
        })
    return result


def extract_soil(soil_json: dict) -> dict:
    """Soatlik tuproq ma'lumotidan oxirgi qiymatlarni oladi."""
    h = soil_json.get("hourly", {})

    def last(lst):
        vals = [v for v in (lst or []) if v is not None]
        return round(vals[-1], 2) if vals else None

    def pct(lst):
        v = last(lst)
        return round(v * 100, 1) if v is not None else None

    return {
        "surface_temp":    last(h.get("soil_temperature_0cm")),
        "depth_6cm_temp":  last(h.get("soil_temperature_6cm")),
        "depth_18cm_temp": last(h.get("soil_temperature_18cm")),
        "moisture_0_1cm":  pct(h.get("soil_moisture_0_to_1cm")),
        "moisture_1_3cm":  pct(h.get("soil_moisture_1_to_3cm")),
        "moisture_3_9cm":  pct(h.get("soil_moisture_3_to_9cm")),
        "moisture_9_27cm": pct(h.get("soil_moisture_9_to_27cm")),
        "humidity":        round(last(h.get("relative_humidity_2m")) or 0, 1),
        "wind_speed":      round(last(h.get("wind_speed_10m")) or 0, 1),
    }

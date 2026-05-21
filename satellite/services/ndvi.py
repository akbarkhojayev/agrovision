"""NDVI, EVI va Qurg'oqchilik indeksi hisoblash."""
from statistics import mean, stdev


# Markaziy Osiyo iqlimiga moslashtirilgan oylik bazaviy NDVI
_SEASONAL = {
    1: 0.06, 2: 0.11, 3: 0.30, 4: 0.54, 5: 0.68, 6: 0.73,
    7: 0.70, 8: 0.64, 9: 0.50, 10: 0.33, 11: 0.16, 12: 0.06,
}


def estimate_ndvi(temp: float, precip: float, et: float, month: int) -> float:
    base  = _SEASONAL.get(month, 0.30)
    water = min(1.35, (precip * 0.75 + 5) / et) if et > 0.5 else 1.0
    if 14 <= temp <= 26:        t_k = 1.00
    elif temp < 0 or temp > 42: t_k = 0.25
    elif temp < 8 or temp > 35: t_k = 0.55
    else:                       t_k = 0.80
    return round(min(0.93, max(-0.05, base * water * t_k)), 3)


def estimate_evi(ndvi: float) -> float:
    """EVI ≈ NDVI * 0.87 (yashil hududlar uchun taxminiy)."""
    return round(max(-0.05, ndvi * 0.87), 3)


def drought_index(monthly: list[dict]) -> float:
    """
    Standartlashtirilgan yog'in-evapotranspiratsiya indeksi.
    Qiymat: -3 (juda quruq) ... +3 (juda nam).
    """
    deficits = [m["precip"] - m["et"] for m in monthly]
    if len(deficits) < 2:
        return 0.0
    avg = mean(deficits)
    std = stdev(deficits)
    if std == 0:
        return 0.0
    latest = deficits[-1]
    return round(max(-3.0, min(3.0, (latest - avg) / std)), 2)


def enrich_monthly(
    monthly: list[dict],
    real_ndvi: dict | None = None,
) -> tuple[list[dict], float]:
    """
    Har bir oyga NDVI, EVI qo'shadi; Drought Index qaytaradi.
    real_ndvi = {"2024-05": {"ndvi": 0.45, "evi": 0.39}, ...} bo'lsa,
    haqiqiy sun'iy yo'ldosh qiymatlari ishlatiladi; aks holda formula.
    """
    di = drought_index(monthly)
    for m in monthly:
        mn = int(m["month"][5:7])
        if real_ndvi and m["month"] in real_ndvi:
            rd               = real_ndvi[m["month"]]
            m["ndvi"]        = rd["ndvi"]
            m["evi"]         = rd["evi"]
            m["ndwi"]        = rd.get("ndwi")
            m["ndvi_source"] = "sentinel-2"
        else:
            ndvi             = estimate_ndvi(m["temp"], m["precip"], m["et"], mn)
            m["ndvi"]        = ndvi
            m["evi"]         = estimate_evi(ndvi)
            m["ndwi"]        = None
            m["ndvi_source"] = "formula"
    return monthly, di

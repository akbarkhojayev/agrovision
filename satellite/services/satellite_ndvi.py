import httpx
from datetime import datetime, timedelta

_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
_STATS_URL  = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

# SCL 2,4,5,6,7,11 — bulut/soya emas piksellar
_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{bands: ["B02", "B04", "B08", "SCL"]}],
    output: [
      {id: "ndvi", bands: 1, sampleType: "FLOAT32"},
      {id: "evi",  bands: 1, sampleType: "FLOAT32"},
      {id: "dataMask", bands: 1}
    ],
    mosaicking: "ORBIT"
  };
}
function evaluatePixel(samples) {
  const valid = samples.filter(s => [2, 4, 5, 6, 7, 11].includes(s.SCL));
  if (valid.length === 0) return {ndvi: [NaN], evi: [NaN], dataMask: [0]};
  const n = valid.length;
  const ndvi = valid.reduce((a, s) => a + (s.B08 - s.B04) / (s.B08 + s.B04 + 1e-10), 0) / n;
  const evi  = valid.reduce((a, s) =>
    a + 2.5 * (s.B08 - s.B04) / (s.B08 + 6*s.B04 - 7.5*s.B02 + 1 + 1e-10), 0) / n;
  return {ndvi: [ndvi], evi: [evi], dataMask: [1]};
}
"""


def get_token(username: str, password: str) -> str:
    resp = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "password",
            "username":   username,
            "password":   password,
            "client_id":  "cdse-public",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_monthly_ndvi(lat: float, lng: float, token: str) -> dict:

    end_dt   = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=365)
    delta    = 0.001

    payload = {
        "input": {
            "bounds": {
                "bbox": [lng - delta, lat - delta, lng + delta, lat + delta],
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"maxCloudCoverage": 100}}],
        },
        "aggregation": {
            "timeRange": {
                "from": start_dt.strftime("%Y-%m-%dT00:00:00Z"),
                "to":   end_dt.strftime("%Y-%m-%dT00:00:00Z"),
            },
            "aggregationInterval": {"of": "P1M"},
            "resx": 0.0001,
            "resy": 0.0001,
            "evalscript": _EVALSCRIPT,
        },
    }

    resp = httpx.post(
        _STATS_URL,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    resp.raise_for_status()

    result = {}
    for entry in resp.json().get("data", []):
        month_key = entry["interval"]["from"][:7]
        try:
            outputs  = entry.get("outputs", {})
            ndvi_val = outputs["ndvi"]["bands"]["B0"]["stats"]["mean"]
            evi_val  = outputs["evi"]["bands"]["B0"]["stats"]["mean"]
            if ndvi_val is not None and ndvi_val == ndvi_val:  # NaN tekshiruvi
                result[month_key] = {
                    "ndvi": round(float(ndvi_val), 3),
                    "evi":  round(float(evi_val), 3)
                    if (evi_val is not None and evi_val == evi_val)
                    else round(float(ndvi_val) * 0.87, 3),
                }
        except (KeyError, TypeError):
            pass

    return result

from statistics import mean

from django.conf import settings
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import AnalysisResult
from .serializers import AnalysisListSerializer, AnalysisDetailSerializer
from .services import meteo, ai_service, satellite_ndvi, agro_ndvi
from .services import soil_grids
from .services.ndvi import enrich_monthly


def _build_source(monthly: list[dict]) -> str:
    sat = sum(1 for m in monthly if m.get("ndvi_source") == "sentinel-2")
    if sat:
        return f"Sentinel-2 NDVI ({sat}/{len(monthly)} oy) + SoilGrids + Open-Meteo ERA5 + Groq LLaMA"
    return "Open-Meteo ERA5 (NDVI formula) + SoilGrids + Groq LLaMA"


class FrontendView(APIView):
    def get(self, request):
        return render(request, "index.html")


class SatelliteAnalyzeView(APIView):
    """POST /api/satellite/analyze/"""

    def post(self, request):
        coords  = request.data.get("coordinates", [])
        area_ha = request.data.get("area_ha")
        save    = request.data.get("save", False)
        name    = request.data.get("name", "").strip()

        if not coords:
            return Response({"error": "Koordinatalar kiritilmagan"}, status=400)

        lat = sum(c["lat"] for c in coords) / len(coords)
        lng = sum(c["lng"] for c in coords) / len(coords)

        try:
            archive, soil_json = meteo.fetch_data(lat, lng)
        except Exception as exc:
            return Response({"error": f"Open-Meteo xatosi: {exc}"}, status=502)

        monthly = meteo.process_monthly(archive)
        soil    = meteo.extract_soil(soil_json)

        # SoilGrids — tuproq kimyosi (meteo bilan bir vaqtda ishga tushirilgan edi,
        # lekin httpx sinxron bo'lgani uchun ketma-ket chaqiramiz)
        soil_props = soil_grids.fetch_soil_properties(lat, lng)
        if soil_props:
            soil["properties"] = soil_props

        # 1. AgroMonitoring — haqiqiy Sentinel-2 NDVI + EVI + NDWI
        real_ndvi = {}
        if getattr(settings, "AGRO_API_KEY", ""):
            try:
                real_ndvi = agro_ndvi.fetch_indices(lat, lng, settings.AGRO_API_KEY)
            except Exception:
                real_ndvi = {}

        # 2. CDSE zaxira (agar AgroMonitoring ishlamasa)
        if not real_ndvi and getattr(settings, "CDSE_USERNAME", "") and getattr(settings, "CDSE_PASSWORD", ""):
            try:
                token     = satellite_ndvi.get_token(settings.CDSE_USERNAME, settings.CDSE_PASSWORD)
                real_ndvi = satellite_ndvi.fetch_monthly_ndvi(lat, lng, token)
            except Exception:
                real_ndvi = {}

        monthly, di = enrich_monthly(monthly, real_ndvi or None)

        cur_ndvi  = monthly[-1]["ndvi"]  if monthly else 0.3
        cur_ndwi  = monthly[-1].get("ndwi") if monthly else None
        ago_ndvi  = monthly[0]["ndvi"]   if monthly else 0.3
        ndvi_chg  = round(cur_ndvi - ago_ndvi, 3)
        ann_prec  = round(sum(m["precip"]   for m in monthly), 1)
        avg_temp  = round(mean(m["temp"]    for m in monthly), 1)
        avg_wind  = round(mean(m["wind"]    for m in monthly if m.get("wind") is not None), 1)
        avg_humid = round(mean(m["humidity"] for m in monthly if m.get("humidity") is not None), 1)

        ai_ctx = {
            "joylashuv":         {"lat": round(lat, 4), "lng": round(lng, 4), "maydon_ha": area_ha},
            "joriy_ndvi":        cur_ndvi,
            "joriy_evi":         monthly[-1].get("evi", 0) if monthly else 0,
            "joriy_ndwi":        cur_ndwi,
            "ndvi_ozgarishi":    ndvi_chg,
            "qurgochlik_di":     di,
            "tuproq":            soil,
            "tuproq_kimyosi":    soil_props if soil_props else None,
            "yillik_yogin_mm":   ann_prec,
            "ortacha_harorat":   avg_temp,
            "ortacha_shamol":    avg_wind,
            "ortacha_namlik":    avg_humid,
            "max_ndvi":          max(m["ndvi"] for m in monthly),
            "min_ndvi":          min(m["ndvi"] for m in monthly),
        }

        try:
            analysis = ai_service.analyze(ai_ctx)
        except Exception as exc:
            analysis = {"xulosa": f"AI xatosi: {exc}"}

        weather = {
            "monthly":       [
                {
                    "month":   m["month"],
                    "temp":    m["temp"],
                    "precip":  m["precip"],
                    "wind":    m.get("wind", 0),
                    "humidity": m.get("humidity", 0),
                }
                for m in monthly
            ],
            "annual_precip": ann_prec,
            "avg_temp":      avg_temp,
            "avg_wind":      avg_wind,
            "avg_humidity":  avg_humid,
        }

        payload = {
            "location":  {"lat": round(lat, 4), "lng": round(lng, 4), "area_ha": area_ha},
            "ndvi":      {
                "current":       cur_ndvi,
                "change":        ndvi_chg,
                "monthly":       monthly,
                "drought_index": di,
                "ndwi_current":  cur_ndwi,
            },
            "soil":      soil,
            "weather":   weather,
            "analysis":  analysis,
            "source":    _build_source(monthly),
        }

        if save:
            obj = AnalysisResult.objects.create(
                name=name,
                center_lat=round(lat, 4),
                center_lng=round(lng, 4),
                area_ha=area_ha,
                coordinates=coords,
                ndvi_current=cur_ndvi,
                ndvi_change=ndvi_chg,
                ndwi_current=cur_ndwi,
                drought_index=di,
                ndvi_monthly=monthly,
                soil_data=soil,
                soil_properties=soil_props or {},
                weather_data=weather,
                ai_analysis=analysis,
            )
            payload["saved_id"] = obj.pk

        return Response(payload)


class AnalysisHistoryView(APIView):
    """GET /api/satellite/history/"""

    def get(self, request):
        qs = AnalysisResult.objects.all()[:30]
        return Response({
            "count":   AnalysisResult.objects.count(),
            "results": AnalysisListSerializer(qs, many=True).data,
        })


class AnalysisDetailView(APIView):
    """GET / DELETE /api/satellite/history/<pk>/"""

    def _get(self, pk):
        try:
            return AnalysisResult.objects.get(pk=pk)
        except AnalysisResult.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"error": "Topilmadi"}, status=404)
        return Response(AnalysisDetailSerializer(obj).data)

    def delete(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"error": "Topilmadi"}, status=404)
        obj.delete()
        return Response({"ok": True})

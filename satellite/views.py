from statistics import mean
import os

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import Field, AnalysisResult, CropImage
from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer,
    FieldSerializer, FieldMiniSerializer, FieldWriteSerializer,
    AnalysisListSerializer, AnalysisDetailSerializer,
    CropImageListSerializer, CropImageDetailSerializer,
)
from .services import meteo, ai_service, satellite_ndvi, agro_ndvi, crop_disease
from .services import soil_grids
from .services import water_sources as water_svc
from .services.ndvi import enrich_monthly


# ── OpenAPI schema blocks ──────────────────────────────────────────────────────

_latlng = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['lat', 'lng'],
    properties={
        'lat': openapi.Schema(type=openapi.TYPE_NUMBER, description='Kenglik (latitude)', example=41.2995),
        'lng': openapi.Schema(type=openapi.TYPE_NUMBER, description='Uzunlik (longitude)', example=69.2401),
    },
)

_analyze_request = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['coordinates'],
    properties={
        'coordinates': openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=_latlng,
            description='Dala polygon nuqtalari (kamida 3 ta)',
            min_items=3,
        ),
        'area_ha': openapi.Schema(
            type=openapi.TYPE_NUMBER,
            description='Maydon (gektarda). Null bo\'lsa koordinatalardan hisoblanadi.',
            example=0.5,
            nullable=True,
        ),
        'name': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='Ekin turi yoki dala nomi',
            example='Pomidor',
        ),
    },
)

_monthly_entry = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'month':       openapi.Schema(type=openapi.TYPE_STRING, description='Oy (YYYY-MM)', example='2025-05'),
        'ndvi':        openapi.Schema(type=openapi.TYPE_NUMBER, description='NDVI qiymati (Sentinel-2 yoki formula)', example=0.62, nullable=True),
        'evi':         openapi.Schema(type=openapi.TYPE_NUMBER, description='EVI qiymati', example=0.51, nullable=True),
        'ndwi':        openapi.Schema(type=openapi.TYPE_NUMBER, description='NDWI (suv indeksi)', example=0.12, nullable=True),
        'ndvi_source': openapi.Schema(type=openapi.TYPE_STRING, description='"sentinel-2" yoki "formula"', example='sentinel-2'),
        'temp':        openapi.Schema(type=openapi.TYPE_NUMBER, description='O\'rtacha harorat (°C)', example=24.5),
        'precip':      openapi.Schema(type=openapi.TYPE_NUMBER, description='Oylik yog\'in (mm)', example=18.3),
        'et':          openapi.Schema(type=openapi.TYPE_NUMBER, description='Bug\'lanish-transpiratsiya (mm)', example=120.0),
        'radiation':   openapi.Schema(type=openapi.TYPE_NUMBER, description='Quyosh radiatsiyasi (MJ/m²)', example=22.1),
        'wind':        openapi.Schema(type=openapi.TYPE_NUMBER, description='Shamol tezligi (m/s)', example=2.8),
        'humidity':    openapi.Schema(type=openapi.TYPE_NUMBER, description='Nisbiy namlik (%)', example=48.0),
    },
)

_soil_properties = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    description='SoilGrids ISRIC tuproq kimyosi',
    properties={
        'ph_h2o':  openapi.Schema(type=openapi.TYPE_NUMBER, description='pH (suvda)', example=7.2, nullable=True),
        'clay':    openapi.Schema(type=openapi.TYPE_NUMBER, description='Loy ulushi (g/kg → %)', example=28.0, nullable=True),
        'sand':    openapi.Schema(type=openapi.TYPE_NUMBER, description='Qum ulushi (%)', example=42.0, nullable=True),
        'silt':    openapi.Schema(type=openapi.TYPE_NUMBER, description='Shag\'al ulushi (%)', example=30.0, nullable=True),
        'soc':     openapi.Schema(type=openapi.TYPE_NUMBER, description='Organik karbon (g/kg)', example=12.5, nullable=True),
        'nitrogen':openapi.Schema(type=openapi.TYPE_NUMBER, description='Azot (cg/kg)', example=95.0, nullable=True),
        'bdod':    openapi.Schema(type=openapi.TYPE_NUMBER, description='Ko\'p zichlik (kg/m³)', example=1350.0, nullable=True),
        'cec':     openapi.Schema(type=openapi.TYPE_NUMBER, description='Kation almashinuv sig\'imi (mmol/kg)', example=185.0, nullable=True),
    },
)

_soil_data = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    description='Open-Meteo tuproq sensori va SoilGrids kimyosi',
    properties={
        'surface_temp':    openapi.Schema(type=openapi.TYPE_NUMBER, description='Tuproq yuzasi harorati (°C)', nullable=True),
        'depth_6cm_temp':  openapi.Schema(type=openapi.TYPE_NUMBER, description='6 sm chuqurlikdagi harorat (°C)', nullable=True),
        'depth_18cm_temp': openapi.Schema(type=openapi.TYPE_NUMBER, description='18 sm chuqurlikdagi harorat (°C)', nullable=True),
        'moisture_0_1cm':  openapi.Schema(type=openapi.TYPE_NUMBER, description='Namligi 0-1 sm (%)', nullable=True),
        'moisture_1_3cm':  openapi.Schema(type=openapi.TYPE_NUMBER, description='Namligi 1-3 sm (%)', nullable=True),
        'moisture_3_9cm':  openapi.Schema(type=openapi.TYPE_NUMBER, description='Namligi 3-9 sm (%)', nullable=True),
        'moisture_9_27cm': openapi.Schema(type=openapi.TYPE_NUMBER, description='Namligi 9-27 sm (%)', nullable=True),
        'humidity':        openapi.Schema(type=openapi.TYPE_NUMBER, description='Nisbiy namlik (%)', nullable=True),
        'wind_speed':      openapi.Schema(type=openapi.TYPE_NUMBER, description='Shamol tezligi (m/s)', nullable=True),
        'properties':      _soil_properties,
    },
)

_weather_data = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    description='ERA5 reanaliz ob-havo ko\'rsatkichlari',
    properties={
        'monthly':        openapi.Schema(type=openapi.TYPE_ARRAY, items=_monthly_entry, description='13 oylik ob-havo tarixi'),
        'annual_precip':  openapi.Schema(type=openapi.TYPE_NUMBER, description='Yillik yog\'in yig\'indisi (mm)', example=312.5),
        'avg_temp':       openapi.Schema(type=openapi.TYPE_NUMBER, description='O\'rtacha yillik harorat (°C)', example=15.8),
        'avg_wind':       openapi.Schema(type=openapi.TYPE_NUMBER, description='O\'rtacha shamol tezligi (m/s)', example=2.4),
        'avg_humidity':   openapi.Schema(type=openapi.TYPE_NUMBER, description='O\'rtacha nisbiy namlik (%)', example=51.0),
    },
)

_ai_analysis = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    description='Groq LLaMA 3.3 70B agronomik tahlil natijasi',
    properties={
        'ndvi_baho':             openapi.Schema(type=openapi.TYPE_STRING, description='NDVI/EVI/NDWI qiymatlari va ularning ma\'nosi'),
        'osimlik_holati':        openapi.Schema(type=openapi.TYPE_STRING, description='O\'simlik holati: Juda yaxshi | Yaxshi | O\'rtacha | Yomon | Juda yomon'),
        'tuproq_tahlili':        openapi.Schema(type=openapi.TYPE_STRING, description='Tuproq namligi, harorat va kimyosi tahlili'),
        'qurgochlik':            openapi.Schema(type=openapi.TYPE_STRING, description='Qurg\'oqchilik xatari va sababi'),
        'tavsiya_ekinlar':       openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='Tavsiya etiladigan ekinlar ro\'yxati'),
        'dehqonchilik_maslahati':openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='Dehqonchilik bo\'yicha amaliy maslahatlar'),
        'xavflar':               openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='Aniqlab olingan xavflar ro\'yxati'),
        'ustuvor_harakatlar':    openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='Zudlik bilan bajarilishi kerak bo\'lgan harakatlar'),
        'bashorat':              openapi.Schema(type=openapi.TYPE_STRING, description='Keyingi oyga bashorat'),
        'xulosa':                openapi.Schema(type=openapi.TYPE_STRING, description='Umumiy xulosa va asosiy tavsiya'),
    },
)

_analyze_response = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'location': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description='Dala markazi koordinatalari',
            properties={
                'lat':     openapi.Schema(type=openapi.TYPE_NUMBER, example=41.2995),
                'lng':     openapi.Schema(type=openapi.TYPE_NUMBER, example=69.2401),
                'area_ha': openapi.Schema(type=openapi.TYPE_NUMBER, example=0.5, nullable=True),
            },
        ),
        'ndvi': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description='Sentinel-2 NDVI ko\'rsatkichlari',
            properties={
                'current':       openapi.Schema(type=openapi.TYPE_NUMBER, description='Joriy NDVI (-1 dan +1 gacha)', example=0.58),
                'change':        openapi.Schema(type=openapi.TYPE_NUMBER, description='Yillik NDVI o\'zgarishi', example=0.05),
                'monthly':       openapi.Schema(type=openapi.TYPE_ARRAY, items=_monthly_entry),
                'drought_index': openapi.Schema(type=openapi.TYPE_NUMBER, description='Qurg\'oqchilik indeksi (-3 dan +3 gacha)', example=-0.4),
                'ndwi_current':  openapi.Schema(type=openapi.TYPE_NUMBER, description='Joriy NDWI (suv indeksi)', example=0.12, nullable=True),
            },
        ),
        'soil':     _soil_data,
        'weather':  _weather_data,
        'analysis': _ai_analysis,
        'source':   openapi.Schema(type=openapi.TYPE_STRING, description='Foydalanilgan ma\'lumot manbalari', example='Sentinel-2 NDVI (13/13 oy) + SoilGrids + Open-Meteo ERA5 + Groq LLaMA'),
        'water': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description='10 km radius ichidagi suv manbalari',
            properties={
                'summary': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'closest_name':       openapi.Schema(type=openapi.TYPE_STRING, example='Chirchiq daryosi'),
                        'closest_type_uz':    openapi.Schema(type=openapi.TYPE_STRING, example='Daryo'),
                        'closest_dist_km':    openapi.Schema(type=openapi.TYPE_NUMBER, example=2.4),
                        'closest_dist_text':  openapi.Schema(type=openapi.TYPE_STRING, example='2.4 km'),
                        'closest_direction':  openapi.Schema(type=openapi.TYPE_STRING, example='Shimoli-G\'arb'),
                        'irrigation_source':  openapi.Schema(type=openapi.TYPE_OBJECT, nullable=True),
                        'total_found':        openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                        'plain_text':         openapi.Schema(type=openapi.TYPE_STRING,
                            example="Eng yaqin suv manbai: Chirchiq daryosi — 2.4 km Shimoli-G'arb tomonda. Sug'orish uchun qulay."),
                    },
                ),
                'sources': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    description='Masofaga ko\'ra saralangan suv manbalari ro\'yxati',
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'name':           openapi.Schema(type=openapi.TYPE_STRING, example='Chirchiq daryosi'),
                            'type':           openapi.Schema(type=openapi.TYPE_STRING, example='river'),
                            'type_uz':        openapi.Schema(type=openapi.TYPE_STRING, example='Daryo'),
                            'distance_km':    openapi.Schema(type=openapi.TYPE_NUMBER, example=2.4),
                            'distance_text':  openapi.Schema(type=openapi.TYPE_STRING, example='2.4 km'),
                            'direction':      openapi.Schema(type=openapi.TYPE_STRING, example="Shimoli-G'arb"),
                            'irrigation_ok':  openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True),
                            'lat':            openapi.Schema(type=openapi.TYPE_NUMBER, example=41.3012),
                            'lng':            openapi.Schema(type=openapi.TYPE_NUMBER, example=69.2187),
                        },
                    ),
                ),
            },
        ),
        'saved_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Saqlangan tahlil ID', example=7),
        'field_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Yaratilgan dala ID', example=3),
    },
)

_history_item = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'id':           openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
        'created_at':   openapi.Schema(type=openapi.TYPE_STRING, format='date-time', example='2026-05-18T13:00:00+05:00'),
        'name':         openapi.Schema(type=openapi.TYPE_STRING, description='Ekin turi yoki dala nomi', example='Pomidor'),
        'center_lat':   openapi.Schema(type=openapi.TYPE_NUMBER, example=41.2995),
        'center_lng':   openapi.Schema(type=openapi.TYPE_NUMBER, example=69.2401),
        'area_ha':      openapi.Schema(type=openapi.TYPE_NUMBER, example=0.5, nullable=True),
        'ndvi_current': openapi.Schema(type=openapi.TYPE_NUMBER, description='Tahlil vaqtidagi NDVI', example=0.58),
        'ndwi_current': openapi.Schema(type=openapi.TYPE_NUMBER, description='Tahlil vaqtidagi NDWI', example=0.12, nullable=True),
        'ndvi_change':  openapi.Schema(type=openapi.TYPE_NUMBER, description='NDVI yillik o\'zgarishi', example=0.05),
        'drought_index':openapi.Schema(type=openapi.TYPE_NUMBER, description='Qurg\'oqchilik indeksi', example=-0.4),
        'ndvi_label':   openapi.Schema(type=openapi.TYPE_STRING, description='NDVI holati belgisi', example="O'rtacha"),
    },
)

_history_list_response = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'count':   openapi.Schema(type=openapi.TYPE_INTEGER, description='Jami tahlillar soni', example=12),
        'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=_history_item, description='So\'nggi 30 ta tahlil'),
    },
)

_error_response = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'error': openapi.Schema(type=openapi.TYPE_STRING, example='Koordinatalar kiritilmagan'),
    },
)


# ── Auth OpenAPI schemas ──────────────────────────────────────────────────────

_register_body = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['username', 'password'],
    properties={
        'username':   openapi.Schema(type=openapi.TYPE_STRING, example='akbar'),
        'password':   openapi.Schema(type=openapi.TYPE_STRING, example='secret123'),
        'first_name': openapi.Schema(type=openapi.TYPE_STRING, example='Akbar', description='Ism (ixtiyoriy)'),
        'email':      openapi.Schema(type=openapi.TYPE_STRING, format='email', example='akbar@mail.com', description='Email (ixtiyoriy)'),
    },
)

_login_body = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['username', 'password'],
    properties={
        'username': openapi.Schema(type=openapi.TYPE_STRING, example='akbar'),
        'password': openapi.Schema(type=openapi.TYPE_STRING, example='secret123'),
    },
)

_user_response = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'id':           openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
        'username':     openapi.Schema(type=openapi.TYPE_STRING, example='akbar'),
        'first_name':   openapi.Schema(type=openapi.TYPE_STRING, example='Akbar'),
        'email':        openapi.Schema(type=openapi.TYPE_STRING, example='akbar@mail.com'),
        'date_joined':  openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
    },
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_or_none(request):
    """Login bo'lgan bo'lsa User qaytaradi, aks holda None."""
    u = getattr(request, 'user', None)
    return u if (u and u.is_authenticated) else None


def _sanitize(obj):
    """NaN va Infinity qiymatlarini None ga almashtiradi (JSON muammosini oldini oladi)."""
    if isinstance(obj, float):
        return None if (obj != obj or obj == float("inf") or obj == float("-inf")) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _build_source(monthly: list[dict]) -> str:
    sat = sum(1 for m in monthly if m.get("ndvi_source") == "sentinel-2")
    if sat:
        return f"Sentinel-2 NDVI ({sat}/{len(monthly)} oy) + SoilGrids + Open-Meteo ERA5 + Groq LLaMA"
    return "Open-Meteo ERA5 (NDVI formula) + SoilGrids + Groq LLaMA"


# ── Views ─────────────────────────────────────────────────────────────────────

class FrontendView(APIView):
    """
    Asosiy frontend sahifasi.
    AgroVision React SPA ni qaytaradi.
    """

    swagger_schema = None  # Swagger dan yashir (bu HTML sahifa, API emas)

    def get(self, request):
        return render(request, "index.html")


class SatelliteAnalyzeView(APIView):
    """
    Dala tahlili — asosiy API.

    Berilgan polygon koordinatalari asosida:
    - Sentinel-2 sun'iy yo'ldoshidan NDVI/EVI/NDWI indekslarini oladi
    - ERA5 reanaliz orqali 13 oylik ob-havo tarixini yuklaydi
    - SoilGrids ISRIC dan haqiqiy tuproq kimyosini oladi
    - Groq LLaMA 3.3 70B yordamida agronomik tahlil yaratadi

    **NDVI manbalari (ustuvorlik tartibi):**
    1. AgroMonitoring (Sentinel-2, haqiqiy o'lchovlar)
    2. CDSE / Copernicus Data Space (zaxira)
    3. ERA5 formula asosida hisoblash (oxirgi zaxira)

    **NDVI o'lchovlari:**
    - `0.6+` → Sich o'simlik
    - `0.3–0.6` → O'rtacha
    - `0.1–0.3` → Siyrak
    - `< 0.1` → Quruq/beton
    """

    @swagger_auto_schema(
        operation_id='satellite_analyze',
        operation_summary='Dala tahlili (asosiy)',
        operation_description=(
            'Polygon koordinatalari asosida sun\'iy yo\'ldosh, ob-havo va tuproq '
            'ma\'lumotlarini yuklab AI tahlil natijasini qaytaradi.\n\n'
            '**Ishlash vaqti:** 10–30 soniya (API so\'rovlari tufayli)\n\n'
            '**Majburiy maydon:** `coordinates` — kamida 3 ta nuqta'
        ),
        request_body=_analyze_request,
        responses={
            200: openapi.Response('Tahlil muvaffaqiyatli yakunlandi', _analyze_response),
            400: openapi.Response('Noto\'g\'ri so\'rov (koordinatalar yo\'q)', _error_response),
            502: openapi.Response('Tashqi API xatosi (Open-Meteo, AgroMonitoring)', _error_response),
        },
        tags=['Tahlil'],
    )
    def post(self, request):
        coords          = request.data.get("coordinates", [])
        area_ha         = request.data.get("area_ha")
        name            = request.data.get("name", "").strip()

        if not coords:
            return Response({"error": "Koordinatalar kiritilmagan"}, status=400)

        lat = round(sum(c["lat"] for c in coords) / len(coords), 6)
        lng = round(sum(c["lng"] for c in coords) / len(coords), 6)

        try:
            archive, soil_json = meteo.fetch_data(lat, lng)
        except Exception as exc:
            return Response({"error": f"Open-Meteo xatosi: {exc}"}, status=502)

        monthly = meteo.process_monthly(archive)
        if not monthly:
            return Response({"error": "Ob-havo ma'lumoti olinmadi, qayta urinib ko'ring"}, status=502)
        soil    = meteo.extract_soil(soil_json)

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
        ann_prec   = round(sum(m["precip"] for m in monthly), 1)
        avg_temp   = round(mean(m["temp"]  for m in monthly), 1)
        _winds     = [m["wind"]     for m in monthly if m.get("wind")     not in (None, 0)]
        _humids    = [m["humidity"] for m in monthly if m.get("humidity") not in (None, 0)]
        avg_wind   = round(mean(_winds),  1) if _winds  else 0.0
        avg_humid  = round(mean(_humids), 1) if _humids else 0.0

        # Suv manbalari — AI dan oldin (AI kontekstiga ham kiradi)
        try:
            water_list    = water_svc.fetch_water_sources(lat, lng, radius_km=10)
            water_summary = water_svc.summarize(water_list)
        except Exception:
            water_list    = []
            water_summary = {"plain_text": "Suv manbai ma'lumoti olinmadi", "total_found": 0}

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
            "max_ndvi":          max((m["ndvi"] for m in monthly), default=0.3),
            "min_ndvi":          min((m["ndvi"] for m in monthly), default=0.0),
            "suv_manbalari":     water_summary,
        }

        try:
            analysis = ai_service.analyze(ai_ctx)
        except Exception as exc:
            analysis = {"xulosa": f"AI xatosi: {exc}"}

        weather = {
            "monthly":       [
                {
                    "month":    m["month"],
                    "temp":     m["temp"],
                    "precip":   m["precip"],
                    "wind":     m.get("wind", 0),
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
            "water": {
                "summary": water_summary,
                "sources": water_list,
            },
            "source":    _build_source(monthly),
        }

        # Har doim: dala yaratiladi va tahlil unga bog'lanadi
        current_user = _user_or_none(request)

        field = Field.objects.create(
            user=current_user,
            name=name,
            crop=name,
            coordinates=coords,
            center_lat=round(lat, 4),
            center_lng=round(lng, 4),
            area_ha=area_ha,
        )

        obj = AnalysisResult.objects.create(
            user=current_user,
            field=field,
            name=name,
            center_lat=round(lat, 4),
            center_lng=round(lng, 4),
            area_ha=area_ha,
            coordinates=coords,
            ndvi_current=cur_ndvi,
            ndvi_change=ndvi_chg,
            ndwi_current=cur_ndwi,
            drought_index=di,
            ndvi_monthly=_sanitize(monthly),
            soil_data=_sanitize(soil),
            soil_properties=_sanitize(soil_props or {}),
            weather_data=_sanitize(weather),
            ai_analysis=_sanitize(analysis),
        )

        payload["saved_id"] = obj.pk
        payload["field_id"]  = field.pk

        return Response(_sanitize(payload))


class AnalysisHistoryView(APIView):
    """
    Saqlangan tahlillar tarixi.

    So'nggi 30 ta tahlilni qaytaradi. Har bir element:
    - Tahlil vaqti, joylashuv, maydon
    - NDVI joriy qiymati va holati
    - Qurg'oqchilik indeksi
    """

    @swagger_auto_schema(
        operation_id='history_list',
        operation_summary='Tahlillar ro\'yxati',
        operation_description='So\'nggi 30 ta saqlangan dala tahlilini qaytaradi.',
        responses={
            200: openapi.Response('Muvaffaqiyatli', _history_list_response),
        },
        tags=['Tarix'],
    )
    def get(self, request):
        u = _user_or_none(request)
        qs = AnalysisResult.objects.filter(user=u) if u else AnalysisResult.objects.none()
        return Response({
            "count":   qs.count(),
            "results": AnalysisListSerializer(qs[:30], many=True).data,
        })


class AnalysisDetailView(APIView):
    """
    Bitta tahlilning to'liq ma'lumotlari va o'chirish.

    GET → barcha maydonlar: NDVI oylik qatorlari, tuproq kimyosi, ob-havo tarixi, AI tahlil.\n
    DELETE → tahlilni bazadan o'chiradi.
    """

    def _get(self, pk, user):
        try:
            qs = AnalysisResult.objects.filter(user=user) if user else AnalysisResult.objects.none()
            return qs.get(pk=pk)
        except AnalysisResult.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_id='history_detail',
        operation_summary='Tahlil batafsil',
        operation_description=(
            'Berilgan ID bo\'yicha tahlilning barcha maydonlarini qaytaradi: '
            'NDVI oylik tarixi, tuproq kimyosi (SoilGrids), ob-havo, AI tahlil.'
        ),
        responses={
            200: openapi.Response('Muvaffaqiyatli', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='AnalysisResult modeli barcha maydonlari + ndvi_label',
                properties={
                    'id':             openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                    'created_at':     openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
                    'name':           openapi.Schema(type=openapi.TYPE_STRING, example='Pomidor'),
                    'center_lat':     openapi.Schema(type=openapi.TYPE_NUMBER, example=41.2995),
                    'center_lng':     openapi.Schema(type=openapi.TYPE_NUMBER, example=69.2401),
                    'area_ha':        openapi.Schema(type=openapi.TYPE_NUMBER, example=0.5, nullable=True),
                    'coordinates':    openapi.Schema(type=openapi.TYPE_ARRAY, items=_latlng),
                    'ndvi_current':   openapi.Schema(type=openapi.TYPE_NUMBER, example=0.58),
                    'ndvi_change':    openapi.Schema(type=openapi.TYPE_NUMBER, example=0.05),
                    'ndvi_monthly':   openapi.Schema(type=openapi.TYPE_ARRAY, items=_monthly_entry),
                    'drought_index':  openapi.Schema(type=openapi.TYPE_NUMBER, example=-0.4),
                    'ndwi_current':   openapi.Schema(type=openapi.TYPE_NUMBER, example=0.12, nullable=True),
                    'soil_data':      _soil_data,
                    'soil_properties':_soil_properties,
                    'weather_data':   _weather_data,
                    'ai_analysis':    _ai_analysis,
                    'ndvi_label':     openapi.Schema(type=openapi.TYPE_STRING, example="O'rtacha"),
                },
            )),
            404: openapi.Response('Topilmadi', _error_response),
        },
        tags=['Tarix'],
    )
    def get(self, request, pk):
        obj = self._get(pk, _user_or_none(request))
        if not obj:
            return Response({"error": "Topilmadi"}, status=404)
        return Response(AnalysisDetailSerializer(obj).data)

    @swagger_auto_schema(
        operation_id='history_delete',
        operation_summary='Tahlilni o\'chirish',
        operation_description='Berilgan ID bo\'yicha tahlilni bazadan butunlay o\'chiradi.',
        responses={
            200: openapi.Response('Muvaffaqiyatli o\'chirildi', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={'ok': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True)},
            )),
            404: openapi.Response('Topilmadi', _error_response),
        },
        tags=['Tarix'],
    )
    def delete(self, request, pk):
        obj = self._get(pk, _user_or_none(request))
        if not obj:
            return Response({"error": "Topilmadi"}, status=404)
        obj.delete()
        return Response({"ok": True})


# ── Field OpenAPI schema ───────────────────────────────────────────────────────

_field_write_body = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['coordinates', 'center_lat', 'center_lng'],
    properties={
        'name': openapi.Schema(
            type=openapi.TYPE_STRING,
            description="Dala nomi (ixtiyoriy)",
            example="Janubiy dala",
        ),
        'crop': openapi.Schema(
            type=openapi.TYPE_STRING,
            description="Ekin turi",
            example="Pomidor",
        ),
        'coordinates': openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=_latlng,
            description="Polygon nuqtalari (kamida 3 ta)",
            min_items=3,
        ),
        'center_lat': openapi.Schema(type=openapi.TYPE_NUMBER, description="Markaz kenglik", example=41.2995),
        'center_lng': openapi.Schema(type=openapi.TYPE_NUMBER, description="Markaz uzunlik", example=69.2401),
        'area_ha':    openapi.Schema(type=openapi.TYPE_NUMBER, description="Maydon (gektarda)", example=0.5, nullable=True),
        'notes':       openapi.Schema(type=openapi.TYPE_STRING, description="Qo'shimcha izoh", example=""),
    },
)

_field_response = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'id':             openapi.Schema(type=openapi.TYPE_INTEGER, example=3),
        'created_at':     openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
        'updated_at':     openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
        'name':           openapi.Schema(type=openapi.TYPE_STRING, example="Janubiy dala"),
        'crop':           openapi.Schema(type=openapi.TYPE_STRING, example="Pomidor"),
        'coordinates':    openapi.Schema(type=openapi.TYPE_ARRAY, items=_latlng),
        'center_lat':     openapi.Schema(type=openapi.TYPE_NUMBER, example=41.2995),
        'center_lng':     openapi.Schema(type=openapi.TYPE_NUMBER, example=69.2401),
        'area_ha':        openapi.Schema(type=openapi.TYPE_NUMBER, example=0.5, nullable=True),
        'area_sotix':     openapi.Schema(type=openapi.TYPE_NUMBER, example=50.0, nullable=True),
        'notes':          openapi.Schema(type=openapi.TYPE_STRING, example=""),
    },
)

_field_list_response = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'count':   openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
        'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=_field_response),
    },
)


# ── Field Views ───────────────────────────────────────────────────────────────

class FieldListCreateView(APIView):
    """
    Dalalar ro'yxati va yangi dala yaratish.

    **GET** — barcha saqlangan dalalarni qaytaradi (koordinatalar bilan).
    **POST** — yangi dala yaratadi va saqlab qo'yadi.
    """

    @swagger_auto_schema(
        operation_id='fields_list',
        operation_summary="Dalalar ro'yxati",
        operation_description="Barcha saqlangan dala polygonlari va ma'lumotlari.",
        responses={200: openapi.Response("Muvaffaqiyatli", _field_list_response)},
        tags=['Dalalar'],
    )
    def get(self, request):
        u = _user_or_none(request)
        qs = Field.objects.filter(user=u) if u else Field.objects.none()
        return Response({
            "count":   qs.count(),
            "results": FieldSerializer(qs, many=True).data,
        })

    @swagger_auto_schema(
        operation_id='fields_create',
        operation_summary="Yangi dala saqlash",
        operation_description=(
            "Yangi dala polygon ma'lumotlarini bazaga saqlaydi.\n\n"
            "Frontend FieldPage'dan foydalanuvchi dala chizib bo'lgach "
            "bu endpoint orqali saqlash mumkin."
        ),
        request_body=_field_write_body,
        responses={
            201: openapi.Response("Yaratildi", _field_response),
            400: openapi.Response("Noto'g'ri ma'lumot", _error_response),
        },
        tags=['Dalalar'],
    )
    def post(self, request):
        ser = FieldWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        # center avtomatik hisoblash (agar berilmagan bo'lsa)
        coords = ser.validated_data['coordinates']
        if 'center_lat' not in request.data:
            ser.validated_data['center_lat'] = sum(c['lat'] for c in coords) / len(coords)
        if 'center_lng' not in request.data:
            ser.validated_data['center_lng'] = sum(c['lng'] for c in coords) / len(coords)

        field = ser.save(user=_user_or_none(request))
        return Response(FieldSerializer(field).data, status=201)


class FieldDetailView(APIView):
    """
    Bitta dala: ko'rish, tahrirlash, o'chirish.

    **GET** — to'liq ma'lumot (koordinatalar bilan).\n
    **PUT** — barcha maydonlarni yangilash.\n
    **PATCH** — faqat ko'rsatilgan maydonlarni yangilash.\n
    **DELETE** — dala va uning ma'lumotlarini o'chirish.
    """

    def _get(self, pk, user):
        try:
            qs = Field.objects.filter(user=user) if user else Field.objects.none()
            return qs.get(pk=pk)
        except Field.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_id='fields_detail',
        operation_summary="Dala batafsil",
        operation_description="Berilgan ID bo'yicha dala to'liq ma'lumotlari.",
        responses={
            200: openapi.Response("Muvaffaqiyatli", _field_response),
            404: openapi.Response("Topilmadi", _error_response),
        },
        tags=['Dalalar'],
    )
    def get(self, request, pk):
        obj = self._get(pk, _user_or_none(request))
        if not obj:
            return Response({"error": "Dala topilmadi"}, status=404)
        return Response(FieldSerializer(obj).data)

    @swagger_auto_schema(
        operation_id='fields_update',
        operation_summary="Dala ma'lumotlarini yangilash (to'liq)",
        request_body=_field_write_body,
        responses={
            200: openapi.Response("Yangilandi", _field_response),
            400: openapi.Response("Noto'g'ri ma'lumot", _error_response),
            404: openapi.Response("Topilmadi", _error_response),
        },
        tags=['Dalalar'],
    )
    def put(self, request, pk):
        obj = self._get(pk, _user_or_none(request))
        if not obj:
            return Response({"error": "Dala topilmadi"}, status=404)
        ser = FieldWriteSerializer(obj, data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)
        field = ser.save()
        return Response(FieldSerializer(field).data)

    @swagger_auto_schema(
        operation_id='fields_partial_update',
        operation_summary="Dala ma'lumotlarini yangilash (qisman)",
        request_body=_field_write_body,
        responses={
            200: openapi.Response("Yangilandi", _field_response),
            400: openapi.Response("Noto'g'ri ma'lumot", _error_response),
            404: openapi.Response("Topilmadi", _error_response),
        },
        tags=['Dalalar'],
    )
    def patch(self, request, pk):
        obj = self._get(pk, _user_or_none(request))
        if not obj:
            return Response({"error": "Dala topilmadi"}, status=404)
        ser = FieldWriteSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=400)
        field = ser.save()
        return Response(FieldSerializer(field).data)

    @swagger_auto_schema(
        operation_id='fields_delete',
        operation_summary="Dala o'chirish",
        operation_description="Berilgan ID bo'yicha dala va uning barcha ma'lumotlarini o'chiradi.",
        responses={
            200: openapi.Response("O'chirildi", openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={'ok': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True)},
            )),
            404: openapi.Response("Topilmadi", _error_response),
        },
        tags=['Dalalar'],
    )
    def delete(self, request, pk):
        obj = self._get(pk, _user_or_none(request))
        if not obj:
            return Response({"error": "Dala topilmadi"}, status=404)
        obj.delete()
        return Response({"ok": True})


class FieldAnalysesView(APIView):
    """
    Bitta dalaga tegishli barcha tahlillar.

    **GET** `/api/satellite/fields/<pk>/analyses/`
    → o'sha dala uchun bajarilgan barcha tahlillarni qaytaradi.
    """

    @swagger_auto_schema(
        operation_id='field_analyses',
        operation_summary="Dala tahlillari",
        operation_description="Berilgan dala ID'si bo'yicha barcha tahlil natijalarini qaytaradi.",
        responses={
            200: openapi.Response("Muvaffaqiyatli", _history_list_response),
            404: openapi.Response("Topilmadi", _error_response),
        },
        tags=['Dalalar'],
    )
    def get(self, request, pk):
        u = _user_or_none(request)
        try:
            qs_f = Field.objects.filter(user=u) if u else Field.objects.none()
            field = qs_f.get(pk=pk)
        except Field.DoesNotExist:
            return Response({"error": "Dala topilmadi"}, status=404)

        qs = field.analyses.filter(user=u) if u else field.analyses.none()
        return Response({
            "field":   FieldMiniSerializer(field).data,
            "count":   qs.count(),
            "results": AnalysisListSerializer(qs, many=True).data,
        })


# ── Auth Views ─────────────────────────────────────────────────────────────────

class RegisterView(APIView):
    """
    Yangi foydalanuvchi ro'yxatdan o'tish.

    Username va parol bilan ro'yxatdan o'tadi va avtomatik login bo'ladi.
    """

    @swagger_auto_schema(
        operation_id='auth_register',
        operation_summary="Ro'yxatdan o'tish",
        request_body=_register_body,
        responses={
            201: openapi.Response("Muvaffaqiyatli ro'yxatdan o'tdi", _user_response),
            400: openapi.Response("Xato ma'lumot (masalan, username band)", _error_response),
        },
        tags=['Auth'],
    )
    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)
        user = ser.save()
        login(request, user)
        return Response(UserSerializer(user).data, status=201)


class LoginView(APIView):
    """
    Tizimga kirish.

    Username va parol bilan kiradi, session cookie qaytaradi.
    """

    @swagger_auto_schema(
        operation_id='auth_login',
        operation_summary="Tizimga kirish",
        request_body=_login_body,
        responses={
            200: openapi.Response("Muvaffaqiyatli kirdi", _user_response),
            400: openapi.Response("Username yoki parol noto'g'ri", _error_response),
        },
        tags=['Auth'],
    )
    def post(self, request):
        ser = LoginSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)
        user = authenticate(
            request,
            username=ser.validated_data['username'],
            password=ser.validated_data['password'],
        )
        if not user:
            return Response({"error": "Username yoki parol noto'g'ri"}, status=400)
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    """
    Tizimdan chiqish.

    Session o'chiriladi.
    """

    @swagger_auto_schema(
        operation_id='auth_logout',
        operation_summary="Tizimdan chiqish",
        responses={
            200: openapi.Response("Chiqildi", openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={'ok': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True)},
            )),
        },
        tags=['Auth'],
    )
    def post(self, request):
        logout(request)
        return Response({"ok": True})


class MeView(APIView):
    """
    Joriy foydalanuvchi ma'lumotlari.

    Login bo'lmagan bo'lsa `null` qaytaradi (403 emas).
    """

    @swagger_auto_schema(
        operation_id='auth_me',
        operation_summary="Joriy foydalanuvchi",
        responses={
            200: openapi.Response("Foydalanuvchi ma'lumotlari yoki null", openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'authenticated': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True),
                    'user': _user_response,
                },
            )),
        },
        tags=['Auth'],
    )
    def get(self, request):
        u = _user_or_none(request)
        if not u:
            return Response({"authenticated": False, "user": None})
        return Response({"authenticated": True, "user": UserSerializer(u).data})




# ── Crop Image Analysis ────────────────────────────────────────────────────────

_crop_image_response = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'id':             openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
        'created_at':     openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
        'field':          FieldMiniSerializer().child if hasattr(FieldMiniSerializer(), 'child') else _latlng,
        'health_status':  openapi.Schema(type=openapi.TYPE_STRING, example='healthy', description='healthy|moderate|poor|critical'),
        'confidence':     openapi.Schema(type=openapi.TYPE_NUMBER, example=0.85, description='Ishonch darajasi (0-1)'),
        'diseases':       openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'name':       openapi.Schema(type=openapi.TYPE_STRING, example='Fitoroftora'),
                'symptoms':   openapi.Schema(type=openapi.TYPE_STRING),
                'severity':   openapi.Schema(type=openapi.TYPE_STRING),
                'treatment':  openapi.Schema(type=openapi.TYPE_STRING),
                'confidence': openapi.Schema(type=openapi.TYPE_NUMBER),
            },
        )),
        'analysis':       openapi.Schema(type=openapi.TYPE_OBJECT, description='Batafsil tahlil'),
        'image':          openapi.Schema(type=openapi.TYPE_STRING, format='uri', description='Rasm URL'),
    },
)


class CropImageAnalyzeView(APIView):
    """
    Mahsulot rasmi tahlili — Groq LLaMA 3.3 70B yordamida.

    Foydalanuvchi rasmi yuboradi va dala ID'sini ko'rsatadi.
    API rasm tahlil qiladi va kasalliklar, sog'lig'i holatini aniqlab qo'yadi.

    **Ishlash vaqti:** 5–15 soniya (Groq API chaqiruvi tufayli)
    """
    
    parser_classes = (MultiPartParser, FormParser)

    @swagger_auto_schema(
        operation_id='crop_image_analyze',
        operation_summary='Mahsulot rasmi tahlili',
        operation_description=(
            'Yuklangan rasmdagi mahsulotni AI yordamida tahlil qiladi.\n\n'
            'Sog\'lig\'i holati, kasalliklar, davolash usullari va tavsiyalarni qaytaradi.'
        ),
        manual_parameters=[
            openapi.Parameter(
                'image',
                openapi.IN_FORM,
                description='Rasm fayli (JPEG, PNG)',
                type=openapi.TYPE_FILE,
                required=True,
            ),
            openapi.Parameter(
                'field',
                openapi.IN_FORM,
                description='Dala ID (ixtiyoriy)',
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            201: openapi.Response('Tahlil muvaffaqiyatli yakunlandi', _crop_image_response),
            400: openapi.Response('Rasm yuklangan emas', _error_response),
            502: openapi.Response('Groq API xatosi', _error_response),
        },
        tags=['Mahsulot Tahlili'],
    )
    def post(self, request):
        # Rasm faylini olish
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({"error": "Rasm fayli yuklangan emas"}, status=400)
        
        # Dala ID'sini olish (ixtiyoriy)
        field_id = request.data.get('field')
        field = None
        if field_id:
            try:
                u = _user_or_none(request)
                qs = Field.objects.filter(user=u) if u else Field.objects.none()
                field = qs.get(pk=field_id)
            except Field.DoesNotExist:
                pass
        
        # Rasm vaqtiy saqlash
        temp_dir = settings.MEDIA_ROOT / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        user_id = request.user.id if request.user.is_authenticated else 'anon'
        # Rasm nomini to'g'ri saqlash (UUID qo'shmaslik)
        original_filename = image_file.name
        temp_path = temp_dir / f"crop_{user_id}_{original_filename}"
        
        try:
            # Rasmni saqlash
            with open(temp_path, 'wb') as f:
                for chunk in image_file.chunks():
                    f.write(chunk)
            
            # Ekin turini olish (agar dala bo'lsa)
            crop_name = field.crop if field else ""
            
            # Rasmi tahlil qilish (TensorFlow + Groq)
            analysis_result = crop_disease.analyze_crop_image(str(temp_path), crop_name)
            
            # Rasm nomini to'g'ri saqlash (UUID qo'shmaslik)
            # Django avtomatik UUID qo'shadi, shuning uchun original nomni saqlaymiz
            crop_image = CropImage.objects.create(
                user=_user_or_none(request),
                field=field,
                image=image_file,
                health_status=analysis_result.get('health_status', 'unknown'),
                diseases=analysis_result.get('diseases', []),
                analysis=analysis_result.get('analysis', {}),
                confidence=analysis_result.get('confidence', 0.0),
            )
            
            return Response(
                CropImageDetailSerializer(crop_image).data,
                status=201
            )
        
        except Exception as e:
            print(f"Rasm tahlil xatosi: {e}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": f"Tahlil xatosi: {str(e)}"},
                status=502
            )
        
        finally:
            # Vaqtiy faylni o'chirish
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass


class CropImageHistoryView(APIView):
    """
    Saqlangan mahsulot rasmlari tarixi.

    So'nggi 50 ta rasmi tahlilini qaytaradi.
    """

    @swagger_auto_schema(
        operation_id='crop_image_history',
        operation_summary='Mahsulot rasmlari tarixi',
        operation_description='So\'nggi 50 ta saqlangan rasm tahlillari.',
        responses={
            200: openapi.Response('Muvaffaqiyatli', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER, example=12),
                    'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=_crop_image_response),
                },
            )),
        },
        tags=['Mahsulot Tahlili'],
    )
    def get(self, request):
        u = _user_or_none(request)
        qs = CropImage.objects.filter(user=u) if u else CropImage.objects.none()
        return Response({
            "count": qs.count(),
            "results": CropImageListSerializer(qs[:50], many=True).data,
        })


class CropImageDetailView(APIView):
    """
    Bitta rasm tahlilining to'liq ma'lumotlari.

    **GET** → barcha maydonlar: sog'lig'i holati, kasalliklar, tavsiyalar.\n
    **DELETE** → rasmi tahlilini o'chiradi.
    """

    def _get(self, pk, user):
        try:
            qs = CropImage.objects.filter(user=user) if user else CropImage.objects.none()
            return qs.get(pk=pk)
        except CropImage.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_id='crop_image_detail',
        operation_summary='Rasm tahlili batafsil',
        operation_description='Berilgan ID bo\'yicha rasm tahlilining barcha ma\'lumotlari.',
        responses={
            200: openapi.Response('Muvaffaqiyatli', _crop_image_response),
            404: openapi.Response('Topilmadi', _error_response),
        },
        tags=['Mahsulot Tahlili'],
    )
    def get(self, request, pk):
        obj = self._get(pk, _user_or_none(request))
        if not obj:
            return Response({"error": "Rasm tahlili topilmadi"}, status=404)
        return Response(CropImageDetailSerializer(obj).data)

    @swagger_auto_schema(
        operation_id='crop_image_delete',
        operation_summary='Rasm tahlilini o\'chirish',
        operation_description='Berilgan ID bo\'yicha rasm tahlilini o\'chiradi.',
        responses={
            200: openapi.Response('O\'chirildi', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={'ok': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True)},
            )),
            404: openapi.Response('Topilmadi', _error_response),
        },
        tags=['Mahsulot Tahlili'],
    )
    def delete(self, request, pk):
        obj = self._get(pk, _user_or_none(request))
        if not obj:
            return Response({"error": "Rasm tahlili topilmadi"}, status=404)
        obj.delete()
        return Response({"ok": True})


class FieldCropImagesView(APIView):
    """
    Bitta dalaga tegishli barcha mahsulot rasmlari.

    **GET** `/api/satellite/fields/<pk>/crop-images/`
    → o'sha dala uchun yuklangan barcha rasmlari tahlillarini qaytaradi.
    """

    @swagger_auto_schema(
        operation_id='field_crop_images',
        operation_summary='Dala mahsulot rasmlari',
        operation_description='Berilgan dala ID\'si bo\'yicha barcha rasm tahlillari.',
        responses={
            200: openapi.Response('Muvaffaqiyatli', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'field': FieldMiniSerializer().child if hasattr(FieldMiniSerializer(), 'child') else _latlng,
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                    'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=_crop_image_response),
                },
            )),
            404: openapi.Response('Topilmadi', _error_response),
        },
        tags=['Mahsulot Tahlili'],
    )
    def get(self, request, pk):
        u = _user_or_none(request)
        try:
            qs_f = Field.objects.filter(user=u) if u else Field.objects.none()
            field = qs_f.get(pk=pk)
        except Field.DoesNotExist:
            return Response({"error": "Dala topilmadi"}, status=404)

        qs = field.crop_images.filter(user=u) if u else field.crop_images.none()
        return Response({
            "field": FieldMiniSerializer(field).data,
            "count": qs.count(),
            "results": CropImageListSerializer(qs, many=True).data,
        })

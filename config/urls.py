from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="TerraSat / AgroVision API",
        default_version="v1",
        description=(
            "Sun'iy yo'ldosh, AI va ob-havo asosida qishloq xo'jaligi tahlil platformasi.\n\n"
            "**Asosiy imkoniyatlar:**\n"
            "- Sentinel-2 sun'iy yo'ldoshidan haqiqiy NDVI/EVI/NDWI indekslari (AgroMonitoring)\n"
            "- ERA5 reanaliz orqali ob-havo va tuproq ma'lumotlari (Open-Meteo)\n"
            "- SoilGrids ISRIC tuproq kimyosi (pH, loy, qum, azot, organik karbon)\n"
            "- Groq LLaMA 3.3 70B sun'iy intellekt agronomik tahlil\n"
            "- Tahlil natijalarini saqlash va tarix ko'rish"
        ),
        terms_of_service="",
        contact=openapi.Contact(email="akbarkhojayev@gmail.com"),
        license=openapi.License(name="MIT"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('satellite.urls')),

    # Swagger UI
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    # ReDoc UI
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    # Raw JSON/YAML schema
    path('swagger.json', schema_view.without_ui(cache_timeout=0), name='schema-json'),
]

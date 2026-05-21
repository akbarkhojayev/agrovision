from django.contrib import admin
from .models import AnalysisResult


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display  = ['__str__', 'ndvi_current', 'ndvi_label', 'drought_index', 'area_ha', 'created_at']
    list_filter   = ['created_at']
    search_fields = ['name']
    readonly_fields = [
        'created_at', 'ndvi_monthly', 'soil_data',
        'weather_data', 'ai_analysis', 'coordinates',
    ]
    ordering = ['-created_at']
    fieldsets = (
        ('Joylashuv', {'fields': ('name', 'center_lat', 'center_lng', 'area_ha', 'coordinates')}),
        ('NDVI', {'fields': ('ndvi_current', 'ndvi_change', 'drought_index', 'ndvi_monthly')}),
        ('Ma\'lumotlar', {'fields': ('soil_data', 'weather_data', 'ai_analysis')}),
        ('Meta', {'fields': ('created_at',)}),
    )

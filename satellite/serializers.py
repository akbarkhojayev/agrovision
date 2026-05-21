from rest_framework import serializers
from .models import AnalysisResult


class AnalysisListSerializer(serializers.ModelSerializer):
    ndvi_label = serializers.ReadOnlyField()

    class Meta:
        model  = AnalysisResult
        fields = [
            'id', 'created_at', 'name', 'center_lat', 'center_lng',
            'area_ha', 'ndvi_current', 'ndwi_current', 'ndvi_change',
            'drought_index', 'ndvi_label',
        ]


class AnalysisDetailSerializer(serializers.ModelSerializer):
    ndvi_label = serializers.ReadOnlyField()

    class Meta:
        model  = AnalysisResult
        fields = '__all__'

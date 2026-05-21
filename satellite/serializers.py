from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Field, AnalysisResult


# ── Auth serializers ──────────────────────────────────────────────────────────

class RegisterSerializer(serializers.Serializer):
    username   = serializers.CharField(max_length=150)
    password   = serializers.CharField(min_length=6, write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, default='')
    email      = serializers.EmailField(required=False, default='')

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Bu username band, boshqa tanlang.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            email=validated_data.get('email', ''),
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'username', 'first_name', 'email', 'date_joined']


# ── Field serializers ─────────────────────────────────────────────────────────

class FieldSerializer(serializers.ModelSerializer):
    area_sotix = serializers.ReadOnlyField()

    class Meta:
        model  = Field
        fields = [
            'id', 'created_at', 'updated_at',
            'name', 'crop', 'coordinates',
            'center_lat', 'center_lng',
            'area_ha', 'area_sotix',
            'last_irrigation', 'water_cycle', 'notes',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'area_sotix']


class FieldMiniSerializer(serializers.ModelSerializer):
    """Tahlil ichiga embed qilinadigan yengil variant."""
    area_sotix = serializers.ReadOnlyField()

    class Meta:
        model  = Field
        fields = ['id', 'name', 'crop', 'area_ha', 'area_sotix', 'last_irrigation', 'water_cycle']


class FieldWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Field
        fields = [
            'name', 'crop', 'coordinates',
            'center_lat', 'center_lng',
            'area_ha', 'last_irrigation', 'water_cycle', 'notes',
        ]

    def validate_coordinates(self, value):
        if not isinstance(value, list) or len(value) < 3:
            raise serializers.ValidationError("Kamida 3 ta koordinata bo'lishi kerak.")
        for p in value:
            if not isinstance(p, dict) or 'lat' not in p or 'lng' not in p:
                raise serializers.ValidationError("Har bir nuqtada 'lat' va 'lng' bo'lishi kerak.")
        return value


# ── AnalysisResult serializers ────────────────────────────────────────────────

class AnalysisListSerializer(serializers.ModelSerializer):
    ndvi_label = serializers.ReadOnlyField()
    field      = FieldMiniSerializer(read_only=True)

    class Meta:
        model  = AnalysisResult
        fields = [
            'id', 'created_at', 'name',
            'field',
            'center_lat', 'center_lng',
            'area_ha', 'ndvi_current', 'ndwi_current', 'ndvi_change',
            'drought_index', 'ndvi_label',
        ]


class AnalysisDetailSerializer(serializers.ModelSerializer):
    ndvi_label = serializers.ReadOnlyField()
    field      = FieldMiniSerializer(read_only=True)

    class Meta:
        model  = AnalysisResult
        fields = '__all__'

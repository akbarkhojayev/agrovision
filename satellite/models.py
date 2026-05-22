from django.contrib.auth.models import User
from django.db import models


class Field(models.Model):
    user            = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='fields',
        verbose_name="Foydalanuvchi",
    )
    created_at      = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan")
    updated_at      = models.DateTimeField(auto_now=True,     verbose_name="Yangilangan")
    name            = models.CharField(max_length=200, blank=True, verbose_name="Dala nomi")
    crop            = models.CharField(max_length=100, default='', blank=True, verbose_name="Ekin turi")
    coordinates     = models.JSONField(verbose_name="Polygon koordinatalari")
    center_lat      = models.FloatField(verbose_name="Markaz kenglik")
    center_lng      = models.FloatField(verbose_name="Markaz uzunlik")
    area_ha         = models.FloatField(null=True, blank=True, verbose_name="Maydon (ha)")
    notes           = models.TextField(blank=True, verbose_name="Izoh")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Dala"
        verbose_name_plural = "Dalalar"

    def __str__(self):
        label = self.name or f"Dala {self.pk}"
        return f"{label} — {self.crop} ({self.center_lat:.3f}, {self.center_lng:.3f})"

    @property
    def area_sotix(self):
        if self.area_ha is None:
            return None
        return round(self.area_ha * 100, 1)


class AnalysisResult(models.Model):
    user          = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='analyses',
        verbose_name="Foydalanuvchi",
    )
    field         = models.ForeignKey(
        Field,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='analyses',
        verbose_name="Dala",
    )
    created_at    = models.DateTimeField(auto_now_add=True)
    name          = models.CharField(max_length=200, blank=True, verbose_name="Nomi")
    center_lat    = models.FloatField(verbose_name="Kenglik")
    center_lng    = models.FloatField(verbose_name="Uzunlik")
    area_ha       = models.FloatField(null=True, blank=True, verbose_name="Maydon (ha)")
    coordinates   = models.JSONField(verbose_name="Koordinatalar")

    ndvi_current  = models.FloatField(verbose_name="Joriy NDVI")
    ndvi_change   = models.FloatField(verbose_name="NDVI o'zgarishi")
    ndvi_monthly  = models.JSONField(verbose_name="Oylik NDVI")
    drought_index = models.FloatField(default=0, verbose_name="Qurg'oqchilik indeksi")
    ndwi_current  = models.FloatField(null=True, blank=True, default=None,
                                      verbose_name="Joriy NDWI")

    soil_data       = models.JSONField(default=dict, verbose_name="Tuproq ma'lumoti")
    soil_properties = models.JSONField(default=dict, verbose_name="Tuproq kimyosi (SoilGrids)")
    weather_data  = models.JSONField(default=dict, verbose_name="Ob-havo tarixi")
    ai_analysis   = models.JSONField(default=dict, verbose_name="AI tahlili")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Tahlil natijasi"
        verbose_name_plural = "Tahlil natijalari"

    def __str__(self):
        label = self.name or f"Tahlil {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        return f"{label} ({self.center_lat:.3f}, {self.center_lng:.3f})"

    @property
    def ndvi_label(self):
        v = self.ndvi_current
        if v >= 0.6:  return "Sich o'simlik"
        if v >= 0.3:  return "O'rtacha"
        if v >= 0.1:  return "Siyrak"
        return "Quruq/beton"


class CropImage(models.Model):
    """Mahsulot rasmlari va ularning tahlili"""
    user          = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='crop_images',
        verbose_name="Foydalanuvchi",
    )
    field         = models.ForeignKey(
        Field,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='crop_images',
        verbose_name="Dala",
    )
    created_at    = models.DateTimeField(auto_now_add=True, verbose_name="Yuklangan vaqti")
    image         = models.ImageField(upload_to='crop_images/', verbose_name="Rasm")
    
    # Tahlil natijalari
    health_status = models.CharField(
        max_length=50, blank=True,
        choices=[
            ('healthy', 'Sog\'lig\'i yaxshi'),
            ('moderate', 'O\'rtacha'),
            ('poor', 'Yomon'),
            ('critical', 'Juda yomon'),
        ],
        verbose_name="Sog\'lig\'i holati"
    )
    diseases      = models.JSONField(default=list, verbose_name="Aniqlab olingan kasalliklar")
    analysis      = models.JSONField(default=dict, verbose_name="Batafsil tahlil")
    confidence    = models.FloatField(default=0.0, verbose_name="Ishonch darajasi (0-1)")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Mahsulot rasmi"
        verbose_name_plural = "Mahsulot rasmlari"

    def __str__(self):
        return f"Rasm {self.created_at.strftime('%Y-%m-%d %H:%M')} — {self.health_status}"

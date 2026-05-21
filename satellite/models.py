from django.db import models


class AnalysisResult(models.Model):
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

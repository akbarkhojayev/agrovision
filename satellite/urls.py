from django.urls import path
from . import views

urlpatterns = [
    path('', views.FrontendView.as_view(), name='frontend'),
    path('api/satellite/analyze/',          views.SatelliteAnalyzeView.as_view()),
    path('api/satellite/history/',          views.AnalysisHistoryView.as_view()),
    path('api/satellite/history/<int:pk>/', views.AnalysisDetailView.as_view()),
]

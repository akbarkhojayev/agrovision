from django.urls import path
from . import views

urlpatterns = [
    path('', views.FrontendView.as_view(), name='frontend'),

    # Auth
    path('api/auth/register/', views.RegisterView.as_view()),
    path('api/auth/login/',    views.LoginView.as_view()),
    path('api/auth/logout/',   views.LogoutView.as_view()),
    path('api/auth/me/',       views.MeView.as_view()),

    # Tahlil
    path('api/satellite/analyze/',          views.SatelliteAnalyzeView.as_view()),

    # Tahlil tarixi
    path('api/satellite/history/',          views.AnalysisHistoryView.as_view()),
    path('api/satellite/history/<int:pk>/', views.AnalysisDetailView.as_view()),

    # Dalalar (CRUD)
    path('api/satellite/fields/',                   views.FieldListCreateView.as_view()),
    path('api/satellite/fields/<int:pk>/',          views.FieldDetailView.as_view()),
    path('api/satellite/fields/<int:pk>/analyses/', views.FieldAnalysesView.as_view()),
]

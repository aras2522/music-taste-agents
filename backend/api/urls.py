from django.urls import path

from .views import HealthView, RecommendView

urlpatterns = [
    path("health", HealthView.as_view(), name="api-health"),
    path("recommend", RecommendView.as_view(), name="api-recommend"),
]

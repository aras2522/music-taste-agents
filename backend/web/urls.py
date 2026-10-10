from django.urls import path, re_path

from .views import AboutView, HomeView, ReactAppView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("about/", AboutView.as_view(), name="about"),
    path("app/", ReactAppView.as_view(), name="react-app"),
    re_path(r"^app/(?P<resource>.+)$", ReactAppView.as_view(), name="react-asset"),
]

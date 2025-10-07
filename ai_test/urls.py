from django.contrib import admin
from django.urls import path, include  # 'include' import karna zaroori hai

urlpatterns = [
    path("admin/", admin.site.urls),
    # Root URL (/) par request 'app' ke urls.py mein bhej do
    path("", include("app.urls")),
    path('test/', include('user_tests.urls')), 

]

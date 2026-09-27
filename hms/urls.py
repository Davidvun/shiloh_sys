from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from core.views import custom_404

handler404 = custom_404

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('patients/', include('patients.urls')),
    path('billing/', include('billing.urls')),
    path('clinical/', include('clinical.urls')),
    path('laboratory/', include('laboratory.urls')),
    path('admissions/', include('admissions.urls')),
    path('audit/', include('audit.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + [
    re_path(r'^.*$', custom_404),
]

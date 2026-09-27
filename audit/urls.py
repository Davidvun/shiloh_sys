from django.urls import path
from . import views

urlpatterns = [
    path('changes/', views.change_request_list, name='change_request_list'),
    path('changes/<int:pk>/review/', views.change_request_review, name='change_request_review'),
    path('logs/', views.audit_log, name='audit_log'),
]

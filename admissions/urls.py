from django.urls import path
from . import views

urlpatterns = [
    path('', views.admission_list, name='admission_list'),
    path('admit/<int:visit_pk>/', views.admission_create, name='admission_create'),
    path('discharge/<int:visit_pk>/', views.patient_discharge, name='patient_discharge'),
]

from django.urls import path
from . import views

urlpatterns = [
    path('triage/<int:visit_pk>/', views.triage_create, name='triage_create'),
    path('consultation/<int:visit_pk>/', views.consultation_create, name='consultation_create'),
    path('consultation/<int:visit_pk>/step2/', views.consultation_step2, name='consultation_step2'),
    path('consultation/<int:visit_pk>/edit/', views.consultation_edit, name='consultation_edit'),
    path('records/', views.doctor_records, name='doctor_records'),
]

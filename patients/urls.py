from django.urls import path
from . import views

urlpatterns = [
    path('', views.patient_list, name='patient_list'),
    path('register/', views.patient_register, name='patient_register'),
    path('<int:pk>/', views.patient_detail, name='patient_detail'),
    path('<int:pk>/edit/', views.patient_edit, name='patient_edit'),
    path('<int:pk>/delete/', views.patient_delete, name='patient_delete'),
    path('<int:pk>/edit-request/', views.patient_edit_request, name='patient_edit_request'),
    path('<int:pk>/delete-request/', views.patient_delete_request, name='patient_delete_request'),
    path('<int:patient_pk>/visit/create/', views.visit_create, name='visit_create'),
    path('visit/<int:pk>/', views.visit_detail, name='visit_detail'),
]

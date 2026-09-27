from django.urls import path
from . import views

urlpatterns = [
    path('queue/', views.lab_queue, name='lab_queue'),
    path('queue/visit/<int:visit_pk>/', views.lab_queue_visit, name='lab_queue_visit'),
    path('completed/', views.lab_completed, name='lab_completed'),
    path('request/<int:visit_pk>/', views.lab_request_create, name='lab_request_create'),
    path('request/<int:pk>/cancel/', views.lab_request_cancel, name='lab_request_cancel'),
    path('result/<int:lab_pk>/', views.lab_result_upload, name='lab_result_upload'),
    path('result/<int:lab_pk>/edit/', views.lab_result_edit, name='lab_result_edit'),
    # Admin catalog
    path('catalog/', views.lab_catalog, name='lab_catalog'),
    path('catalog/category/create/', views.lab_category_create, name='lab_category_create'),
    path('catalog/category/<int:pk>/toggle/', views.lab_category_toggle, name='lab_category_toggle'),
    path('catalog/category/<int:pk>/delete/', views.lab_category_delete, name='lab_category_delete'),
    path('catalog/test/create/', views.lab_test_create, name='lab_test_create'),
    path('catalog/test/<int:pk>/edit/', views.lab_test_edit, name='lab_test_edit'),
    path('catalog/test/<int:pk>/toggle/', views.lab_test_toggle, name='lab_test_toggle'),
    path('catalog/test/<int:pk>/delete/', views.lab_test_delete, name='lab_test_delete'),
    path('catalog/test/<int:test_pk>/component/create/', views.lab_test_parameter_create, name='lab_test_parameter_create'),
    path('catalog/component/<int:pk>/delete/', views.lab_test_parameter_delete, name='lab_test_parameter_delete'),
]

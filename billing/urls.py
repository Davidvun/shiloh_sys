from django.urls import path
from . import views

urlpatterns = [
    path('', views.billing_dashboard, name='billing_dashboard'),
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/create/<int:visit_pk>/', views.payment_create, name='payment_create'),
    path('payments/<int:pk>/receipt/', views.payment_receipt, name='payment_receipt'),
    path('payments/<int:pk>/revoke/', views.payment_revoke, name='payment_revoke'),
    path('admin/revoked-payments/', views.revoked_payments_admin, name='revoked_payments_admin'),
    # Supplies billing
    path('supplies/', views.supplies_billing_list, name='supplies_billing_list'),
    path('supplies/visit/<int:visit_pk>/', views.supplies_billing_visit, name='supplies_billing_visit'),
    path('supplies/visit/<int:visit_pk>/pay/', views.supplies_bulk_payment_create, name='supplies_bulk_payment_create'),
    # Lab billing — grouped by patient/visit
    path('labs/', views.lab_billing_list, name='lab_billing_list'),
    path('labs/visit/<int:visit_pk>/', views.lab_billing_visit, name='lab_billing_visit'),
    path('labs/visit/<int:visit_pk>/pay/', views.lab_bulk_payment_create, name='lab_bulk_payment_create'),
    # Pending billing — unified view per patient/visit
    path('pending/', views.pending_billing_list, name='pending_billing_list'),
    path('pending/visit/<int:visit_pk>/', views.pending_billing_visit, name='pending_billing_visit'),
    path('pending/visit/<int:visit_pk>/pay-all/', views.combined_payment_create, name='combined_payment_create'),
]

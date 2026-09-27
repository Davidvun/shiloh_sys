from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('set-my-language/', views.set_my_language, name='set_my_language'),
    path('dashboard/', views.dashboard, name='dashboard'),
    # Users
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/toggle/', views.user_toggle, name='user_toggle'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:pk>/reset-password/', views.user_reset_password, name='user_reset_password'),
    path('change-password/', views.change_password, name='change_password'),
    path('my-profile/', views.my_profile, name='my_profile'),
    path('reports/', views.admin_reports, name='admin_reports'),
    # Settings
    path('settings/', views.hospital_settings, name='hospital_settings'),
    # Specialist Fees
    path('settings/specialist-fees/add/', views.specialist_fee_create, name='specialist_fee_create'),
    path('settings/specialist-fees/<int:pk>/edit/', views.specialist_fee_edit, name='specialist_fee_edit'),
    path('settings/specialist-fees/<int:pk>/delete/', views.specialist_fee_delete, name='specialist_fee_delete'),
    # Forms Library
    path('forms/', views.forms_library, name='forms_library'),
    path('forms/upload/', views.form_upload, name='form_upload'),
    path('forms/<int:pk>/delete/', views.form_delete, name='form_delete'),
    path('forms/<int:pk>/toggle/', views.form_toggle, name='form_toggle'),
    # Consumables / Supplies Catalogue
    path('consumables/', views.consumables_list, name='consumables_list'),
    path('consumables/create/', views.consumable_create, name='consumable_create'),
    path('consumables/<int:pk>/edit/', views.consumable_edit, name='consumable_edit'),
    path('consumables/<int:pk>/toggle/', views.consumable_toggle, name='consumable_toggle'),
    path('consumables/<int:pk>/delete/', views.consumable_delete, name='consumable_delete'),
    # Visit consumables (add/remove items to a visit)
    path('visits/<int:visit_pk>/consumables/add/', views.visit_consumable_add, name='visit_consumable_add'),
    path('visits/<int:visit_pk>/consumables/<int:vc_pk>/remove/', views.visit_consumable_remove, name='visit_consumable_remove'),
    # Insurance
    path('insurance/', views.insurance_list, name='insurance_list'),
    path('insurance/create/', views.insurance_create, name='insurance_create'),
    path('insurance/<int:pk>/edit/', views.insurance_edit, name='insurance_edit'),
    path('insurance/<int:pk>/delete/', views.insurance_delete, name='insurance_delete'),
]

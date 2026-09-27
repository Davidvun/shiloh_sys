from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Insurance

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'get_full_name', 'role', 'is_active']
    list_filter = ['role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (('Role', {'fields': ('role', 'phone', 'is_deleted')}),)

@admin.register(Insurance)
class InsuranceAdmin(admin.ModelAdmin):
    list_display = ['name', 'coverage_percentage', 'is_active']

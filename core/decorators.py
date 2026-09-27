from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in roles and request.user.role != 'admin':
                messages.error(request, "Access denied: insufficient permissions.")
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role != 'admin':
            messages.error(request, "Admin access required.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapped


def login_required_custom(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapped

from django.shortcuts import redirect
from django.urls import reverse
from django.utils import translation
from audit.models import AuditLog

FORCE_CHANGE_EXEMPT = None  # resolved lazily


class HMSLanguageMiddleware:
    """Activate the system language set in HospitalSettings for every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = 'en'
        try:
            from core.models import HospitalSettings
            hs = HospitalSettings.get()
            lang = hs.language or 'en'
        except Exception:
            pass
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            user_lang = getattr(user, 'preferred_language', '') or ''
            if user_lang:
                lang = user_lang
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        response = self.get_response(request)
        translation.deactivate()
        return response


class ForcePasswordChangeMiddleware:
    """Redirect users who must change their password before they can do anything else."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, 'must_change_password', False):
            change_url = reverse('change_password')
            exempt = {change_url, reverse('logout')}
            if request.path not in exempt:
                return redirect(change_url)
        return self.get_response(request)


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated and request.method in ['POST', 'PUT', 'DELETE']:
            ip = self.get_client_ip(request)
            try:
                AuditLog.objects.create(
                    user=request.user,
                    action=request.method,
                    model_name='HTTP',
                    object_id='',
                    description=f"{request.method} {request.path}",
                    ip_address=ip,
                )
            except Exception:
                pass
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')

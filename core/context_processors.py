from audit.models import ChangeRequest, ChangeRequestStatus

def pending_changes(request):
    count = 0
    currency = 'CDF'
    hospital_logo_url = ''
    hospital_name = 'Hospital'
    logo_size_px = '80px'
    s = None
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            count = ChangeRequest.objects.filter(status=ChangeRequestStatus.PENDING).count()
        try:
            from core.models import HospitalSettings
            s = HospitalSettings.get()
            currency = s.currency or 'CDF'
            hospital_name = s.hospital_name or 'Hospital'
            if s.logo:
                hospital_logo_url = s.logo.url
        except Exception:
            s = None
        logo_size_map = {'small': '48px', 'medium': '80px', 'large': '128px'}
        logo_size_px = logo_size_map.get(getattr(s, 'logo_size', 'medium'), '80px') if s else '80px'
    return {
        'pending_change_count': count,
        'currency': currency,
        'hospital_logo_url': hospital_logo_url,
        'hospital_name': hospital_name,
        'logo_size_px': logo_size_px,
    }

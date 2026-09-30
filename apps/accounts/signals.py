def create_staff_profile(sender, instance, created, raw=False, **kwargs):
    """Every user gets a staff profile, including superusers made with createsuperuser."""
    if raw:
        return
    from .models import StaffProfile

    StaffProfile.objects.get_or_create(user=instance)

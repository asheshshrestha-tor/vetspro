def create_staff_profile(sender, instance, created, raw=False, **kwargs):
    """Every user gets a staff profile, including superusers made with createsuperuser."""
    if raw:
        return
    from .models import StaffProfile

    profile, made = StaffProfile.objects.get_or_create(user=instance)
    if made:
        # With a single branch there is nothing to choose, so new staff work there.
        from apps.branches.models import Branch

        branches = list(Branch.objects.filter(is_active=True)[:2])
        if len(branches) == 1:
            profile.default_branch = branches[0]
            profile.save(update_fields=["default_branch"])
            profile.branches.add(branches[0])

"""Who may do what with an appointment, on top of the plain model permissions."""


def can_view_clinical(user):
    return user.has_perm("appointments.view_clinical") or user.has_perm("appointments.record_clinical")


def can_record_clinical(user):
    return user.has_perm("appointments.record_clinical")


def can_edit_completed(user):
    return user.has_perm("appointments.change_completed_appointment")


def can_change(user, appointment=None):
    if not user.has_perm("appointments.change_appointment"):
        return False
    if appointment is not None and appointment.is_locked:
        # Cancelled visits are only restored, never edited; completed ones need the extra permission.
        return appointment.status == appointment.COMPLETED and can_edit_completed(user)
    return True


def can_apply(user, appointment, action):
    if not appointment.can_apply(action) or not user.has_perm("appointments.change_appointment"):
        return False
    if action == "complete":
        return can_record_clinical(user)
    if action == "reopen":
        return can_edit_completed(user)
    return True

"""Record changes made by people using the site.

Changes made outside a request (migrations, commands, tests without a client) are not logged.
"""
import datetime
import decimal
import uuid

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save

from .middleware import current_request

# Apps whose records are logged.
TRACKED_APPS = {
    "core", "services", "team", "pricing", "faq", "gallery", "testimonials",
    "clinic_setup", "clients", "appointments", "accounts", "shop", "billing", "branches", "messaging", "auth",
}
# Records that are already a log, or change too often to be useful here.
SKIPPED_MODELS = {
    ("shop", "stockmovement"), ("shop", "branchstock"), ("messaging", "outboundmessage"),
    ("contact", "contactmessage"), ("auth", "permission"),
}
SKIPPED_FIELDS = {"created_at", "updated_at", "last_login", "phone_digits", "slug", "line_total"}
HIDDEN_FIELDS = {"password"}


def tracked(model):
    meta = model._meta
    return (
        meta.app_label in TRACKED_APPS
        and (meta.app_label, meta.model_name) not in SKIPPED_MODELS
        and not meta.auto_created
    )


def plain(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (decimal.Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    if hasattr(value, "name"):  # files
        return value.name or ""
    return str(value)


def snapshot(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in SKIPPED_FIELDS:
            continue
        values[field.name] = plain(getattr(instance, field.attname))
    return values


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def write(action, request, user=None, instance=None, changes=None, username=""):
    from apps.branches.context import SESSION_KEY

    from .models import ActivityLog

    user = user if user is not None else getattr(request, "user", None)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    branch_id = None
    session = getattr(request, "session", None)
    if session is not None:
        value = str(session.get(SESSION_KEY, ""))
        branch_id = int(value) if value.isdigit() else None
    entry = ActivityLog(
        user=user,
        username=username or (user.get_username() if user else ""),
        action=action,
        changes=changes or {},
        ip_address=client_ip(request) if request is not None else None,
        branch_id=branch_id,
    )
    if instance is not None:
        meta = instance._meta
        entry.app_label = meta.app_label
        entry.model_name = str(meta.verbose_name)
        entry.object_id = str(instance.pk or "")
        entry.object_repr = str(instance)[:200]
    try:
        entry.save()
    except Exception:  # noqa: BLE001 - logging must never stop the change itself
        pass


def signed_in_request():
    """The request being handled, if a signed-in person made it. Visitors' side effects are not logged."""
    request = current_request()
    user = getattr(request, "user", None)
    return request if user is not None and user.is_authenticated else None


def remember_old(sender, instance, raw=False, **kwargs):
    if raw or not tracked(sender) or signed_in_request() is None or instance.pk is None:
        return
    old = sender._base_manager.filter(pk=instance.pk).first()
    instance._activity_before = snapshot(old) if old is not None else None


def log_save(sender, instance, created, raw=False, **kwargs):
    request = signed_in_request()
    if raw or request is None or not tracked(sender):
        return
    after = snapshot(instance)
    if created:
        changes = {name: [None, value] for name, value in after.items() if value not in (None, "", False)}
        action = "create"
    else:
        before = getattr(instance, "_activity_before", None) or {}
        changes = {name: [before.get(name), value] for name, value in after.items() if before.get(name) != value}
        if not changes:
            return
        action = "update"
    for name in HIDDEN_FIELDS & changes.keys():
        changes[name] = ["•••", "changed"]
    write(action, request, instance=instance, changes=changes)


def log_delete(sender, instance, **kwargs):
    request = signed_in_request()
    if request is None or not tracked(sender):
        return
    write("delete", request, instance=instance, changes={})


def log_login(sender, request, user, **kwargs):
    write("login", request, user=user)


def log_logout(sender, request, user, **kwargs):
    if user is not None:
        write("logout", request, user=user)


def log_login_failed(sender, credentials, request=None, **kwargs):
    if request is not None:
        write("login_failed", request, username=str(credentials.get("username", ""))[:150])


def connect():
    pre_save.connect(remember_old, dispatch_uid="activity_pre_save")
    post_save.connect(log_save, dispatch_uid="activity_post_save")
    post_delete.connect(log_delete, dispatch_uid="activity_post_delete")
    user_logged_in.connect(log_login, dispatch_uid="activity_login")
    user_logged_out.connect(log_logout, dispatch_uid="activity_logout")
    user_login_failed.connect(log_login_failed, dispatch_uid="activity_login_failed")


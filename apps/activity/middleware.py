import threading

_state = threading.local()


def current_request():
    return getattr(_state, "request", None)


class CurrentRequestMiddleware:
    """Remembers the request being handled, so saved records can be logged against the person."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.request = request
        try:
            return self.get_response(request)
        finally:
            _state.request = None

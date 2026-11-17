"""API package with lazy application loading."""

__all__ = ["app"]


def __getattr__(name):
    if name == "app":
        from .app import app
        return app
    raise AttributeError(name)

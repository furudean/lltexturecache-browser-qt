try:
    from lltexturecache_browser_qt._meta import APP_DISPLAY_NAME as APP_DISPLAY_NAME
    from lltexturecache_browser_qt._meta import APP_NAME as APP_NAME
    from lltexturecache_browser_qt._meta import __version__ as __version__
except ImportError:
    # fallback
    APP_NAME = __name__
    APP_DISPLAY_NAME = __name__
    __version__ = "0.0.0-dev"

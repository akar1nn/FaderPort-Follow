"""An independent native-mode FaderPort V2 control surface for Live 12."""

__version__ = "1.0.0"


def create_instance(c_instance):
    # Delay the Live-only import so protocol and behavior tests run outside Live.
    from .surface import FaderPortFollow
    return FaderPortFollow(c_instance)


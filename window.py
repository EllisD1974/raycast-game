"""Window helpers shared by the game and the map editor."""
import pygame


def maximize(window=None):
    """Maximize `window` (a pygame.Window), or the window pygame.display opened, if the platform lets us.
    Returns True if it did.

    Needs pygame-ce's Window API. Anywhere it is missing or refused (some headless drivers),
    the window just stays at its normal size, which is fine.
    """
    try:
        (window or pygame.Window.from_display_module()).maximize()
        return True
    except Exception:
        return False

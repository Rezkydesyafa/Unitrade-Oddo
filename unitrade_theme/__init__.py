# UniTrade Theme Module
from . import models
from . import controllers


def post_init_hook(env):
    """Set Rupiah currency on fresh install."""
    env['res.company']._unitrade_enforce_idr_currency()

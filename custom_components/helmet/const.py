"""Constants for the Helmet library loans integration."""

from datetime import timedelta

DOMAIN = "helmet"
BASE_URL = "https://helmet.finna.fi"
LIBRARY_TARGET = "helmet"
UPDATE_INTERVAL = timedelta(hours=6)
# Keep in sync with manifest.json; also busts the browser cache for the cards.
VERSION = "0.2.1"

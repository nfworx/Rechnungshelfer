"""Zentrale, spaeter leicht austauschbare Produktmetadaten."""

from version import __version__


# APP_ID wird fuer technische Pfade und Dateinamen verwendet. Nach der ersten
# oeffentlichen Version sollte sie nur noch mit einer Datenmigration geaendert
# werden. APP_NAME darf dagegen als sichtbarer Produktname angepasst werden.
APP_NAME = "Rechnungshelfer"
APP_ID = "Rechnungshelfer"
APP_EXECUTABLE_NAME = APP_ID
APP_VERSION = __version__
APP_PUBLISHER = "nfischer-code"
APP_DESCRIPTION = "Rechnungen und Gutschriften erstellen, verwalten und validieren"

DATA_DIR_ENV = "RECHNUNGSHELFER_DATA_DIR"
MAINTAINER_MODE_ENV = "RECHNUNGSHELFER_MAINTAINER"

# Oeffentliche Releasequelle fuer den Online-Updatecheck der Benutzeranwendung.
UPDATE_RELEASE_API_URL = "https://api.github.com/repos/nfworx/Rechnungshelfer/releases/latest"
UPDATE_CHANNEL = "stable"

"""Package only the Babel locale data used by Rechnungshelfer."""

from pathlib import Path

from PyInstaller.utils.hooks import get_package_paths


_, babel_package = get_package_paths("babel")
babel_package = Path(babel_package)

datas = [
    (str(babel_package / "global.dat"), "babel"),
    *(
        (str(babel_package / "locale-data" / filename), "babel/locale-data")
        for filename in ("root.dat", "de.dat", "de_DE.dat")
    ),
]

# Loading the pickled locale data requires these modules at runtime.
hiddenimports = [
    "babel.dates",
    "babel.localedata",
    "babel.plural",
    "babel.numbers",
]

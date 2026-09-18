# Music Chooser

A local-only music discovery app that uses Metacritic album metadata to build a weekly five-album listening set.

## Quick start

Python 3.12+ is required.

After the first-time setup, the app can be launched with `start.cmd`.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
music-chooser
```

For a simpler Windows launch, run this from PowerShell or double-click `start.cmd`:

```powershell
.\start.cmd
```

The launcher creates the virtual environment if needed, installs the project dependencies, and starts the app without requiring PowerShell script activation.

Open <http://127.0.0.1:8000>.

The default database is `.music-chooser/music-chooser.db`. The app does not make network requests at startup. Recent releases are fetched only when you explicitly use the refresh action. Historical pages are imported only from explicitly approved URLs.

Useful environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MUSIC_CHOOSER_DB` | `.music-chooser/music-chooser.db` | SQLite path |
| `MUSIC_CHOOSER_TIMEZONE` | `Australia/Sydney` | Calendar-window timezone |
| `MUSIC_CHOOSER_REFRESH_HOURS` | `24` | Automatic refresh interval |
| `MUSIC_CHOOSER_REQUEST_DELAY` | `2` | Minimum seconds between requests |
| `MUSIC_CHOOSER_AUTO_SYNC` | `0` | Optional startup sync; disabled by default |

The application does not persist fetched HTML. It retains parsed album metadata, including the listing description, and fetch timestamps only.

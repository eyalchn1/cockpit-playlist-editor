# Windows executable

Run `build-windows.cmd` from Windows with Python installed on the build machine.
The script creates `.venv` if needed, installs the pinned runtime and build
dependencies, and builds using `Cockpit Playlist Editor.spec`.

Output: `dist\Cockpit Playlist Editor.exe`. Copy this file alone to the target
computer; Python, VS Code, and `.venv` are not required there. This is a
PyInstaller single-file GUI build, with Python, PySide6, and the required Qt
plugins bundled. It does not open a console window or require elevation.

The executable extracts its runtime to a temporary folder at startup, so the
first launch can take several seconds. Keep the executable in a user-writable
folder: preferences are stored in `.user-settings.ini` beside it, preserving
the application's existing portable settings behavior. To carry existing
preferences over, copy that INI file beside the executable too. Preferences
are not embedded in the build.

Build on the Windows architecture you intend to distribute (the current build
is x64). The executable is unsigned; Windows or antivirus software may warn
about an unfamiliar downloaded executable. Signing is a separate release step.
Generated `build/` and `dist/` folders are ignored by Git.

Run the existing tests after changes:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests using a real playlist require `COCKPIT_TEST_PLAYLIST` to reference a local
fixture; otherwise those tests are skipped.

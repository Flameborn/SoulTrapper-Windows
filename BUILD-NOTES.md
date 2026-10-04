Soul Trapper 1.1 Windows build notes

Runtime: Python 3.12.7 x64, pygame 2.6.1, Unicorn 2.0.1.post1
(the latter reports 2.0.1 through its Python API).

The Unicorn Windows wheel replaces the 2.1.4 wheel used in 1.0. This is
a compatibility change for native crashes during emulator initialization;
it does not change the original game scripts or the save format.
The affected player's machine still needs to confirm the fix.

For Python 3.12, the wheel's unicorn/unicorn.py uses `import sysconfig`
instead of `import distutils.sysconfig`, and `sysconfig.get_path('purelib')`
instead of `distutils.sysconfig.get_python_lib()`. Remove its unused
`import pkg_resources` and the `pkg_resources.resource_filename` search
entry. The next existing search entry already resolves the wheel's lib
directory relative to __file__. The native DLLs are unmodified.

Compile Launcher.cs as a Windows executable referencing System.Windows.Forms,
with Launcher.manifest passed to the compiler's /win32manifest option.
The supportedOS declaration prevents the launcher from reporting Windows 10
as NT 6.2. Python's Windows version and the emulator version also appear in
captured startup output if the launcher needs to write error.log.

Periodic autosaves now use a single background writer, without pausing audio.
Save loading and shutdown wait for pending writes; write failures are reported
through the existing error handler. Manual saves still finish before confirmation.
The mixer buffer is 2048 frames instead of 512 to provide more headroom.

Save files remain compatible with 1.0. When updating, keep the existing saves
folder beside Soul Trapper.exe, or copy it into the new extracted game folder.

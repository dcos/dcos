# Warning:
#   - hidden import must be used as there is a bug in pyinstaller
#     https://github.com/pyinstaller/pyinstaller/issues/2185
#   - data must be decalared explicitly if not a .py file
#   - Building will suck up the local SSL .so and package it
#     with the final exe. Ensure build system has OpenSSL 1.0.2g or greater
a = Analysis(['test_util/launch_cli.py'],
             hiddenimports=['html.parser'],
             datas=[('gen/ip-detect/*.sh', 'gen/ip-detect/')])
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='dcos-launch',
    debug=False,
    strip=False,
    upx=True,
    console=True)

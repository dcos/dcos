a = Analysis(['spaceport/cli.py'])
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='dcos-spaceport',
    debug=False,
    strip=False,
    upx=True,
    console=True)

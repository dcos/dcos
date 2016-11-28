a = Analysis(['test_util/launch.py'])
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

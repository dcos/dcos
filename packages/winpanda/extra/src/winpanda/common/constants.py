"""Panda package management for Windows.

Application-wide constant objects.
"""
# Application
APP_NAME = 'winpanda'
APP_LOG_FNAME = f'{APP_NAME}.log'
APP_LOG_FSIZE_MAX = 1048576  # 1 MiB
APP_LOG_HSIZE_MAX = 10       # Log file history max size

# DC/OS distribution storage URL
DCOS_DSTOR_URL_DFT = 'https://wintesting.s3.amazonaws.com'
# DC/OS distribution storage package repository path
DCOS_DSTOR_PKGREPO_PATH_DFT = 'testing/packages'



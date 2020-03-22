"""Panda package management for Windows.

Application-wide constant objects.
"""
import logging

# Application
APP_NAME = 'winpanda'
APP_LOG_LEVEL_DFT = logging.INFO
APP_LOG_FNAME = f'{APP_NAME}.log'
APP_LOG_FSIZE_MAX = 10485760  # 10 MiB
APP_LOG_HSIZE_MAX = 10       # Log file history max size

DCOS_CLUSTER_CFG_FNAME_DFT = 'cluster.conf'
ZK_CLIENTPORT_DFT = 2181

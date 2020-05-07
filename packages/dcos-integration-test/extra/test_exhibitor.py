import os

import pytest


class TestExhibitor:

    def test_permissions(self) -> None:
        """
        ZooKeeper data files are not accessible
        """
        # Verify that a parent directory exists
        assert os.path.isdir('/var/lib/dcos/exhibitor/zookeeper')
        # Verify that snapshots and transaction logs are not accessible
        with pytest.raises(PermissionError):
            os.listdir('/var/lib/dcos/exhibitor/zookeeper/snapshot')
        with pytest.raises(PermissionError):
            os.listdir('/var/lib/dcos/exhibitor/zookeeper/transactions')

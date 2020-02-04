import json
import uuid

import pytest
from dcos_test_utils.enterprise import EnterpriseApiSession
from dcos_test_utils.etcd import EtcdCtl, is_enterprise


class TestEtcdctlOpen:
    def test_fetching_members(self, dcos_api_session: EnterpriseApiSession) -> None:
        if is_enterprise:
            pytest.skip("not suitable for Enterprise DC/OS")

        etcd_ctl = EtcdCtl()

        cluster_health_cmd = ["member", "list", "-w", "json"]
        p = etcd_ctl.run(cluster_health_cmd, check=True)

        member_info = json.loads(p.stdout.strip())
        members = member_info["members"]
        assert len(members) == len(dcos_api_session.masters)

    def test_write_and_read(self) -> None:
        if is_enterprise:
            pytest.skip("not suitable for Enterprise DC/OS")

        key = "/int-testing/foo-{}".format(uuid.uuid4())
        value = str(uuid.uuid4())

        etcd_ctl = EtcdCtl()

        write_cmd = ["put", key, value]
        etcd_ctl.run(write_cmd, check=True, env={"ETCDCTL_API": "3"})

        read_cmd = ["get", "--print-value-only=true", key]
        p = etcd_ctl.run(read_cmd, check=True, env={"ETCDCTL_API": "3"})

        output = p.stdout.decode('ascii').strip()

        assert value == output

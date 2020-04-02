import contextlib
import subprocess
from argparse import Namespace
from unittest import mock


import etcd_discovery.etcd_discovery as etd
import pytest


@pytest.fixture(scope="function")
def etcdctl_path(tmp_path):
    return tmp_path / "etcdctl_path"  # Just a dummy path


@pytest.fixture(scope="function")
def call_data(etcdctl_path, tmp_path):
    res = {}
    base_args = [
        str(etcdctl_path),
        "--endpoints",
        "http://127.0.0.1:2379",
    ]

    for user in ["root", "calico", "adminrouter"]:
        tmp_args = base_args + ["user", "add", "--no-password", user]
        res["user_add_" + user] = {
            "args":
            tmp_args,
            "action":
            subprocess.CompletedProcess(
                args=tmp_args,
                returncode=0,
                stdout=b'',
                stderr=b'',
            )
        }

    for role in ["calico_prefix", "adminrouter_prefix"]:
        tmp_args = base_args + ["role", "add", role]
        res["role_add_" + role] = {
            "args":
            tmp_args,
            "action":
            subprocess.CompletedProcess(
                args=tmp_args,
                returncode=0,
                stdout=b'',
                stderr=b'',
            )
        }

    for role in ["calico_prefix", "adminrouter_prefix"]:
        tmp_args = base_args + ["role", "add", role]
        res["role_add_" + role] = {
            "args":
            tmp_args,
            "action":
            subprocess.CompletedProcess(
                args=tmp_args,
                returncode=0,
                stdout=b'',
                stderr=b'',
            )
        }

    for role_grant in [("root", "root"), ("calico", "calico_prefix"),
                       ("adminrouter", "adminrouter_prefix")]:
        tmp_args = base_args + [
            "user", "grant-role", role_grant[0], role_grant[1]
        ]
        res["role_grant_" + role_grant[0]] = {
            "args":
            tmp_args,
            "action":
            subprocess.CompletedProcess(
                args=tmp_args,
                returncode=0,
                stdout=b'',
                stderr=b'',
            )
        }

    for role_permission in [("calico_prefix", "/calico/"),
                            ("adminrouter_prefix", "/")]:
        tmp_args = base_args + [
            "role", "grant", role_permission[0], "--prefix=true", "readwrite",
            role_permission[1]
        ]
        res["role_permission_" + role_permission[0]] = {
            "args":
            tmp_args,
            "action":
            subprocess.CompletedProcess(
                args=tmp_args,
                returncode=0,
                stdout=b'',
                stderr=b'',
            )
        }

    for name in ["user", "role"]:
        tmp_args = base_args + [name, "list"]
        res[name + "_list"] = {
            "args":
            tmp_args,
            "action":
            subprocess.CompletedProcess(
                args=tmp_args,
                returncode=0,
                stdout=b'',
                stderr=b'',
            )
        }

    tmp_args = base_args + ["auth", "enable"]
    res["auth_enable"] = {
        "args":
        tmp_args,
        "action":
        subprocess.CompletedProcess(
            args=tmp_args,
            returncode=0,
            stdout=b'',
            stderr=b'',
        )
    }

    tmp_args = base_args + ["endpoint", "health"]
    res["endpoint_health"] = {
        "args":
        tmp_args,
        "action":
        subprocess.CompletedProcess(
            args=tmp_args,
            returncode=0,
            stdout=b'',
            stderr=b'',
        )
    }

    tmp_args = base_args + ["member", "list", "-w", "json"]
    res["member_list"] = {
        "args":
        tmp_args,
        "action":
        subprocess.CompletedProcess(
            args=tmp_args,
            returncode=0,
            stdout=b'''{
                         "header": {
                           "cluster_id": 2953241377848662500,
                           "member_id": 4079294043104093700,
                           "raft_term": 17
                         },
                         "members": [
                           {
                             "ID": 1301204472537744000,
                             "name": "etcd-1.1.1.1",
                             "peerURLs": [
                               "https://1.1.1.1:2380"
                             ],
                             "clientURLs": [
                               "http://1.1.1.1:2379",
                               "http://localhost:2379"
                             ]
                           }
                         ]
                       }
            ''',
            stderr=b'',
        )
    }

    tmp_args = base_args + [
        "member", "add", "etcd-1.2.3.4", "--peer-urls=https://1.2.3.4:2380"
    ]
    res["member_add"] = {
        "args":
        tmp_args,
        "action":
        subprocess.CompletedProcess(
            args=tmp_args,
            returncode=0,
            stdout=b'',
            stderr=b'',
        )
    }

    return res


@pytest.fixture(scope="function")
def subprocess_sideeffect(call_data):
    def res(args, stdout, stderr):
        assert stdout is subprocess.PIPE
        assert stderr is subprocess.PIPE

        for k in call_data:
            if call_data[k]["args"] == args:
                return call_data[k]["action"]
        else:
            pytest.fail(
                "unhandled arguments have been passed: {}".format(args))

    return res


@pytest.fixture(scope="function")
def args(tmp_path, etcdctl_path):
    cluster_state_file = tmp_path / "cluster_state_file.txt"
    cluster_nodes_file = tmp_path / "cluster_nodes_file.txt"

    res = Namespace(
        etcd_data_dir=str(etcdctl_path),
        zk_addr="127.0.0.1:2181",
        cluster_state_file=str(cluster_state_file),
        cluster_nodes_file=str(cluster_nodes_file),
        etcdctl_path=str(etcdctl_path),
        secure=False,
        ca_cert="",
        etcd_client_tls_cert="",
        etcd_client_tls_key="",
    )

    return res


class TestJoinCluster:
    def test_etcd_already_initialized(self, etcdctl_path):
        etcdctl_path.mkdir()

        args = Namespace(etcd_data_dir=str(etcdctl_path))

        etd.join_cluster(args)

    def test_happy_path_first_node(self, zk, tmp_path, args):
        detectip_mock = mock.Mock(return_value="1.2.3.4")
        subprocess_mock = mock.MagicMock()

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch('etcd_discovery.etcd_discovery.detect_ip',
                           detectip_mock))
            stack.enter_context(mock.patch('subprocess.run', subprocess_mock))
            etd.join_cluster(args)

        detectip_mock.assert_called_once()
        subprocess_mock.assert_not_called()

    def test_happy_path_subsequent_node(self, zk, tmp_path,
                                        subprocess_sideeffect, call_data,
                                        args):
        this_node = "1.2.3.4"
        active_node = "1.1.1.1"

        zk.set('/etcd/nodes',
               bytes('{{"nodes":["{}"]}}'.format(active_node), "utf8"))

        # Adjust the IP we are expecting
        for k in call_data:
            call_data[k]["args"][2] = "http://{}:2379".format(active_node)
            call_data[k]["action"].args[2] = "http://{}:2379".format(
                active_node)

        detectip_mock = mock.Mock(return_value=this_node)
        subprocess_mock = mock.MagicMock(side_effect=subprocess_sideeffect)

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch('etcd_discovery.etcd_discovery.detect_ip',
                           detectip_mock))
            stack.enter_context(mock.patch('subprocess.run', subprocess_mock))
            etd.join_cluster(args)

        detectip_mock.assert_called_once()
        subprocess_mock.assert_has_calls([
            mock.call(call_data["member_list"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["member_add"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["endpoint_health"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
        ],
                                         any_order=True)  # noqa: E126
        assert subprocess_mock.call_count == 3

    def test_subsequent_node_already_registered(self, zk, tmp_path,
                                                subprocess_sideeffect,
                                                call_data, args):
        this_node = "1.2.3.4"
        active_node = "1.1.1.1"

        zk.set(
            '/etcd/nodes',
            bytes('{{"nodes":["{}", "{}"]}}'.format(this_node, active_node),
                  "utf8"))

        # Adjust the IP we are expecting
        for k in call_data:
            call_data[k]["args"][2] = "http://{}:2379".format(active_node)
            call_data[k]["action"].args[2] = "http://{}:2379".format(
                active_node)

        detectip_mock = mock.Mock(return_value=this_node)
        subprocess_mock = mock.MagicMock(side_effect=subprocess_sideeffect)

        # designated node is choosen basing on the exit status of the
        # `endpoint health` command
        tmp = call_data.pop("endpoint_health")
        call_data["endpoint_health_this_node"] = {
            "args":
            tmp["args"].copy(),
            "action":
            subprocess.CompletedProcess(
                args=tmp["action"].args.copy(),
                returncode=1,
                stdout=b'',
                stderr=b'',
            )
        }
        call_data["endpoint_health_this_node"]["args"][
            2] = "http://{}:2379".format(this_node)
        call_data["endpoint_health_this_node"]["action"].args[
            2] = "http://{}:2379".format(this_node)
        call_data["endpoint_health_active_node"] = {
            "args":
            tmp["args"].copy(),
            "action":
            subprocess.CompletedProcess(
                args=tmp["action"].args.copy(),
                returncode=0,
                stdout=b'',
                stderr=b'',
            )
        }
        call_data["endpoint_health_active_node"]["args"][
            2] = "http://{}:2379".format(active_node)
        call_data["endpoint_health_active_node"]["action"].args[
            2] = "http://{}:2379".format(active_node)

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch('etcd_discovery.etcd_discovery.detect_ip',
                           detectip_mock))
            stack.enter_context(mock.patch('subprocess.run', subprocess_mock))
            etd.join_cluster(args)

        detectip_mock.assert_called_once()
        subprocess_mock.assert_has_calls([
            mock.call(call_data["member_list"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["member_add"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["endpoint_health_active_node"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["endpoint_health_this_node"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
        ],
                                         any_order=True)  # noqa: E126
        assert subprocess_mock.call_count == 5


class TestEnsurePermissions:
    def test_no_previous_permissions(self, subprocess_sideeffect, call_data,
                                     args):
        detectip_mock = mock.Mock(return_value="1.2.3.4")

        subprocess_mock = mock.MagicMock(side_effect=subprocess_sideeffect)

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch('etcd_discovery.etcd_discovery.detect_ip',
                           detectip_mock))
            stack.enter_context(mock.patch('subprocess.run', subprocess_mock))
            etd.ensure_permissions(args)

        subprocess_mock.assert_has_calls([
            mock.call(call_data["user_list"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["user_add_root"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["user_add_calico"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["user_list"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["user_add_adminrouter"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_grant_root"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_add_calico_prefix"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_grant_calico"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_add_adminrouter_prefix"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_grant_adminrouter"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_list"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["auth_enable"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["endpoint_health"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_permission_calico_prefix"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_permission_adminrouter_prefix"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
        ],
                                         any_order=True)  # noqa: E126
        assert subprocess_mock.call_count == 17

    # Situation when the permissions have been already granted
    def test_permissions_preexist(self, subprocess_sideeffect, call_data,
                                  args):
        detectip_mock = mock.Mock(return_value="1.2.3.4")

        subprocess_mock = mock.MagicMock(side_effect=subprocess_sideeffect)

        call_data["user_list"][
            "action"].stdout = b'root\ncalico\nadminrouter\n'
        call_data["role_list"][
            "action"].stdout = b'adminrouter_prefix\ncalico_prefix\n'

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch('etcd_discovery.etcd_discovery.detect_ip',
                           detectip_mock))
            stack.enter_context(mock.patch('subprocess.run', subprocess_mock))
            etd.ensure_permissions(args)

        subprocess_mock.assert_has_calls([
            mock.call(call_data["user_list"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_list"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_grant_root"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_grant_calico"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_grant_adminrouter"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_permission_calico_prefix"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["role_permission_adminrouter_prefix"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["endpoint_health"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(call_data["auth_enable"]["args"],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
        ],
                                         any_order=True)  # noqa: E126
        assert subprocess_mock.call_count == 12

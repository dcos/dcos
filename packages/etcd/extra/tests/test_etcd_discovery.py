
import contextlib
import subprocess
from argparse import Namespace
from unittest import mock

import etcd_discovery.etcd_discovery as etd
import pytest


class TestJoinCluster:
    def test_etcd_already_initialized(self, tmp_path):
        d = tmp_path / "default.etcd"
        d.mkdir()

        args = Namespace(etcd_data_dir=str(d))

        etd.join_cluster(args)

    def test_happy_path_first_node(self, zk, tmp_path):
        cluster_state_file = tmp_path / "cluster_state_file.txt"
        cluster_nodes_file = tmp_path / "cluster_nodes_file.txt"
        etcdctl_path = tmp_path / "etcdctl_path"

        detectip_mock = mock.Mock(return_value="1.2.3.4")
        etcdctl_result = subprocess.CompletedProcess(
            args=["foo", "bar"],
            returncode=0,
            stdout="foo stdout",
            stderr="foo stderr",
        )
        subprocess_mock = mock.MagicMock(return_value=etcdctl_result)
        args = Namespace(
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

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch('etcd_discovery.etcd_discovery.detect_ip',
                           detectip_mock))
            stack.enter_context(mock.patch('subprocess.run', subprocess_mock))
            etd.join_cluster(args)

        detectip_mock.assert_called_once()
        subprocess_mock.assert_not_called()

    def test_happy_path_subsequent_node(self, zk, tmp_path):
        cluster_state_file = tmp_path / "cluster_state_file.txt"
        cluster_nodes_file = tmp_path / "cluster_nodes_file.txt"
        etcdctl_path = tmp_path / "etcdctl_path"

        zk.set('/etcd/nodes', b'{"nodes":["1.1.1.1"]}')

        detectip_mock = mock.Mock(return_value="1.2.3.4")
        base_args = [
            str(etcdctl_path),
            "--endpoints",
            "http://1.1.1.1:2379",
        ]
        member_list_args = base_args + ["member", "list", "-w", "json"]
        member_add_args = base_args + [
            "member", "add", "etcd-1.2.3.4", "--peer-urls=https://1.2.3.4:2380",
        ]
        endpoint_health = base_args + ["endpoint", "health"]

        def subprocess_sideeffect(args, stdout, stderr):
            assert stdout is subprocess.PIPE
            assert stderr is subprocess.PIPE

            if args == member_list_args:
                return subprocess.CompletedProcess(
                    args=member_list_args,
                    returncode=0,
                    stdout='''{
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
                    stderr="foo stderr",
                )
            elif args == member_add_args:
                return subprocess.CompletedProcess(
                    args=member_add_args,
                    returncode=0,
                    stdout="foo stdout",
                    stderr="foo stderr",
                )
            elif args == endpoint_health:
                return subprocess.CompletedProcess(
                    args=member_add_args,
                    returncode=0,
                    stdout="foo stdout",
                    stderr="foo stderr",
                )
            else:
                pytest.fail(
                    "unhandled arguments have been passed: {}".format(args))

        subprocess_mock = mock.MagicMock(side_effect=subprocess_sideeffect)
        args = Namespace(
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

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch('etcd_discovery.etcd_discovery.detect_ip',
                           detectip_mock))
            stack.enter_context(mock.patch('subprocess.run', subprocess_mock))
            etd.join_cluster(args)

        detectip_mock.assert_called_once()
        subprocess_mock.assert_has_calls([
            mock.call(endpoint_health,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(member_list_args,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(member_add_args,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
        ],
                                         any_order=False)  # noqa: E126
        assert subprocess_mock.call_count == 3

    def test_subsequent_node_already_registered(self, zk, tmp_path):
        cluster_state_file = tmp_path / "cluster_state_file.txt"
        cluster_nodes_file = tmp_path / "cluster_nodes_file.txt"
        etcdctl_path = tmp_path / "etcdctl_path"

        zk.set('/etcd/nodes', b'{"nodes":["1.1.1.1", "1.2.3.4"]}')

        detectip_mock = mock.Mock(return_value="1.2.3.4")
        base_args = [
            str(etcdctl_path),
            "--endpoints",
            "http://1.1.1.1:2379",
        ]
        member_list_args = base_args + ["member", "list", "-w", "json"]
        endpoint_health = base_args + ["endpoint", "health"]
        member_add_args = base_args + [
            "member", "add", "etcd-1.2.3.4", "--peer-urls=https://1.2.3.4:2380",
        ]

        # designated node is choosen from a healthy node by checking the return
        # value of the endpoint
        endpoint_health_cur_node = [
            str(etcdctl_path), "--endpoints", "http://1.2.3.4:2379",
            "endpoint", "health"
        ]

        def subprocess_sideeffect(args, stdout, stderr):
            assert stdout is subprocess.PIPE
            assert stderr is subprocess.PIPE

            if args == member_list_args:
                return subprocess.CompletedProcess(
                    args=member_list_args,
                    returncode=0,
                    stdout='''{
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
                    stderr="foo stderr",
                )
            elif args == member_add_args:
                return subprocess.CompletedProcess(
                    args=member_add_args,
                    returncode=0,
                    stdout="foo stdout",
                    stderr="foo stderr",
                )
            elif args == endpoint_health:
                return subprocess.CompletedProcess(
                    args=member_add_args,
                    returncode=0,
                    stdout="foo stdout",
                    stderr="foo stderr",
                )
            elif args == endpoint_health_cur_node:
                return subprocess.CompletedProcess(
                    args=member_add_args,
                    returncode=1,
                    stdout="foo stdout",
                    stderr="foo stderr",
                )
            else:
                pytest.fail(
                    "unhandled arguments have been passed: {}".format(args))

        subprocess_mock = mock.MagicMock(side_effect=subprocess_sideeffect)
        args = Namespace(
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

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch('etcd_discovery.etcd_discovery.detect_ip',
                           detectip_mock))
            stack.enter_context(mock.patch('subprocess.run', subprocess_mock))
            etd.join_cluster(args)

        detectip_mock.assert_called_once()
        subprocess_mock.assert_has_calls([
            mock.call(endpoint_health,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(endpoint_health_cur_node,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(member_list_args,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(member_list_args,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
            mock.call(member_add_args,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE),
        ])

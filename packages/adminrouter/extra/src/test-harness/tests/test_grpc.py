# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import grpc
import pytest

from mocker.endpoints import grpc_endpoint_pb2


class TestGRPC:
    def test_unary_happy_path(self, master_ar_process, valid_user_header, grpc_stub):
        request = grpc_endpoint_pb2.StringMessage(message="foo 123")
        response = grpc_stub.UnaryDoSomething(
            request,
            metadata=(
                ('authorization', valid_user_header['Authorization']),
            ),
        )

        assert request.message in response.message

    def test_unary_unauthn(self, master_ar_process, grpc_stub):
        with pytest.raises(grpc.RpcError) as e:
            request = grpc_endpoint_pb2.StringMessage(message="foo 123")
            grpc_stub.UnaryDoSomething(
                request,
            )

        assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
        assert "not authenticated" in e.value.details()

    def test_unary_failed(
            self, master_ar_process, valid_user_header, grpc_stub, mocker,
            repo_is_ee):

        if repo_is_ee:
            endpoint_id = 'grpcs://127.0.0.1:2379'
        else:
            endpoint_id = 'grpc://127.0.0.1:2379'

        mocker.send_command(
            endpoint_id=endpoint_id,
            func_name='always_bork',
            aux_data=True,
        )

        with pytest.raises(grpc.RpcError) as e:
            request = grpc_endpoint_pb2.StringMessage(message="foo 123")
            grpc_stub.UnaryDoSomething(
                request,
                metadata=(
                    ('authorization', valid_user_header['Authorization']),
                ),
            )

        assert e.value.code() == grpc.StatusCode.FAILED_PRECONDITION
        assert e.value.details() == "request borked per request"

    def test_unary_timeout(
            self, master_ar_process, valid_user_header, grpc_stub, mocker,
            repo_is_ee):

        if repo_is_ee:
            endpoint_id = 'grpcs://127.0.0.1:2379'
        else:
            endpoint_id = 'grpc://127.0.0.1:2379'

        mocker.send_command(
            endpoint_id=endpoint_id,
            func_name='always_stall',
            aux_data=3,
        )

        with pytest.raises(grpc.RpcError) as e:
            request = grpc_endpoint_pb2.StringMessage(message="foo 123")
            grpc_stub.UnaryDoSomething(
                request,
                metadata=(
                    ('authorization', valid_user_header['Authorization']),
                ),
                timeout=2
            )

        assert e.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED

    def test_serverstream_happy_path(
            self, master_ar_process, valid_user_header, grpc_stub):
        messageIDs = [3, 5, 10, 1]

        request = grpc_endpoint_pb2.IntCollectionMessage(messageIDs=messageIDs)
        response = grpc_stub.ServerSteramDoSomething(
            request,
            metadata=(
                ('authorization', valid_user_header['Authorization']),
            ),
        )

        received = []
        for message in response:
            received.append(message.messageID)

        assert messageIDs == received

    def test_serverstream_unauthn(self, master_ar_process, grpc_stub):
        messageIDs = [3, 5, 10, 1]

        request = grpc_endpoint_pb2.IntCollectionMessage(messageIDs=messageIDs)
        with pytest.raises(grpc.RpcError) as e:
            response = grpc_stub.ServerSteramDoSomething(
                request,
            )
            # Drain the response
            next(response)

        assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
        assert "not authenticated" in e.value.details()

    def test_clientstream_happy_path(
            self, master_ar_process, valid_user_header, grpc_stub):
        messageIDs = [3, 5, 10, 1]
        messageGen = (grpc_endpoint_pb2.IntMessage(messageID=i) for i in messageIDs)

        response = grpc_stub.ClientStreamDoSomething(
            messageGen,
            metadata=(
                ('authorization', valid_user_header['Authorization']),
            ),
        )

        assert response.messageIDs == messageIDs

    def test_clientstream_unauthn(self, master_ar_process, grpc_stub):
        messageIDs = [3, 5, 10, 1]
        messageGen = (grpc_endpoint_pb2.IntMessage(messageID=i) for i in messageIDs)

        with pytest.raises(grpc.RpcError) as e:
            grpc_stub.ClientStreamDoSomething(
                messageGen,
            )

        assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
        assert "not authenticated" in e.value.details()

# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import pytest
import requests
import time

from mocker.endpoints.marathon import NGINX_APP_ALWAYSTHERE_DIFFERENTPORT
from mocker.endpoints.mesos import (
    NGINX_FWRK_ALWAYSTHERE_DIFFERENTPORT,
    NGINX_FWRK_ALWAYSTHERE_NOWEBUI,
    framework_from_template
    )
from mocker.endpoints.mesos_dns import NGINX_SRV_ALWAYSTHERE_DIFFERENTPORT
from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    header_is_absent,
)
from generic_test_code.common import (
    generic_upstream_headers_verify_test,
)

CACHE_UPDATE_DELAY = 2  # seconds
assert CACHE_UPDATE_DELAY > 1.5  # due to cache_expiration=(CACHE_UPDATE_DELAY - 1)


@pytest.fixture()
def master_ar_process_fastcache(nginx_class):
    """An AR process instance fixture for situations where a short lived cache
       is needed. In order to achieve it, the scope of this fixture needs to be
       single test.
    """
    nginx = nginx_class(role="master",
                        cache_poll_period=CACHE_UPDATE_DELAY,
                        cache_expiration=(CACHE_UPDATE_DELAY - 1),
                        cache_first_poll_delay=1,
                        )
    nginx.start()

    yield nginx

    nginx.stop()


class TestServiceStatefull:
    # Test all the statefull test-cases/tests where AR caching may influence the
    # results
    def test_if_marathon_apps_are_resolved(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from MesosDNS and Mesos mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[])
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data={})

        # Check if we can use root Marathon app data to resolve `/service`
        # location requests:
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.1:16000"
            )

        # Update the application, wait for cache to register the change
        new_apps = {"apps": [NGINX_APP_ALWAYSTHERE_DIFFERENTPORT, ]}
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data=new_apps)
        time.sleep(CACHE_UPDATE_DELAY + 1)

        # Check if the location now resolves correctly to the new app port
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_is_resolved_using_framework_id(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from MesosDNS and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data={})

        # Check if we can use Mesos framework data to resolve `/service`
        # location request using framework ID:
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/0f8899bf-a31a-44d5-b1a5-c8c3f7128905-0000/foo/bar/',
            "http://127.0.0.1:16000"
            )

        # Update the application, wait for cache to register the change
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_DIFFERENTPORT])
        time.sleep(CACHE_UPDATE_DELAY + 1)

        # Check if the location now resolves correctly to the new app port
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/0f8899bf-a31a-44d5-b1a5-c8c3f7128905-0000/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_is_resolved_using_framework_name(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from MesosDNS and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data={})

        # Check if we can use Mesos framework data to resolve `/service`
        # location request using framework ID:
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.1:16000"
            )

        # Update the application, wait for cache to register the change
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_DIFFERENTPORT])
        time.sleep(CACHE_UPDATE_DELAY + 1)

        # Check if the location now resolves correctly to the new app port
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_mesos_dns_resolving_works(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_NOWEBUI])

        # Check if we can use Mesos framework data to resolve `/service`
        # location request using framework ID:
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.1:16000"
            )

        # Update the application, wait for cache to register the change
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=NGINX_SRV_ALWAYSTHERE_DIFFERENTPORT)
        time.sleep(CACHE_UPDATE_DELAY + 1)

        # Check if the location now resolves correctly to the new app port
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_marathon_apps_have_prio_over_webui_url(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from MesosDNS
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data={})

        # Make svcapps resolve the app upstream to a different address,
        # framework data implicitly has default port (127.0.0.1:16000)
        new_apps = {"apps": [NGINX_APP_ALWAYSTHERE_DIFFERENTPORT, ]}
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data=new_apps)

        # Check that svcapps resolve to different port
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_marathon_apps_have_prio_over_mesos_dns(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Disable resolving service data using webui
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_NOWEBUI])

        # Make svcapps resolve the app upstream to a different address,
        # framework data implicitly has default port (127.0.0.1:16000)
        new_apps = {"apps": [NGINX_APP_ALWAYSTHERE_DIFFERENTPORT, ]}
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data=new_apps)

        # Check that svcapps resolve to different port
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_has_prio_over_mesos_dns(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from Marathon mock
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})

        # Set a different port for webui-based framework data:
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_DIFFERENTPORT])

        # Check that svcapps resolve to different port
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_by_fwrk_id_has_prio_over_webui_url_by_fwrk_name(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # This one is tricky, we need to create a state-summary entry that has
        # a framework entry with "name" field equal to the "id" field of a
        # different entry

        # Remove the data from Marathon mock
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})

        # Remove the data from MesosDNS mock
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data={})

        # Fabricate state-summary data needed for the tests
        fwrk_a = framework_from_template(
            "0f8899bf-a31a-44d5-b1a5-c8c3f7128905-0000",
            "nginx-alwaysthere",
            "http://127.0.0.15:16001")
        fwrk_b = framework_from_template(
            "0535dd9a-2644-4945-a365-6fe0145f103f-0000",
            "0f8899bf-a31a-44d5-b1a5-c8c3f7128905-0000",
            "http://127.0.0.1:16000")
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[fwrk_a, fwrk_b])

        # Check that svcapps resolve to different port
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/0f8899bf-a31a-44d5-b1a5-c8c3f7128905-0000/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_path_is_normalized(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from Marathon mock
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})

        # Remove the data from MesosDNS mock
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data={})

        # Test webui_url entry withouth trailing slash:
        fwrk = framework_from_template(
            "0f8899bf-a31a-44d5-b1a5-c8c3f7128905-0000",
            "nginx-alwaysthere",
            "http://127.0.0.15:16001")
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[fwrk])
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )
        generic_correct_upstream_request_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            '/foo/bar/',
            http_ver='HTTP/1.1'
            )

        # Test webui_url entry with trailing slash:
        fwrk = framework_from_template(
            "0f8899bf-a31a-44d5-b1a5-c8c3f7128905-0000",
            "nginx-alwaysthere",
            "http://127.0.0.15:16001/")
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[fwrk])
        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )
        generic_correct_upstream_request_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            '/foo/bar/',
            http_ver='HTTP/1.1'
            )

    def test_if_broken_json_from_mesos_dns_is_handled(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_NOWEBUI])
        # Make MesosDNS mock respond with garbled data
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_encoded_response',
                            aux_data=b'blah blah duh duh')

        # Verify the response:
        url = master_ar_process_fastcache.make_url_from_path(
            '/service/nginx-alwaysthere/foo/bar/')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 503

    def test_if_broken_response_status_from_mesos_dns_is_handled(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_NOWEBUI])

        # Make MesosDNS mock respond with invalid data
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='always_bork',
                            aux_data=True)

        # Verify the response:
        url = master_ar_process_fastcache.make_url_from_path(
            '/service/nginx-alwaysthere/foo/bar/')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 503

    def test_if_timed_out_response_from_mesos_dns_is_handled(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_NOWEBUI])

        # Make MesosDNS mock stall response by 10s
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='always_stall',
                            aux_data=10)

        # Verify the response:
        url = master_ar_process_fastcache.make_url_from_path(
            '/service/nginx-alwaysthere/foo/bar/')
        t_start = time.time()
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)
        t_spent = time.time() - t_start

        assert t_spent < 10
        assert resp.status_code == 503

    def test_if_mesos_dns_subrequest_does_not_pass_auth_header_to_mesos_dns(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[NGINX_FWRK_ALWAYSTHERE_NOWEBUI])
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=NGINX_SRV_ALWAYSTHERE_DIFFERENTPORT)

        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='record_requests')

        generic_correct_upstream_dest_test(
            master_ar_process_fastcache,
            valid_user_header,
            '/service/nginx-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

        r_reqs = mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                                     func_name='get_recorded_requests')

        assert len(r_reqs) == 1
        header_is_absent(r_reqs[0]['headers'], 'Authorization')

    def test_if_no_services_in_cluster_case_is_handled(
            self, master_ar_process_fastcache, mocker, valid_user_header):
        # Remove the data from ALL backends:
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[])
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data={})

        url = master_ar_process_fastcache.make_url_from_path(
            '/service/nginx-alwaysthere/foo/bar/')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        # TODO: should be 404
        assert resp.status_code == 500

# For future:
#  * (JIRA!)test if inexistant service ends up in 404
#  * (JIRA!)test if inactive frameworks are not taken into consideration
#  * (JIRA!)test if nested services are honoured:
#    * by svc
#    * by mesos-dns
#    * by framework-id
#  * (JIRA!)pre-processing mesos data:
#    * pre-process mesos data into two hashes, one webui_url per framework id, and
#      other with webui_url per framework name.
#    * some error conditions checking:
#      * webui_url is invalid/cannot be parsed
#      * scheme is missing from webui

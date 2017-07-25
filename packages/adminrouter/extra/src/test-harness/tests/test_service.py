
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import time

import requests

from generic_test_code.common import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    header_is_absent,
)
from mocker.endpoints.marathon import (
    SCHEDULER_APP_ALWAYSTHERE_DIFFERENTPORT,
    app_from_template,
)
from mocker.endpoints.mesos import (
    SCHEDULER_FWRK_ALWAYSTHERE_DIFFERENTPORT,
    SCHEDULER_FWRK_ALWAYSTHERE_ID,
    SCHEDULER_FWRK_ALWAYSTHERE_NOWEBUI,
    framework_from_template,
)
from mocker.endpoints.mesos_dns import (
    EMPTY_SRV,
    SCHEDULER_SRV_ALWAYSTHERE_DIFFERENTPORT,
)
from util import GuardedSubprocess


class TestServiceStateful:
    # Test all the stateful test-cases/tests where AR caching may influence the
    # results
    def test_if_marathon_apps_are_resolved(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from MesosDNS and Mesos mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[])
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=EMPTY_SRV)

        # Set non-standard socket for the applicaiton
        new_apps = {"apps": [SCHEDULER_APP_ALWAYSTHERE_DIFFERENTPORT, ]}
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data=new_apps)

        # Check if the location now resolves correctly to the new app socket
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_is_resolved_using_framework_id(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from MesosDNS and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=EMPTY_SRV)

        # Set non-standard socket for the framework
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_DIFFERENTPORT])

        # Check if the location now resolves correctly to the new framework
        # socket
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/{}/foo/bar/'.format(SCHEDULER_FWRK_ALWAYSTHERE_ID),
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_is_resolved_using_framework_name(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from MesosDNS and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=EMPTY_SRV)

        # Set non-standard port for the framework:
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_DIFFERENTPORT])

        # Check if the location now resolves correctly to the new framework
        # socket
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_mesos_dns_resolving_works(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_NOWEBUI])

        # Set non-standard port for the framework:
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=SCHEDULER_SRV_ALWAYSTHERE_DIFFERENTPORT)

        # Check if the location now resolves correctly to the new framework
        # socket
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_marathon_apps_have_prio_over_webui_url(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from MesosDNS
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=EMPTY_SRV)

        # Make svcapps resolve the app upstream to a different address,
        # framework data implicitly has default port (127.0.0.1:16000)
        new_apps = {"apps": [SCHEDULER_APP_ALWAYSTHERE_DIFFERENTPORT, ]}
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data=new_apps)

        # Check that svcapps resolve to different port
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_marathon_apps_have_prio_over_mesos_dns(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Disable resolving service data using webui
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_NOWEBUI])

        # Make svcapps resolve the app upstream to a different address,
        # framework data implicitly has default port (127.0.0.1:16000)
        new_apps = {"apps": [SCHEDULER_APP_ALWAYSTHERE_DIFFERENTPORT, ]}
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data=new_apps)

        # Check that svcapps resolve to different port
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_has_prio_over_mesos_dns(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from Marathon mock
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})

        # Set a different port for webui-based framework data:
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_DIFFERENTPORT])

        # Check that svcapps resolve to different port
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_by_fwrk_id_has_prio_over_webui_url_by_fwrk_name(
            self, master_ar_process_pertest, mocker, valid_user_header):
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
                            aux_data=EMPTY_SRV)

        # Fabricate state-summary data needed for the tests
        fwrk_a = framework_from_template(
            SCHEDULER_FWRK_ALWAYSTHERE_ID,
            "scheduler-alwaysthere",
            "http://127.0.0.15:16001")
        fwrk_b = framework_from_template(
            "0535dd9a-2644-4945-a365-6fe0145f103f-0000",
            SCHEDULER_FWRK_ALWAYSTHERE_ID,
            "http://127.0.0.1:16000")
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[fwrk_a, fwrk_b])

        # Check that svcapps resolve to different port
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/{}/foo/bar/'.format(SCHEDULER_FWRK_ALWAYSTHERE_ID),
            "http://127.0.0.15:16001"
            )

    def test_if_webui_url_path_is_normalized(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from Marathon mock
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})

        # Remove the data from MesosDNS mock
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=EMPTY_SRV)

        # Test webui_url entry withouth trailing slash:
        fwrk = framework_from_template(
            SCHEDULER_FWRK_ALWAYSTHERE_ID,
            "scheduler-alwaysthere",
            "http://127.0.0.15:16001")
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[fwrk])
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )
        generic_correct_upstream_request_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            '/foo/bar/',
            http_ver='websockets'
            )

        # Test webui_url entry with trailing slash:
        fwrk = framework_from_template(
            SCHEDULER_FWRK_ALWAYSTHERE_ID,
            "scheduler-alwaysthere",
            "http://127.0.0.15:16001/")
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[fwrk])
        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )
        generic_correct_upstream_request_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            '/foo/bar/',
            http_ver='websockets'
            )

    def test_if_broken_json_from_mesos_dns_is_handled(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_NOWEBUI])
        # Make MesosDNS mock respond with garbled data
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_encoded_response',
                            aux_data=b'blah blah duh duh')

        # Verify the response:
        url = master_ar_process_pertest.make_url_from_path(
            '/service/scheduler-alwaysthere/foo/bar/')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 503

    def test_if_broken_response_status_from_mesos_dns_is_handled(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_NOWEBUI])

        # Make MesosDNS mock respond with invalid data
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='always_bork',
                            aux_data=True)

        # Verify the response:
        url = master_ar_process_pertest.make_url_from_path(
            '/service/scheduler-alwaysthere/foo/bar/')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 503

    def test_if_timed_out_response_from_mesos_dns_is_handled(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_NOWEBUI])

        # Make MesosDNS mock stall response by 10s
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='always_stall',
                            aux_data=10)

        # Verify the response:
        url = master_ar_process_pertest.make_url_from_path(
            '/service/scheduler-alwaysthere/foo/bar/')
        t_start = time.time()
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)
        t_spent = time.time() - t_start

        # If the timeout was properly enforced by Admin Router, the total time
        # spent waiting for response will be less than 10s. If there is no
        # timeout - it will be at least 10s.
        assert t_spent < 10
        assert resp.status_code == 503

    def test_if_mesos_dns_subrequest_does_not_pass_auth_header_to_mesos_dns(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from Mesos and Marathon mocks w.r.t. resolved service
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[SCHEDULER_FWRK_ALWAYSTHERE_NOWEBUI])
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=SCHEDULER_SRV_ALWAYSTHERE_DIFFERENTPORT)

        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='record_requests')

        generic_correct_upstream_dest_test(
            master_ar_process_pertest,
            valid_user_header,
            '/service/scheduler-alwaysthere/foo/bar/',
            "http://127.0.0.15:16001"
            )

        r_reqs = mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                                     func_name='get_recorded_requests')

        assert len(r_reqs) == 1
        header_is_absent(r_reqs[0]['headers'], 'Authorization')

    def test_if_no_services_in_cluster_case_is_handled(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from ALL backends:
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='set_apps_response',
                            aux_data={"apps": []})
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[])
        mocker.send_command(endpoint_id='http://127.0.0.1:8123',
                            func_name='set_srv_response',
                            aux_data=EMPTY_SRV)

        url = master_ar_process_pertest.make_url_from_path(
            '/service/scheduler-alwaysthere/foo/bar/')
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 404

    def test_if_only_matching_scheme_redirects_are_adjusted_for_marathon_apps(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from MesosDNS and Mesos mocks w.r.t. resolved service
        mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='set_frameworks_response',
            aux_data=[])
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8123',
            func_name='set_srv_response',
            aux_data=EMPTY_SRV)

        # Mock TLS-enabled Marathon app
        app_dict = app_from_template(
            'scheduler-alwaysthere', 443, ip="127.0.0.4", scheme='https')
        new_apps = {"apps": [app_dict, ]}
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8080',
            func_name='set_apps_response',
            aux_data=new_apps)

        # Non-matching:
        mocker.send_command(
            endpoint_id="https://127.0.0.4:443",
            func_name='always_redirect',
            aux_data="http://127.0.0.1/")
        url = master_ar_process_pertest.make_url_from_path(
            "/service/scheduler-alwaysthere/foo/bar")
        r = requests.get(url, allow_redirects=False, headers=valid_user_header)
        assert r.status_code == 307
        assert r.headers['Location'] == "http://127.0.0.1/"

        # Matching:
        mocker.send_command(
            endpoint_id="https://127.0.0.4:443",
            func_name='always_redirect',
            aux_data="https://127.0.0.1/")
        url = master_ar_process_pertest.make_url_from_path(
            "/service/scheduler-alwaysthere/foo/bar")
        r = requests.get(url, allow_redirects=False, headers=valid_user_header)
        assert r.status_code == 307
        assert r.headers['Location'] == "http://127.0.0.1/service/scheduler-alwaysthere/"

    def test_if_only_matching_scheme_redirects_are_adjusted_for_mesos_frameworks(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from MesosDNS and Marathon mocks w.r.t. resolved service
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8080',
            func_name='set_apps_response',
            aux_data={"apps": []})
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8123',
            func_name='set_srv_response',
            aux_data=EMPTY_SRV)

        # Mock TLS-enabled framework
        fwrk = framework_from_template(
            SCHEDULER_FWRK_ALWAYSTHERE_ID,
            "scheduler-alwaysthere",
            "https://127.0.0.4:443/")
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[fwrk])

        # Non-matching:
        mocker.send_command(
            endpoint_id="https://127.0.0.4:443",
            func_name='always_redirect',
            aux_data="http://127.0.0.1/")
        url = master_ar_process_pertest.make_url_from_path(
            "/service/scheduler-alwaysthere/foo/bar")
        r = requests.get(url, allow_redirects=False, headers=valid_user_header)
        assert r.status_code == 307
        assert r.headers['Location'] == "http://127.0.0.1/"

        # Matching:
        mocker.send_command(
            endpoint_id="https://127.0.0.4:443",
            func_name='always_redirect',
            aux_data="https://127.0.0.1/")
        url = master_ar_process_pertest.make_url_from_path(
            "/service/scheduler-alwaysthere/foo/bar")
        r = requests.get(url, allow_redirects=False, headers=valid_user_header)
        assert r.status_code == 307
        assert r.headers['Location'] == "http://127.0.0.1/service/scheduler-alwaysthere/"

    def test_if_scheme_is_honoured_for_marathon_apps(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from MesosDNS and Mesos mocks w.r.t. resolved service
        mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='set_frameworks_response',
            aux_data=[])
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8123',
            func_name='set_srv_response',
            aux_data=EMPTY_SRV)

        # Mock TLS-enabled Marathon app
        app_dict = app_from_template(
            'scheduler-alwaysthere', 443, ip="127.0.0.4", scheme='https')
        new_apps = {"apps": [app_dict, ]}
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8080',
            func_name='set_apps_response',
            aux_data=new_apps)

        url = master_ar_process_pertest.make_url_from_path("/service/scheduler-alwaysthere/")
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['endpoint_id'] == "https://127.0.0.4:443"

    def test_if_scheme_is_honoured_in_mesos_scheduler_entry(
            self, master_ar_process_pertest, mocker, valid_user_header):
        # Remove the data from MesosDNS and Marathon mocks w.r.t. resolved service
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8080',
            func_name='set_apps_response',
            aux_data={"apps": []})
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8123',
            func_name='set_srv_response',
            aux_data=EMPTY_SRV)

        # Mock TLS-enabled framework
        fwrk = framework_from_template(
            SCHEDULER_FWRK_ALWAYSTHERE_ID,
            "scheduler-alwaysthere",
            "https://127.0.0.4:443/")
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='set_frameworks_response',
                            aux_data=[fwrk])

        url = master_ar_process_pertest.make_url_from_path("/service/scheduler-alwaysthere/")
        resp = requests.get(url,
                            allow_redirects=False,
                            headers=valid_user_header)

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['endpoint_id'] == "https://127.0.0.4:443"

    def test_if_ar_with_empty_cache_waits_for_marathon_during_service_resolve(
            self, mocker, nginx_class, valid_user_header):
        # Make service endpoint resolve only Marathon-related data:
        mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='set_frameworks_response',
            aux_data=[])
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8123',
            func_name='set_srv_response',
            aux_data=EMPTY_SRV)

        # Make Mock endpoint stall a little, make sure AR cache update timeouts
        # are big enough to swallow it:
        backend_request_timeout = 6
        refresh_lock_timeout = backend_request_timeout * 2

        # Make period cache refreshes so rare that they do not get into
        # picture:
        ar = nginx_class(cache_first_poll_delay=1200,
                         cache_poll_period=1200,
                         cache_expiration=1200,
                         cache_max_age_soft_limit=1200,
                         cache_max_age_hard_limit=1800,
                         cache_backend_request_timeout=backend_request_timeout,
                         cache_refresh_lock_timeout=refresh_lock_timeout,
                         )
        url = ar.make_url_from_path("/service/scheduler-alwaysthere/")

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='always_stall',
                            aux_data=backend_request_timeout * 0.5)

        # Measure the time it took and the results:
        with GuardedSubprocess(ar):
            t_start = time.time()
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

        t_spent = time.time() - t_start
        assert resp.status_code == 200
        data = resp.json()
        assert data['endpoint_id'] == 'http://127.0.0.1:16000'

        # If AR waits for cache during resolve, then time spent should be
        # greater than the stall time that has been set. Due to the fact
        # that update coroutines are not separated yet, this will be
        # slightly higher than: 2 * (backend_request_timeout * 0.5)
        # as we have two calls to Marathon (svcapps + marathon leader) from
        # the cache code.
        assert t_spent > 2 * (backend_request_timeout * 0.5)

    def test_if_ar_with_empty_cache_waits_for_mesos_during_service_resolve(
            self, mocker, nginx_class, valid_user_header):
        # Make service endpoint resolve only Mesos-related data:
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8080',
            func_name='set_apps_response',
            aux_data={"apps": []})
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8123',
            func_name='set_srv_response',
            aux_data=EMPTY_SRV)

        # Make Mock endpoint stall a little, make sure AR cache update timeouts
        # are big enough to swallow it:
        backend_request_timeout = 6
        refresh_lock_timeout = backend_request_timeout * 2

        # Make period cache refreshes so rare that they do not get into
        # picture:
        ar = nginx_class(cache_first_poll_delay=1200,
                         cache_poll_period=1200,
                         cache_expiration=1200,
                         cache_max_age_soft_limit=1200,
                         cache_max_age_hard_limit=1800,
                         cache_backend_request_timeout=backend_request_timeout,
                         cache_refresh_lock_timeout=refresh_lock_timeout,
                         )
        url = ar.make_url_from_path("/service/scheduler-alwaysthere/")

        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='always_stall',
                            aux_data=backend_request_timeout * 0.5)

        # Measure the time it took and the results:
        with GuardedSubprocess(ar):
            t_start = time.time()
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)

            t_spent = time.time() - t_start
            assert resp.status_code == 200
            data = resp.json()
            data['endpoint_id'] == 'http://127.0.0.15:16001'

        assert t_spent > backend_request_timeout * 0.5

    def test_if_broken_marathon_prevents_resolving_via_mesos_state_summary(
            self, mocker, nginx_class, valid_user_header):
        # Bork Marathon Mock, DO NOT touch Mesos Mock:
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8080',
            func_name='always_bork',
            aux_data=True)

        # Make period cache refreshes so rare that they do not get into
        # picture:
        ar = nginx_class(cache_first_poll_delay=1200,
                         cache_poll_period=1200,
                         cache_expiration=1200,
                         cache_max_age_soft_limit=1200,
                         cache_max_age_hard_limit=1800,
                         )
        url = ar.make_url_from_path("/service/scheduler-alwaysthere/")

        with GuardedSubprocess(ar):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 503
        assert '503 Service Unavailable: invalid Marathon svcapps cache' in resp.text

    def test_if_broken_mesos_prevents_resolving_via_mesosdns(
            self, mocker, nginx_class, valid_user_header):
        # Bork Mesos Mock, Make Marathon mock respond with no apps, so that AR
        # tries to resolve via Mesos /state-summary
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8080',
            func_name='set_apps_response',
            aux_data={"apps": []})
        mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='always_bork',
            aux_data=True)

        # Make period cache refreshes so rare that they do not get into
        # picture:
        ar = nginx_class(cache_first_poll_delay=1200,
                         cache_poll_period=1200,
                         cache_expiration=1200,
                         cache_max_age_soft_limit=1200,
                         cache_max_age_hard_limit=1800,
                         )
        url = ar.make_url_from_path("/service/scheduler-alwaysthere/")

        with GuardedSubprocess(ar):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 503
        assert '503 Service Unavailable: invalid Mesos state cache' == resp.text.strip()

    def test_if_broken_mesos_does_not_prevent_resolving_via_marathon(
            self, mocker, nginx_class, valid_user_header):
        # Bork Mesos Mock, Make MesosDNS mock respond with no apps, so that AR
        # is able to resolve only via Marathon/we are certain that it resolved
        # via Marathon.
        mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='always_bork',
            aux_data=True)
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8123',
            func_name='set_srv_response',
            aux_data=EMPTY_SRV)

        # Make period cache refreshes so rare that they do not get into
        # picture:
        ar = nginx_class(cache_first_poll_delay=1200,
                         cache_poll_period=1200,
                         cache_expiration=1200,
                         cache_max_age_soft_limit=1200,
                         cache_max_age_hard_limit=1800,
                         )
        url = ar.make_url_from_path("/service/scheduler-alwaysthere/")

        with GuardedSubprocess(ar):
            resp = requests.get(
                url,
                allow_redirects=False,
                headers=valid_user_header)

        assert resp.status_code == 200
        data = resp.json()
        assert data['endpoint_id'] == 'http://127.0.0.1:16000'

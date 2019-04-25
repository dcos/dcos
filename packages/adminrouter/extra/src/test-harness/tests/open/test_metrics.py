import pytest
import requests


def get_static_upstream_annotations() -> dict:
    static_upstream_annotations = {
        '/mesos/': 'Mesos',
        '/cosmos/service/': 'Cosmos',
        '/dcos-ui-update-service/api/v1/version/': 'DCOSUIUpdateService',
        '/acs/api/v1': 'IAM',
        '/system/health/v1': 'DCOSDiagnostics',
        '/system/checks/v1': 'DCOSChecks',
        '/navstar/lashup/key': 'DCOSNet',
        '/net/': 'DCOSNet',
        '/system/v1/logs/': 'DCOSLog',
        '/system/v1/metrics/': 'DCOSMetrics',
        '/mesos_dns/': 'MesosDNS',
        '/pkgpanda/': 'Pkgpanda',
        '/exhibitor/exhibitor/v1/cluster/status': 'Exhibitor',
        '/service/marathon/v2/queue': 'service:=marathon',
        '/service/metronome/v1/jobs': 'service:=metronome',
    }
    return static_upstream_annotations


class TestMetrics:

    @pytest.mark.parametrize(
        'location,annotation', get_static_upstream_annotations().items(),
        ids=list(get_static_upstream_annotations().values())
        )
    def test_metrics_prometheus_static_upstreams_annotated(
            self, master_ar_process, valid_user_header, location, annotation):
        """
        /nginx/metrics returns metrics in Prometheus format that are properly
        annotated for static upstreams
        """

        url = master_ar_process.make_url_from_path('/nginx/metrics')

        # We are making an HTTP(s) request to a fixed upstream location.
        # This will cause nginx to apply corresponding annotation
        # label to the upstream metric, regardless of the status of the
        # call. As we are interested only in the label here, we are not
        # checking the status code.
        upstream_url = master_ar_process.make_url_from_path(location)
        requests.get(
            upstream_url,
            allow_redirects=True,
            headers=valid_user_header,
        )

        resp = requests.get(
            url,
            allow_redirects=False,
        )

        assert resp.status_code == 200
        assert resp.headers['Content-Type'] == 'text/plain'
        assert annotation in resp.text
        assert location in resp.text

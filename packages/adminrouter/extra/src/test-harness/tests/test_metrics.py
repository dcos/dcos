
import urllib.parse

import requests

from generic_test_code.common import repo_is_ee


class TestMetrics:

    def test_metrics_html(self, master_ar_process):
        """
        /nginx/status returns metrics in HTML format
        """
        url = master_ar_process.make_url_from_path('/nginx/status')

        resp = requests.get(
            url,
            allow_redirects=False
        )

        assert resp.status_code == 200
        assert resp.headers['Content-Type'] == 'text/html'

    def test_metrics_prometheus(self, master_ar_process):
        """
        /nginx/metrics returns metrics in Prometheus format
        """
        url = master_ar_process.make_url_from_path('/nginx/metrics')

        resp = requests.get(
            url,
            allow_redirects=False,
        )

        assert resp.status_code == 200
        assert resp.headers['Content-Type'] == 'text/plain'
        assert resp.text.startswith('# HELP nginx_vts_info Nginx info')

    def test_metrics_prometheus_long(self, master_ar_process, valid_user_header):
        """
        /nginx/metrics handles long URLs.
        """
        url_path = '/service/monitoring/grafan' + 'a' * 530
        url = master_ar_process.make_url_from_path(url_path)

        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header)

        assert resp.status_code == 404

        url = master_ar_process.make_url_from_path('/nginx/metrics')

        resp = requests.get(
            url,
            allow_redirects=False
        )

        assert resp.status_code == 200
        assert resp.headers['Content-Type'] == 'text/plain'
        assert url_path in resp.text

    def test_metrics_prometheus_static_upstreams_annotated(self, master_ar_process):
        """
        /nginx/metrics returns metrics in Prometheus format that are properly
        annotated for static upstreams
        """
        # Adding upstreams present in both Open and EE DC/OS
        static_upstream_annotations = {
            '/acs/api/v1': 'IAM',
            '/system/health/v1': 'DCOSDiagnostics',
            '/system/checks/v1': 'DCOSChecks',
            '/navstar/lashup/key': 'DCOSNet',
            '/net/': 'DCOSNet',
            '/system/v1/logs/': 'DCOSLog',
            '/system/v1/metrics/': 'DCOSMetrics',
            '/mesos_dns/': 'MesosDNS',
            }

        # Adding upstreams available only in Open DC/OS
        if not repo_is_ee:
            static_upstream_annotations.update(
                {
                    '/pkgpanda': 'Pkgpanda',
                    '/exhibitor/exhibitor/v1/cluster/status': 'Exhibitor',
                }
            )

        url = master_ar_process.make_url_from_path('/nginx/metrics')

        # We are iterating over the fixed upstream locations and issuing HTTP(s)
        # request to them.
        # This will cause nginx to apply corresponding annotation
        # label to the upstream metric, regardless of the status of the
        # call. As we are interested only in the label here, we are not
        # checking the status code.
        for upstream, label in static_upstream_annotations.items():
            upstream_url = master_ar_process.make_url_from_path(upstream)
            requests.get(
                upstream_url,
                allow_redirects=True,
            )

            resp = requests.get(
                url,
                allow_redirects=False,
            )
            assert resp.status_code == 200
            assert resp.headers['Content-Type'] == 'text/plain'
            assert label in resp.text

    def test_metrics_prometheus_escape(self, master_ar_process, valid_user_header):
        """
        /nginx/metrics escapes Prometheus format correctly.
        """

        # https://github.com/prometheus/docs/blob/master/content/docs/instrumenting/exposition_formats.md#text-format-details
        # "label_value can be any sequence of UTF-8 characters, but the backslash
        # (\, double-quote ("}, and line feed (\n) characters have to be escaped
        # as \\, \", and \n, respectively."

        # Add \t for tab as well, to show that is passes through unescaped

        url_path = urllib.parse.quote('/service/monitoring/gra"f\\a\nn\ta')
        url = master_ar_process.make_url_from_path(url_path)

        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header)

        assert resp.status_code == 404

        url = master_ar_process.make_url_from_path('/nginx/metrics')

        resp = requests.get(
            url,
            allow_redirects=False
        )

        assert resp.status_code == 200
        assert resp.headers['Content-Type'] == 'text/plain'
        # DCOS-50265 swaps the truth of the following two asserts:
        # not escaped:
        assert '/service/monitoring/gra"f\\a\nn\ta' not in resp.text
        # correctly escaped:
        assert '/service/monitoring/gra\\"f\\\\a\\nn\ta' in resp.text

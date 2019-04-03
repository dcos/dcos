import textwrap
import urllib.parse

import requests


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

    def test_metrics_prometheus_histogram(self, master_ar_process, mocker, valid_user_header):
        """
        Response times are measured in histogram output.
        """
        mocker.send_command(endpoint_id='http://127.0.0.1:8181',
                            func_name='always_stall',
                            aux_data=0.05)

        url = master_ar_process.make_url_from_path('/exhibitor/')

        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header)

        mocker.send_command(endpoint_id='http://127.0.0.1:8181',
                            func_name='always_stall',
                            aux_data=0.3)

        resp = requests.get(
            url,
            allow_redirects=False,
            headers=valid_user_header)

        url = master_ar_process.make_url_from_path('/nginx/metrics')

        resp = requests.get(
            url,
            allow_redirects=False
        )

        assert resp.status_code == 200
        assert resp.headers['Content-Type'] == 'text/plain'
        prefix = (
            'nginx_vts_filter_request_duration_seconds_bucket{'
            'filter="upstream:=Exhibitor",'
            'filter_name="backend:=127.0.0.1:8181"'
        )
        assert textwrap.dedent('''\
            %(prefix)s,le="0.008"} 0
            %(prefix)s,le="0.040"} 0
            %(prefix)s,le="0.200"} 1
            %(prefix)s,le="1.000"} 2
            %(prefix)s,le="5.000"} 2
            %(prefix)s,le="25.000"} 2
            %(prefix)s,le="+Inf"} 2
        ''' % {'prefix': prefix}) in resp.text

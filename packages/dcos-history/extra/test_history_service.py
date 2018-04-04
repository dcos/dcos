"""Test uses randomly generated data such that data ordering
and refreshing can be checked
"""
import os
import random
import string
from datetime import datetime, timedelta

import pytest

import history.server_util
import history.statebuffer
import pkgpanda.util
from history.statebuffer import FETCH_PERIOD, FILE_EXT


@pytest.fixture(scope='function')
def history_service(monkeypatch, tmpdir):
    mock_data = []
    update_counter = 0
    # Data will only be added to buffer if timestamp >= next_update. next_update
    # is set to be datetime.now at initialization. Using FETCH_PERIOD means that
    # each call to update will result in a appended /history/minute buffer

    def mock_state(headers):
        nonlocal update_counter
        nonlocal start_time
        nonlocal mock_data
        data = str(datetime.now()) + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(3))
        mock_data.append(data)
        delta_t = update_counter * FETCH_PERIOD
        timestamp = start_time + timedelta(seconds=delta_t)
        update_counter += 1
        return timestamp, data

    monkeypatch.setattr(history.statebuffer, 'fetch_state', mock_state)

    def mock_headers():
        return {'Authorization': 'test'}

    monkeypatch.setattr(history.server_util, 'add_headers_cb', mock_headers)

    sb = history.statebuffer.BufferCollection(tmpdir.strpath)
    start_time = datetime.now()
    history.server_util.state_buffer = sb  # connect mock to app
    test_app = history.server_util.test()
    test_app.config.update(dict(TESTING=True, DEBUG=True))
    test_client = test_app.test_client()
    updater = history.statebuffer.BufferUpdater(sb, None)

    def populate_buffer(update_count):
        for i in range(update_count):
            updater.update()

    return test_client, populate_buffer, mock_data, sb


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_ping(history_service):
    resp = history_service[0].get("/ping")
    assert resp.data.decode() == 'pong'


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_endpoint_last(history_service):
    history_service[1](60)  # 2 minutes of data
    resp = history_service[0].get("/history/last")
    assert resp.data.decode() == history_service[2][-1]


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_endpoint_minute(history_service):
    history_service[1](60)  # 2 minutes of data
    resp = history_service[0].get("/history/minute")
    # We exepect msg from initial startup and one per write interval
    minute_resp = '[' + ','.join(history_service[2][-30:]) + ']'
    assert resp.data.decode() == minute_resp


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_endpoint_hour(history_service):
    history_service[1](30 * 60 * 2)  # 2 hours of data
    resp = history_service[0].get("/history/hour")
    # first update and every update on the minute will be used for hourly buffer
    filtered_history = [history_service[2][i] for i in range(0, 30 * 60 * 2, 30)]
    # only the last hour of data should be returned
    filtered_history = filtered_history[-60:]
    assert resp.data.decode() == '[' + ','.join(filtered_history) + ']'


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_file_trimming(history_service):
    history_service[1](30 * 60 * 2)  # 2 hours of data
    assert len(os.listdir(history_service[3].buffers['minute'].path)) == 30
    assert len(os.listdir(history_service[3].buffers['hour'].path)) == 60


@pytest.mark.skipif(pkgpanda.util.is_windows, reason="test fails on Windows reason unknown")
def test_data_recovery(monkeypatch, tmpdir):

    def mock_state(headers):
        nonlocal start_time
        return start_time, 'baz'

    monkeypatch.setattr(history.statebuffer, 'fetch_state', mock_state)
    sb = history.statebuffer.BufferCollection(tmpdir.strpath)
    minute_path = sb.buffers['minute'].path
    # make really old data that should be trimmed
    past_time = datetime.now() - timedelta(seconds=60 * FETCH_PERIOD)
    for _ in range(50):
        with open(os.path.join(minute_path, "{}{}".format(past_time.isoformat(), FILE_EXT)), 'w') as fh:
            fh.write('2_old')
        past_time += timedelta(seconds=FETCH_PERIOD)
    # now write some backup data we want to check
    with open(os.path.join(minute_path, "{}{}".format(past_time.isoformat(), FILE_EXT)), 'w') as fh:
        fh.write('foo')
    # Test gaps between backup files
    past_time += timedelta(seconds=3 * FETCH_PERIOD)
    with open(os.path.join(minute_path, "{}{}".format(past_time.isoformat(), FILE_EXT)), 'w') as fh:
        fh.write('qux')
    # Test no gaps between backup files
    past_time += timedelta(seconds=FETCH_PERIOD)
    with open(os.path.join(minute_path, "{}{}".format(past_time.isoformat(), FILE_EXT)), 'w') as fh:
        fh.write('bar')
    # Test that persistence file filtering works
    with open(os.path.join(minute_path, "{}.user-summary.json".format(past_time.isoformat())), 'w') as fh:
        fh.write('DEADBEEF')
    # set start_time after instantiation to guarantee update on first write
    sb = history.statebuffer.BufferCollection(tmpdir.strpath)
    start_time = datetime.now()
    history.server_util.state_buffer = sb
    test_app = history.server_util.test()
    test_app.config.update(dict(TESTING=True, DEBUG=True))
    test_client = test_app.test_client()
    updater = history.statebuffer.BufferUpdater(sb, None)
    updater.update()
    resp = test_client.get("/history/minute")
    # recovery data w/gap + 8 FF updates + first real update
    exp_resp = ['foo', '{}', '{}', 'qux', 'bar'] + (['{}'] * 5) + ['baz']
    resp_data = resp.data.decode()[1:-1].split(',')[-11:]
    assert resp_data == exp_resp
    # also check that all the previous data is '2old'
    assert all([s == '2old' for s in resp_data[:-11]])
    # check that excess old data was trimmed, but 'user' data is untouched
    assert len(os.listdir(sb.buffers['minute'].path)) == 31
    resp = test_client.get("/history/hour")
    # No data was left for hour, so nothing loads other than the first update
    assert resp.data.decode() == '[baz]'


def test_add_headers(history_service):
    resp = history_service[0].get('/history/minute')
    # check that new header is added
    assert resp.headers['Authorization'] == 'test'
    # check that original headers are still there
    assert resp.headers['Access-Control-Max-Age'] == '86400'


# Tests for malformed filenames, ref DCOS_OSS-2210
def test_file_timestamp(monkeypatch, tmpdir):
    round_ts = datetime(2018, 2, 28, 20, 17, 14, 0)
    b = history.statebuffer.HistoryBuffer(60, 2, path=tmpdir.strpath)
    qname = b._get_datafile_name(round_ts)
    fname = qname.split('/')[-1]
    parsed_time = datetime.strptime(fname, '%Y-%m-%dT%H:%M:%S.%f.state-summary.json')
    assert parsed_time == round_ts

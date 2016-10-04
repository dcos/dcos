import json
import logging
import os
import asyncio
from collections import deque
from datetime import datetime, timedelta

import requests

logging.getLogger('requests.packages.urllib3').setLevel(logging.WARN)

FILE_EXT = '.state-summary.json'

STATE_SUMMARY_URI = os.getenv('STATE_SUMMARY_URI', 'http://leader.mesos:5050/state-summary')

TLS_VERIFY = True
# The verify arg to requests.get() can either
# be a boolean or the path to a CA_BUNDLE
if 'TLS_VERIFY' in os.environ:
    if os.environ['TLS_VERIFY'] == 'false':
        TLS_VERIFY = False
    elif os.environ['TLS_VERIFY'] == 'true':
        TLS_VERIFY = True
    else:
        TLS_VERIFY = os.environ['TLS_VERIFY']


def parse_log_time(fname):
    return datetime.strptime(fname, '%Y-%m-%dT%H:%M:%S.%f{}'.format(FILE_EXT))


def fetch_state(headers_cb):
    timestamp = datetime.now()
    try:
        # TODO(cmaloney): Access the mesos master redirect before requesting
        # state-summary so that we always get the "authoritative"
        # state-summary. leader.mesos isn't updated instantly.
        # That requires mesos stop returning hostnames from `/master/redirect`.
        # See: https://github.com/apache/mesos/blob/master/src/master/http.cpp#L746
        resp = requests.get(STATE_SUMMARY_URI, timeout=FETCH_PERIOD * .9, headers=headers_cb(), verify=TLS_VERIFY)
        resp.raise_for_status()
        state = resp.text
    except Exception as e:
        logging.warning("Could not fetch state: %s" % e)
        state = '{}'
    return timestamp, state


class HistoryBuffer():

    def __init__(self, time_window, update_period, path=None):
        """
        :param time_window: how many seconds this buffer will span
        :param update_period: the number of seconds between updates for this buffer
        :param path: (str) path for the dir to write to disk in
        """
        updates_per_window = int(time_window / update_period)
        if time_window % update_period != 0:
            raise ValueError(
                'Invalid updates per window: {} '
                'time_window/update_period must be an integer'.format(updates_per_window))

        self.in_memory = deque([], updates_per_window)
        self.update_period = timedelta(seconds=update_period)

        if path:
            try:
                os.makedirs(path)
            except FileExistsError:
                logging.info('Using previously created buffer persistence dir: {}'.format(path))
            self.path = path
            self.disk_count = updates_per_window
            old_files = [os.path.join(self.path, f) for f in os.listdir(self.path)]
            filtered_old_files = [f for f in old_files if f.endswith(FILE_EXT)]
            self.disk_files = list(sorted(filtered_old_files))
            backup_files = self.disk_files[-1 * updates_per_window:]
            backup_count = len(backup_files)

            def update_and_ff(f_path, ff_end):
                """Accounts for gaps between data in memory with blank filler
                """
                # Set timestamp to None for memory-only buffer updates
                with open(f_path, 'r') as fh:
                    self._update_buffer(fh.read())
                while (ff_end - self.update_period) >= self.next_update:
                    self._update_buffer('{}')

            for idx, f in enumerate(backup_files):
                if idx == 0:
                    # set the first update time to correspond to the oldest backup file
                    # before we attempt to do an update and fastforward
                    self.next_update = parse_log_time(f.split('/')[-1])
                if idx == (backup_count - 1):
                    # Last backup file, fastforward to present
                    update_and_ff(f, datetime.now())
                else:
                    # More backup files, only fastforward to the next one
                    next_filetime = parse_log_time(backup_files[idx + 1].split('/')[-1])
                    update_and_ff(f, next_filetime)
        else:
            self.disk_count = 0

        # Guarantees first call after instanciation will cause update
        self.next_update = datetime.now()

    def _get_datafile_name(self, timestamp):
        assert isinstance(timestamp, datetime)
        assert timestamp.tzinfo is None
        return '{}/{}{}'.format(self.path, timestamp.isoformat(), FILE_EXT)

    def _clean_excess_disk_files(self):
        while len(self.disk_files) > self.disk_count:
            os.remove(self.disk_files.pop(0))

    def add_data(self, timestamp, state):
        assert isinstance(timestamp, datetime)
        if timestamp >= self.next_update:
            self._update_buffer(state, storage_time=timestamp)

    def _update_buffer(self, state, storage_time=None):
        self.in_memory.append(state)
        self.next_update += self.update_period

        if storage_time and (self.disk_count > 0):
            assert isinstance(storage_time, datetime)
            data_file = self._get_datafile_name(storage_time)
            with open(data_file, 'w') as f:
                json.dump(state, f)
            self.disk_files.append(data_file)
            self._clean_excess_disk_files()

    def dump(self):
        return self.in_memory


class BufferCollection():
    """Defines the buffers to be maintained"""
    def __init__(self, buffer_dir):
        self.buffers = {
            'minute': HistoryBuffer(60, 2, path=buffer_dir + '/minute'),
            'hour': HistoryBuffer(60 * 60, 60, path=buffer_dir + '/hour'),
            'last': HistoryBuffer(FETCH_PERIOD, FETCH_PERIOD)}

    def dump(self, name):
        return self.buffers[name].dump()

    def add_data(self, timestamp, data):
        for buf in self.buffers.keys():
            self.buffers[buf].add_data(timestamp, data)


class BufferUpdater():
    """Class that fetchs and pushes that fetched update to BufferCollection
    Args:
        headers_cb (method): a callback method that returns a dictionary
            of headers to be used for mesos state-summary requests
    """
    def __init__(self, buffer_collection, headers_cb):
        self.buffer_collection = buffer_collection
        self.headers_cb = headers_cb

    def update(self):
        self.buffer_collection.add_data(*fetch_state(self.headers_cb))


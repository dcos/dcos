#!/opt/mesosphere/bin/python

import http.client
import sys
import time


def main():
    if len(sys.argv) != 2:
        print('Usage: dcos-net-observer.py APP', file=sys.stderr)
        sys.exit(1)
    app = sys.argv[1]
    while status(app):
        time.sleep(5)
    sys.exit(2)


def status(app):
    conn = http.client.HTTPConnection("localhost:62080")
    conn.request("GET", "/status?application={app}".format(app=app))
    response = conn.getresponse()
    return response.status == 204 or response.status == 200


if __name__ == "__main__":
    main()

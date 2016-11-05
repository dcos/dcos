import http.server
import os
import socketserver
from multiprocessing import Process


def launch_server(directory):
    os.chdir("resources/repo")
    httpd = socketserver.TCPServer(
        ("", 8000),
        http.server.SimpleHTTPRequestHandler)
    httpd.serve_forever()


class TestRepo:

    def __init__(self, repo_dir):
        self.__dir = repo_dir

    def __enter__(self):
        self.__server = Process(target=launch_server, args=(self.__dir))
        self.__server.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.__server.join()

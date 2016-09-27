from history.server import on_starting_server


bind = '0.0.0.0:15055'
workers = 1


def on_starting(server):
    on_starting_server(server)

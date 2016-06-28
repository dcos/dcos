FROM python:3.4.4-slim
RUN pip install requests
RUN apt-get update && apt-get install -y nmap curl
COPY test_server.py /opt/test_server.py
RUN chmod ugo+rx /opt/test_server.py
ENTRYPOINT ["/opt/test_server.py"]
EXPOSE 9080
USER nobody
LABEL description="Simple HTTP server used by integration tests"

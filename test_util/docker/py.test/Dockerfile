FROM python:3.4.4-slim
RUN pip install \
    beautifulsoup4 \
    boto3 \
    dnspython3 \
    kazoo \
    pytest \
    requests \
    retrying \
    teamcity-messages
ADD integration_test.py /integration_test.py
ADD test_wrapper.sh /test_wrapper.sh
CMD bash /test_wrapper.sh

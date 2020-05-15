FROM docker:19.03.0-dind

ENV PATH /usr/local/bin:$PATH
ENV LANG C.UTF-8

RUN apk --no-cache add git python3 python3-dev make gcc libc-dev libffi-dev openssl-dev g++

COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["entrypoint.sh"]
CMD []

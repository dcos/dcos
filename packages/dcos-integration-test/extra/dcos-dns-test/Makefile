CC=gcc
CFLAGS=-Wall -Werror -std=gnu11

dns-test-prog: dns-test-prog.o bpf-helper.o
	gcc $(CFLAGS) -o dns-test-prog dns-test-prog.o bpf-helper.o
dns-test-prog.o: dns-test-prog.c bpf-helper.h
	gcc $(CFLAGS) -c -o dns-test-prog.o dns-test-prog.c
bpf-helper.o: bpf-helper.c bpf-helper.h
	gcc $(CFLAGS) -c -o bpf-helper.o bpf-helper.c

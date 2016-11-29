CC=gcc
CFLAGS=-Wall -Werror -std=gnu11

test-prog: test-prog.o bpf-helper.o
	gcc $(CFLAGS) -o test-prog test-prog.o bpf-helper.o
test-prog.o: test-prog.c bpf-helper.h
	gcc $(CFLAGS) -c -o test-prog.o test-prog.c
bpf-helper.o: bpf-helper.c bpf-helper.h
	gcc $(CFLAGS) -c -o bpf-helper.o bpf-helper.c

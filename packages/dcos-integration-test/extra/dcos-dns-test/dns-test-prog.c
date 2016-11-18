#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/unistd.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <unistd.h>

#include <assert.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <errno.h>
#include <stdlib.h>
#include <netdb.h>

#include "bpf-helper.h"

#define VALUE_TESTING_EXPRESS_RECORDS 36

int main() {
	struct hostent *he;
	char *h_addr;
	int len;

	struct bpf_labels l = {
		.count = 0,
	};
	struct sock_filter filter[] = {
		LOAD_SYSCALL_NR,
		SYSCALL(__NR_socket, JUMP(&l, socket)),
		ALLOW,

		LABEL(&l, socket),
		ARG(0),
		JEQ(AF_INET, JUMP(&l, inetish)),
		JEQ(AF_INET6, JUMP(&l, inetish)),
		ALLOW,

		LABEL(&l, inetish),
		ARG(1),
		JEQ(SOCK_STREAM, ERRNO(EPERM)),
		ALLOW,
	};

	struct sock_fprog prog = {
		.filter = filter,
		.len = (unsigned short)(sizeof(filter)/sizeof(filter[0])),
	};

	bpf_resolve_jumps(&l, filter, sizeof(filter)/sizeof(*filter));

	if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) {
		perror("prctl(NO_NEW_PRIVS)");
		return 1;
	}

	if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog)) {
		perror("prctl(SECCOMP)");
		return 1;
	}

	assert(socket(AF_INET, SOCK_STREAM, 0) == -1 && errno == EPERM);
	assert(socket(AF_INET6, SOCK_STREAM, 0) == -1 && errno == EPERM);
	assert(socket(AF_INET, SOCK_DGRAM, 0) > 0);

	assert(he = gethostbyname2("value.testing.express", AF_INET));

        for (len = 0; he->h_addr_list[len]; len++);


	assert(len == VALUE_TESTING_EXPRESS_RECORDS);

}

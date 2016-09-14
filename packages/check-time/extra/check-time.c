#include <stdlib.h>
#include <stdio.h>
#include <sys/timex.h>
#include <string.h>
#include <errno.h>

#define USEC_PER_MSEC 1000L
#define MAX_EST_ERROR_US 100L * USEC_PER_MSEC /* 100 millisecond */

int main() {
	struct timex tx = {0};
	int rc;
	long long int error;

	if (getenv("IGNORE_CHECK_TIME")) {
		fprintf(stderr, "check-time ignoring time, passing no matter what\n");
		return 0;
	}

	rc = adjtimex(&tx);
	error = tx.esterror - MAX_EST_ERROR_US;

	if (rc == TIME_BAD)
		fprintf(stderr, "Time is marked as bad\n");
	else if (rc == -1)
		perror("adjtimex");
	/* This is to check if NTP thinks the clock is unstable */
	else if (error > 0)
		fprintf(stderr, "Max estimated error exceeded by: %lld(usec)\n", error);
	/* If NTP is down for ~16000 seconds, the clock will go unsync, based on
	 * modern kernels. Unfortunately, even though there are a bunch of other
	 * heuristics in the timex struct, it doesn't make a ton of sense to look
	 * at them. Maybe in the future we can do something smarter.
	 */
	else if (tx.status & STA_UNSYNC)
		fprintf(stderr, "Time not in sync\n");
	else
		return 0;
	return 1;
}

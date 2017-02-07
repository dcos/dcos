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

    const char *enable_check_time = getenv("ENABLE_CHECK_TIME");
    if (enable_check_time == NULL) {
        fprintf(stderr, "ENABLE_CHECK_TIME unset. internal consistency is broken. failing hard.\n");
        return 1;
    }

    if (strcmp(enable_check_time, "false") == 0) {
        // Skipping checking time as requested by user via configuration.
        fprintf(stderr, "Time synchronization check has been disabled. Skipping NTP check. If clocks drift, odd bugs may appear.\n");
        return 0;
    } else if (strcmp(enable_check_time, "true") == 0) {
        // Fall out and check time is synchronized.
    } else {
        fprintf(stderr, "ENABLE_CHECK_TIME is something other than 'true' or 'false'. "
            "internal consistency is broken. failing hard.\n");
        return 1;
    }


    fprintf(stderr, "Checking whether time is synchronized using the kernel adjtimex API.\n");
    fprintf(stderr, "Time can be synchronized via most popular mechanisms (ntpd, chrony, systemd-timesyncd, etc.)\n");

    rc = adjtimex(&tx);
    if (rc == -1) {
        perror("adjtimex");
        fprintf(stderr, "adjtimex() returned -1 indicating error. Unable to determine clock sync. See above perror message for details.\n");
        return 1;
    }

    if (rc == TIME_ERROR) {
        fprintf(stderr, "Time is not synchronized / marked as bad by the kernel.\n");
        return 1;
    }

    // This is to check if NTP thinks the clock is unstable
    error = tx.esterror - MAX_EST_ERROR_US;
    if (error > 0) {
        fprintf(stderr, "Clock is less stable than allowed. Max estimated error exceeded by: %lld(usec)\n", error);
        return 1;
    }

    /* If NTP is down for ~16000 seconds, the clock will go unsync, based on
     * modern kernels. Unfortunately, even though there are a bunch of other
     * heuristics in the timex struct, it doesn't make a ton of sense to look
     * at them. Maybe in the future we can do something smarter.
     */
    if (tx.status & STA_UNSYNC) {
        fprintf(stderr, "Clock is out of sync / in unsync state. Must be synchronized for proper operation.\n");
        return 1;
    }

    // All time sync check passed, clock is in sync.
    fprintf(stderr, "Time is in sync!\n");
    return 0;
}

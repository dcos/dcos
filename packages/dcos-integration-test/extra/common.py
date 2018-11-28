import pytest

# Mute Flaky Integration Tests with custom pytest marker.
# Rationale for doing this is mentioned at DCOS-45308
xfailflake = pytest.mark.xfail(strict=False)

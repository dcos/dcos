package test

import (
	"context"
	"os"
	"testing"

	"github.com/dcos/client-go/dcos"
	"github.com/stretchr/testify/assert"
)

// MASTER_HOSTS
// PUBLIC_SLAVE_HOSTS
// SLAVE_HOSTS
// EXPECTED_DCOS_VERSION

func TestClusterStructure(t *testing.T) {
	// var masterHosts, publicSlaveHosts, slaveHosts, expectedDCOSVersion string

	// test main should check if expected variables are set.
	expectedDCOSVersion := os.Getenv("EXPECTED_DCOS_VERSION")

	dcos, err := dcos.NewClient()

	if !assert.NoError(t, err) {
		t.FailNow()
	}

	h, _, err := dcos.Health.V1SystemHealth(context.TODO())

	assert.NoError(t, err)

	assert.Equal(t, expectedDCOSVersion, h.DcosVersion)
}

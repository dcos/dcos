#!/bin/bash

AWS_URL="http://169.254.169.254/latest/dynamic/instance-identity/document"

AZURE_REGION_URL="http://169.254.169.254/metadata/instance/compute/location?api-version=2017-08-01&format=text"
AZURE_FD_URL="http://169.254.169.254/metadata/instance/compute/platformFaultDomain?api-version=2017-04-02&format=text"

GCP_METADATA_URL="http://metadata.google.internal/computeMetadata/v1/instance/zone"


function aws() {
    METADATA="$(curl -f -m3 $AWS_URL 2>/dev/null)"
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "unable to fetch aws region/zone. URL $AWS_URL. Ret code $rc" >&2
        exit 1
    fi
    REGION=$(echo $METADATA | grep -Po "\"region\"\s+:\s+\"(.*?)\"" | cut -f2 -d: | tr -d ' \"')
    ZONE=$(echo $METADATA | grep -Po "\"availabilityZone\"\s+:\s+\"(.*?)\"" | cut -f2 -d: | tr -d ' \"')
    echo "{\"fault_domain\":{\"region\":{\"name\": \"aws/$REGION\"},\"zone\":{\"name\": \"aws/$ZONE\"}}}"
}

function azure() {
    REGION=$(curl -f -m3 -H Metadata:true "$AZURE_REGION_URL" 2>/dev/null)
    rc=$?
    if [ $rc -ne 0 ]; then
      echo "unable to fetch azure region. URL $AZURE_REGION_URL. Ret code $rc" >&2
      exit 1
    fi

    FAULT_DOMAIN=$(curl -f -m3 -H Metadata:true "$AZURE_FD_URL" 2>/dev/null)
    rc=$?
    if [ $rc -ne 0 ]; then
      echo "unable to fetch azure fault domain. URL $AZURE_FD_URL. Ret code $rc" >&2
      exit 1
    fi

    echo "{\"fault_domain\":{\"region\":{\"name\": \"azure/$REGION\"},\"zone\":{\"name\": \"azure/$FAULT_DOMAIN\"}}}"
}

function gcp() {
    BODY=$(curl -f -m3 -H "Metadata-Flavor: Google" "$GCP_METADATA_URL" 2>/dev/null)
    rc=$?
    if [ $rc -ne 0 ]; then
      echo "unable to fetch gcp metadata. URL $GCP_METADATA_URL. Ret code $rc" >&2
      exit 1
    fi

    ZONE=$(echo "$BODY" | sed 's@^projects/.*/zones/\(.*\)$@\1@')
    REGION=$(echo "$ZONE" | sed 's@\(.*-.*\)-.*@\1@')

    echo "{\"fault_domain\":{\"region\":{\"name\": \"gcp/$REGION\"},\"zone\":{\"name\": \"gcp/$ZONE\"}}}"
}

function main() {
    if [ $# -eq 1 ]; then
        case $1 in
            --aws) aws; exit 0;;
            --azure) azure; exit 0;;
            --gcp) gcp; exit 0;;
        esac
        echo "invalid parameter $1. Must be one of --aws, --azure or --gcp"
        exit 1
    fi

    # declare PROVIDERS as an empty array
    PROVIDERS=()

    # try aws first
    curl -f -q -m1 "$AWS_URL" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        PROVIDERS+=("aws")
    fi

    # try azure
    curl -f -q -m1 -H 'Metadata:true' "$AZURE_REGION_URL" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        PROVIDERS+=("azure")
    fi

    # try gcp
    curl -f -q m1 -H "Metadata-Flavor: Google" "$GCP_METADATA_URL" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        PROVIDERS+=("gcp")
    fi

    if [ ${#PROVIDERS[@]} -eq 0 ]; then
        "ERROR: unable to detect cloud provider. Use explicit parameter --aws, --azure, or --gcp" >&2
        exit 1
    fi

    if [ ${#PROVIDERS[@]} -gt 1 ]; then
        echo "ERROR: found multiple cloud providers: ${PROVIDERS[@]}" >&2
        exit 1
    fi

    provider=${PROVIDERS[0]}
    case $provider in
        "aws") aws; exit 0;;
        "gcp") gcp; exit 0;;
        "azure") azure; exit 0;;
        *) echo "ERROR: Unknown cloud provider $provider" >&2; exit 1;;
    esac
}

main $@

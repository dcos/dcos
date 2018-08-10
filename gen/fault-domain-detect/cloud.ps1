$AZURE_REGION_URL="http://169.254.169.254/metadata/instance/compute/location?api-version=2017-08-01&format=text"
$AZURE_FD_URL="http://169.254.169.254/metadata/instance/compute/platformFaultDomain?api-version=2017-04-02&format=text"

function azure() {
    $headers = @{"Metadata" = "true"}

    try {
        $r = Invoke-WebRequest -headers $headers $AZURE_REGION_URL -UseBasicParsing
    }
    catch [Exception] {
        write-error "unable to fetch azure region. URL $AZURE_REGION_URL. Error: ${_.Exception.Message}"
        exit 1
    }
    $REGION = $r.Content
    
    try {
        $r = Invoke-WebRequest -headers $headers $AZURE_FD_URL -UseBasicParsing
    }
    catch [Exception] {
        write-error "unable to fetch azure fault domain. URL $AZURE_FD_URL. Error: ${_.Exception.Message}"
        exit 1 
    }
    $FAULT_DOMAIN = $r.Content
    
    write-host "{`"fault_domain`":{`"region`":{`"name`": `"azure/$REGION`"},`"zone`":{`"name`": `"azure/$FAULT_DOMAIN`"}}}"
}

if ($args.count -eq 1) {
    switch($args[0]) {
        "--azure" {
             azure
             exit 0
            }
        default {
            write-error "invalid parameter ${args[0]}. Must be --azure"
            exit 1
        }
    }
}

#assume it is azure
azure
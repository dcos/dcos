# Generates setup / config files for DC/OS

## Overview

`gen` is the library responsible for generating static configuration for DC/OS cluster nodes from configuration parameters. This is achieved in part with a custom template engine whose primary feature is generating a parameter schema from a template. To see an example of this in action, check out the [DC/OS Settings Template](dcos-config.yaml)

## Directories
* `aws/`: AWS Cloudformation templates used in both simple and advanced Cloudformation templates
* `azure/`: templates used for Azure Resource Manager deployments
* `build_deploy/`: instructions for how to construct the templates and associated artifacts per deployment method
* `coreos` and `coreos-aws`: templated add-ons for CoreOS
* `ip-detect`: commonly used ip-detect scripts which can be pulled up as defaults

## Notable modules
* `__init__.py`: contains the combined methods for generating a complete deployment artifacts for a given configuration
* `calc.py`: methods for top-level option determination and validation
* `internals.py`: tools for defining required arguments as well how to conditionally resolve them
* `template.py`: custom templating engine

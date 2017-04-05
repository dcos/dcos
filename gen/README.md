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

## Deployment Artifacts
The artifacts configured by gen templates and built by pkgpanda are actually delivered to hosts via one of the deployment methods crafted in the `do_create` function of the modules in `gen.build_deploy`.

## Templates
The modules `gen.build_deploy.aws` and `gen.build_deploy.azure` provide templates that interact directly with the specific provider services and APIs. By leveraging the native tools of a cloud provider, DC/OS can be spun up much faster with appropriate configurations. The downside is that relying on provider APIs can make upgrading much harder as many more settings outside of DC/OS need to be touched. Finally, some settings need to be baked into a template as provider APIs might not allow the required level of configuration flexibility.

## Onprem Installer
The on-prem installer is a docker image that is loaded with an entry-point for the program `dcos_installer` (hosted in the top-level of this repository) as well as the complete set of built packages. The installer can:
* use SSH to push packages to hosts
* call gen to configure DC/OS to the fullest
* generate configured artifacts for other provisioning methods

The [Dockerfile](gen/build_deploy/bash/Dockerfile.in) is templated and must be processed by gen to inject the build-specific artifact paths. The setup of the installer software is [easily handled](gen/build_deploy/bash/Dockerfile.in) by extracting the installer bootstrap tarball to /opt/mesosphere and sourcing `/opt/mesosphere/environment.export`

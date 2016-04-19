## Initialization

- Install the Azure CLI
https://azure.microsoft.com/en-us/documentation/articles/xplat-cli/#configure

- Login to your account on the Azure CLI
https://azure.microsoft.com/en-us/documentation/articles/xplat-cli-connect/

## Azure Resource Browser

https://resources.azure.com/

## Azure Resource Manager (ARM) Reference Material

* [Authoring ARM Templates](https://azure.microsoft.com/en-us/documentation/articles/resource-group-authoring-templates/)
* [ARM Template Functions](https://azure.microsoft.com/en-us/documentation/articles/resource-group-template-functions/)
* [ARM Schema Definitions](https://github.com/Azure/azure-resource-manager-schemas/tree/master/schemas)
* [Examples](https://github.com/azure/azure-quickstart-templates)

## Schema and apiVersions

The recommendation from Microsoft as of 2015-09-17 is to develop ARM templates
with the following versions:

* Schema: http://schema.management.azure.com/schemas/2015-01-01/deploymentTemplate.json#
* apiVersions (all but Storage): 2015-06-15
* Storage apiVersions: 2015-05-01-preview

## Virtual Machine Scale Sets

virtualMachineScaleSets is a new feature that Microsoft is developing similar
to autoscale groups. It is not generally available yet but will be made
available to an early access group on Oct. 1. There is an example of how this
will work in Ross' [azure-myriad](https://github.com/gbowerman/azure-myriad/)
and
[mesos-swarm-marathon](https://github.com/gbowerman/azure-quickstart-templates/tree/master/mesos-swarm-marathon)
examples.

## Azure Subscription and Service Limits

[Azure Subscription and Service Limits, Quotas, and Constraints](https://azure.microsoft.com/en-us/documentation/articles/azure-subscription-service-limits/)

Key resource limitations for a DC/OS stack on Azure:

| RESOURCE | DEFAULT LIMIT | MAXIMUM LIMIT |
| -------- | ------------- | ------------- |
| Cores per subscription | 20 | 10000 |
| Storage accounts per subscription | 100 | 100 |
| Local networks per subscription | 10 | 500 |
| Reserved IPs per subscription | 20 | 100 |

## VMs per Storage Account

We use logic to spread out VMs across Storage Accounts to prevent I/O limitation
per Storage Account. Parameter `vmsPerStorageAccount` lets you adjust number
of Private Slaves per Storage Acount. Currently there is a limit of 36*36 = 1296
Storage Accounts per Subscription.

## TODO

* Validate uniquename input, must be between 3-24 char in length and use numbers
  and lower-case letters only.
* Support or protect against single-quote characters in cloud config templates.
  Currently, a single quote character will break the ARM template when injected.
  The only approach that seems possible at this point (without some additional
  help from Microsoft) is referencing a single quote character with an ARM
  template variable, i.e. variables('singleQuote').

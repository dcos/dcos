TERRAFORM_VERSION := 0.12.26
OS ?= $(shell uname|tr A-Z a-z)

# Path to Terraform binary.
TERRAFORM ?= ./terraform.bin

terraform.initialized: $(TERRAFORM) main.tf
	@echo "##teamcity[blockOpened name='terraform-init' description='Terraform initialization']"
	$(TERRAFORM) init -input=false --upgrade | tee terraform.log
	mv terraform.log $@
	@echo "##teamcity[blockClosed name='terraform-init']"

terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip:
	wget -nv https://releases.hashicorp.com/terraform/$(TERRAFORM_VERSION)/$@

$(TERRAFORM): terraform_$(TERRAFORM_VERSION)_$(OS)_amd64.zip
	unzip -n $<;
	mv ./terraform $(TERRAFORM);
	chmod +x $(TERRAFORM);

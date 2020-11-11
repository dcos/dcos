diagnostics_bundle_file = diagnostics-$(shell date +%Y-%m-%d_%H-%M-%S).zip

################################# DISGNOSTICS #################################

diagnostics_api = localhost:1050/system/health/v1/diagnostics
curl_cmd = curl
ifneq ($(TF_VAR_variant), open)
	diagnostics_api = --unix-socket /var/run/dcos/dcos-diagnostics.sock http:/system/health/v1/diagnostics
	curl_cmd = sudo curl
endif

.PHONY: diagnostics
diagnostics: $(diagnostics_bundle_file)

# Start diagnostics bundle creation.
diagnostics-%.started: cluster.json
	@echo "##teamcity[blockOpened name='diagnostics-bundle' description='Download Diagnostics bundle']"
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<) -- \
		"$(curl_cmd) -X PUT $(diagnostics_api)/$*"
	touch $@

# Wait until diagnostics bundle is ready.
diagnostics-%.done: cluster.json diagnostics-%.started
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<) -- \
		"$(curl_cmd) -s $(diagnostics_api)/$* -o status.json; \
		until jq '.status' status.json | grep -q 'Done'; do cat status.json; $(curl_cmd) -s $(diagnostics_api)/$* -o status.json; sleep 5; done;"
	rm diagnostics-$*.started || true
	touch $@

# Download diagnostics bundle.
diagnostics-%.zip : cluster.json diagnostics-%.done
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<) -- \
		"$(curl_cmd) $(diagnostics_api)/$*/file -o $@"
	scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $(SSH_KEY) $(shell jq '.cluster_username.value' $<)@$(shell jq '.master_public_ips.value[0]' $<):/home/centos/$@ $@.work
	rm diagnostics-$*.done || true
	mv $@.work $@
	@echo "##teamcity[blockClosed name='diagnostics-bundle']"

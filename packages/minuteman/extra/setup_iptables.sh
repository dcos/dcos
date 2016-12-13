#!/bin/bash

set -euo pipefail
set -x

# http://stackoverflow.com/questions/2870992/automatic-exit-from-bash-shell-script-on-error
# Any subsequent(*) commands which fail will cause the shell script to exit immediately

## Cleanup old minuteman (NFQUEUE) rules
iptables --wait -D FORWARD -p tcp -m set --match-set minuteman dst,dst -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -j REJECT --reject-with icmp-port-unreachable || true
iptables --wait -D OUTPUT -p tcp -m set --match-set minuteman dst,dst -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -j REJECT --reject-with icmp-port-unreachable || true
iptables --wait -t raw -D PREROUTING -p tcp -m set --match-set minuteman dst,dst -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -j NFQUEUE --queue-balance 50:58 || true
iptables --wait -t raw -D OUTPUT -p tcp -m set --match-set minuteman dst,dst -m tcp --tcp-flags FIN,SYN,RST,ACK SYN -j NFQUEUE --queue-balance 50:58 || true

RULE="POSTROUTING -m ipvs --ipvs --vdir ORIGINAL --vmethod MASQ -m comment --comment Minuteman-IPVS-IPTables-masquerade-rule -j MASQUERADE"

if ! iptables --wait -t nat -C ${RULE}; then
  echo "Minuteman IPTables Rule not found: ${RULE}"
  echo "Inserting Rule"
  iptables --wait -t nat -I ${RULE} && echo "Rule successfully inserted"
else
  echo "Minuteman IPTables rule found"
fi


### How to Test It
Tests of the functionality of etcd discovery locally requires a working zookeeper.

`make default` is all you need.

Or You can split the steps by:
- run `make start-zk` to initialize a zookeepr
- run `make tests` to execute the integration tests
- run `make stop-zk` to remove the zookeepr

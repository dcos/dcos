# TODO / Notes

 - Cannot change roles after startup / initial install currently. Need a full-reinstall.
 - Should enable managing systemd service files / adding them to dcos.target.wants from packages.
 - Can't upgrade / change dcos.target, dcos-setup.service, dcos-download.service, mesos-master.service, mesos-slave.service
 - Cannot add repository_url, masters after startup
 - mkpanda should use Repository.has_package()
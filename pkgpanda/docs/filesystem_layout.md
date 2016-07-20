# File System Layout

Host overall filesystem layout.

```bash
/etc/mesosphere/roles/{master,slave}
/etc/mesosphere/setup-flags/
    active.json
    repository-url
/etc/systemd/dcos.target.wants/
    mesos-master.service
/opt/mesosphere/
    bin/
    lib/
    etc/
    environment
    active/
        mesos -> /opt/mesosphere/packages/mesos--0.22.0
        java -> ...
        zookeeper -> ...
    packages/
    mesos-config--123/
        etc/
    mesos--0.22.0/
        bin/
        lib/
        libexec/
        ...
        dcos.target.wants_master/
            mesos-master.service
    java--ranodmversionstring/
        ...
    zookeeper--0.123/
        ...
```


## Package layout

```bash
pkginfo.json        # json file describing list of dependencies / requires of package either
                    # by name (mesos) or by specific package id (mesos-0.22)
                    # Also lists environment variables to be loaded into the global environment.
etc/
bin/
lib/
dcos.target.wants/
    foo.service
    {role}/
        bar.service
```




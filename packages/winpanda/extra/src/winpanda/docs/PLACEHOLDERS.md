VARIABLE PLACEHOLDER NAMES RECOGNIZED BY THE WINPANDA APPLICATION
=================================================================

>_**NOTE.**_
    Currently all the variable placeholder names described in this document may
  be used in per DC/OS package _&lt;package_name&gt;.nssm.j2_ and
  _&lt;package_name&gt;.extra.j2_ configuration files. The DC/OS aggregated
  configuration object - _dcos-config-windows.yaml_ cannot use variables from
  the _PACKAGE CONTEXT_ (section 2.2), as it's not specific to processing a
  particular package.

-------------------------------------------------------------------------------



# 1. DC/OS General Configuration Variable Names
-----------------------------------------------

## 1.1 DCOS GENERAL CONTEXT
---------------------------

>_**NOTE.**_
    All the variable names from the section _2.1 "ISTOR GENERAL CONTEXT"_ are
  also available for use in the _DCOS GENERAL CONTEXT_.


**{{ master_priv_ipaddr }}** - master node's private IP-address
                                 (substitution example "172.16.7.46")

**{{ local_priv_ipaddr }}**  - local (agent) node's private IP-address
                                 (substitution example "172.16.3.63")

**{{ zk_client_port }}**     - zookeeper client port (on which zookeeper
                                 listens)
                                 (substitution example "2181")



# 2. DC/OS Installation Storage Layout Variable Names (Agent Node Specific)
-------------------------------------------------------------------------

## 2.1 INSTALATION STORAGE (ISTOR) GENERAL CONTEXT
--------------------------------------------------

>_**NOTE.**_
    These variables are available for use in any procedures which do not aim any
    particular package (meaning that a package ID is not available in the
    context). E.g. rendering the DC/OS aggregated configuration object -
    dcos-config-windows.yaml durin clean DC/OS deployment procedure.
    
>_**NOTE.**_
    All the variable names from the section _1.1 DCOS GENERAL CONTEXT_ are also
    available for use in the _ISTOR GENERAL CONTEXT_.


**{{ dcos_inst_dpath }}**   - DC/OS installation's (root) directory path
                            (substitution example "c:\dcos")                          

**{{ dcos_cfg_dpath }}**    - DC/OS installation's shared configuration
                            directory path. Per package sub-directories named
                            after package's name and containing config files
                            for individual DC/OS packages, are created below
                            this directory.
                            (substitution example "c:\dcos\conf")

**{{ dcos_work_dpath }}**   - DC/OS installation's shared work directory path.
                            Per package work sub-directories named after 
                            package's name, are created below this directory
                            for individual DC/OS packages.
                            (substitution example "c:\dcos\var\opt")
                            
**{{ dcos_run_dpath }}**    - DC/OS installation's shared runtime data directory
                            path. Per package runtime data sub-directories named
                            after package's name, are created below this
                            directory for individual DC/OS packages.
                            (substitution example "c:\dcos\var\run")
                            
**{{ dcos_log_dpath }}**    - DC/OS installation's shared log directory path.
                            Per package log sub-directories named after 
                            package's name, are created below this directory
                            for individual DC/OS packages.
                            (substitution example "c:\dcos\var\log")
                            
**{{ dcos_tmp_dpath }}**    - DC/OS installation's shared temporary directory
                            path. Any application may use it to store it's
                            temporary files.
                            (substitution example "c:\dcos\var\tmp")

**{{ dcos_bin_dpath }}**    - DC/OS installation's shared executables directory
                            path.
                            (substitution example "c:\dcos\bin")
                            
**{{ dcos_lib_dpath }}**    - DC/OS installation's shared libraries directory
                            path.
                            (substitution example "c:\dcos\lib")               


## 2.2 PACKAGE CONTEXT
----------------------

>_**NOTE.**_
    These variables are available for use only when a procedure aims a
  particular package (meaning that a package ID is available in the context),
  like package installation/deinstallation. E.g. rendering per DC/OS package
  _&lt;package_name&gt;.nssm.j2_ and _&lt;package_name&gt;.extra.j2_
  configuration files during package installation/deinstalation procedures.

>_**NOTE.**_
    All the variable names from sections _1.1 "DCOS GENERAL CONTEXT"_ and
  _2.1 "ISTOR GENERAL CONTEXT"_ are also available for use in the _PACKAGE
  CONTEXT_.


**{{ pkg_inst_dpath }}**    - package installation's (root) directory path
                            (substitution example "c:\dcos\packages\mesos--1")

**{{ pkg_log_dpath }}**     - package's dedicated logs directory path
                            (substitution example "c:\dcos\var\log\mesos")

**{{ pkg_rtd_dpath }}**     - package's dedicated runtime data directory path
                            (substitution example "c:\dcos\var\run\mesos")

**{{ pkg_work_dpath }}**    - package's dedicated work directory path
                            (substitution example "c:\dcos\var\opt\mesos")
                          
**{{ pkg_shrcfg_dpath }}**  - package's dedicated configuration directory path
                            within the DC/OS installation's shared configuration
                            directory
                            (substitution example "c:\dcos\conf\mesos")
                          


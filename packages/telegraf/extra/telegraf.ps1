 param (
    [string]$pkg_inst_dpath,
    [string]$local_ip
 )

$conf = "$pkg_inst_dpath\etc\telegraf.conf"
Add-Content $conf '
[global_tags]
[agent]
  interval = "10s"
  round_interval = true
  metric_batch_size = 1000
  metric_buffer_limit = 90000
  collection_jitter = "0s"
  flush_interval = "10s"
  flush_jitter = "0s"
  precision = ""
  debug = false
  quiet = false
  logfile = ""
  hostname = ""
  omit_hostname = false
[[inputs.cpu]]
  percpu = false
  totalcpu = true
  collect_cpu_time = false
  report_active = false
[[inputs.mem]]
[[inputs.disk]]
[[inputs.swap]]
[[inputs.net]]
[[inputs.win_perf_counters]]
[[inputs.system]]
[[inputs.internal]]
  collect_memstats = true
     [[inputs.win_perf_counters.object]]
        ObjectName = "Processor"
        Instances = ["*"]
        Counters = [
          "% Idle Time",
          "% Interrupt Time",
          "% Privileged Time",
          "% User Time",
          "% Processor Time",
          "% DPC Time",
        ]
        Measurement = "win_cpu"
        IncludeTotal=true
     [[inputs.win_perf_counters.object]]
        ObjectName = "Diagnostics"
        Instances = ["*"]
        Counters = [
          "Elapsed Time",
          "% Processor Time",
        ]
        Measurement = "dcos_diagnostics"


[[inputs.docker]]
   endpoint = "ENV"

[[inputs.mesos]]

  timeout = 100 '

$slaves = '   slaves = ["http://' + $local_ip + ':5051"]'
Add-Content $conf $slaves
Add-Content $conf '   slave_collections = [
     "resources",
     "agent",
     "system",
     "executors",
     "tasks",
     "messages",
]
[[outputs.prometheus_client]]
  listen = ":61091"
  expiration_interval = "60s"
'
& $pkg_inst_dpath\bin\telegraf.exe --service install --config $conf
Start-Service -Name telegraf

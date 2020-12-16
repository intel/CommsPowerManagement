#Introduction

The pkgpower.py script is python plugin designed for collectd.
This plugin collects "current power and TDP power in watts" for
all packages of the system.

This plugin uses "/sys/devices/virtual/powercap/intel-rapl" sysfs
to read about the power information. So, The minimum kernel
version required is 3.13

#Integration of the plugin with collectd

The plugin should be used with collectd, so to enable the
plugin in collectd run, follow below steps.

1)Clone the collectd code
2)Build and install it.
3)Edit and uncomment below lines of python plugin section from
collectd.conf file to enable the pkgpower.py.

    #LoadPlugin python

    #<Plugin python>
    #       ModulePath "<specify folder location where pkgpower.py exists>"
    #       Import "pkgpower"
    #
    #       <Module pkgpower>
    #       </Module>
    #</Plugin>

5)Also enable collectd logging in collectd.conf.

4)Run the collectd binary, which fetches the power stats and records at
at collectd stats location.

#Expected output
Successfully started collectd with pkgpower enabled should not show any
python errors and below successful log should be seen.

    #/opt/collectd/sbin/collectd -f
    plugin_load: plugin "python" successfully loaded.


The power stats folders should be created and populated by collectd
inside the collectd stats location as in below format.

TDP power location:             "package-<package-number>-TDP-power/power-<date>"
Current Package power location: "package-<package-number>-power/power-<date>"

    #Example output location:
    /opt/collectd/var/lib/localhost/package-0-power/power-2020-03-23
    /opt/collectd/var/lib/localhost/package-1-power/power-2020-03-23
    /opt/collectd/var/lib/localhost/package-0-TDP-power/power-2020-03-23
    /opt/collectd/var/lib/localhost/package-1-TDP-power/power-2020-03-23

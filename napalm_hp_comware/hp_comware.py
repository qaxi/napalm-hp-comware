"""
Napalm driver for HpComware Devices

Read https://napalm.readthedocs.io for more information.
"""
from netmiko import ConnectHandler, FileTransfer, InLineTransfer
from netmiko import __version__ as netmiko_version

import sys
import re


from napalm_base.utils import py23_compat
from napalm_base.base import NetworkDriver
from napalm_base.exceptions import (
    ConnectionException,
    SessionLockedException,
    MergeConfigException,
    ReplaceConfigException,
    CommandErrorException,
    )


class HpComwareDriver(NetworkDriver):
    """ Napalm driver for HpComware devices.  """
    _MINUTE_SECONDS = 60
    _HOUR_SECONDS = 60 * _MINUTE_SECONDS
    _DAY_SECONDS = 24 * _HOUR_SECONDS
    _WEEK_SECONDS = 7 * _DAY_SECONDS
    _YEAR_SECONDS = 365 * _DAY_SECONDS

    def __init__(self, hostname, username, password, timeout=60, optional_args=None):
        """ Constructor.
        
        Additional Optional args:
            - proxy_host - SSH hopping station 
            - proxy_username - hopping station username
            - proxy_password - hopping station password
            - proxy_port - hopping station ssh port
            TODO: 
                Set proxy host to work with user/password 
                (works only with preloaded ssh-key in the ssh-agent for now)
        """

        self.device = None
        self.hostname = hostname
        self.username = username
        self.password = password
        self.timeout = timeout

        if optional_args is None:
            optional_args = {}

        # proxy part
        self.proxy_host = optional_args.get('proxy_host', None)
        self.proxy_username = optional_args.get('proxy_username', None)
        self.proxy_password = optional_args.get('proxy_password', None)
        self.proxy_port = optional_args.get('proxy_port', None)
       

        # Check for proxy parameters and generate ssh config file
        if self.proxy_host:
            if self.proxy_port and self.proxy_username: 
                print("Generate SSH proxy config file for hopping station: {}".format(self.proxy_host))
                self.ssh_proxy_file = self._generate_ssh_proxy_file()
            else:
                raise ValueError("All proxy options must be specified ")
        else:
            self.ssh_proxy_file = None

        # Netmiko possible arguments
        netmiko_argument_map = {
            'ip': None,
            'username': None,
            'password': None,
            'port': None,
            'secret': '',
            'verbose': False,
            'keepalive': 30,
            'global_delay_factor': 1,
            'use_keys': False,
            'key_file': None,
            'ssh_strict': False,
            'system_host_keys': False,
            'alt_host_keys': False,
            'alt_key_file': '',
            'ssh_config_file': None,
        }
         

        fields = netmiko_version.split('.')
        fields = [int(x) for x in fields]
        maj_ver, min_ver, bug_fix = fields
        if maj_ver >= 2:
            netmiko_argument_map['allow_agent'] = False
        elif maj_ver == 1 and min_ver >= 1:
            netmiko_argument_map['allow_agent'] = False

        # Build dict of any optional Netmiko args
        self.netmiko_optional_args = {}
        for k, v in netmiko_argument_map.items():
            try:
                self.netmiko_optional_args[k] = optional_args[k]
            except KeyError:
                pass
        if self.ssh_proxy_file:
            self.netmiko_optional_args['ssh_config_file'] = self.ssh_proxy_file


    
    def _generate_ssh_proxy_file(self):
        filename = 'ssh_proxy_'+ self.hostname
        fh = open(filename, 'w')
        fh.write('Host '+ self.hostname + '\n')
        fh.write('HostName '+ self.hostname + '\n')
        fh.write('User '+ self.proxy_username +'\n')
        fh.write('Port 22'+'\n')
        fh.write('StrictHostKeyChecking no\n')
        fh.write('ProxyCommand ssh '
                + self.proxy_username  +'@'+ self.proxy_host+' nc %h %p')
        fh.close()
        return filename

 
    def open(self):
        """Open a connection to the device."""
        self.device = ConnectHandler(
                device_type = 'hp_comware',
                host = self.hostname,
                username = self.username,
                password = self.password,
                **self.netmiko_optional_args)

    def close(self):
        """Close the connection to the device."""
        self.device.disconnect()

    def get_facts(self):
        """
        Returns a dictionary containing the following information:
         * uptime - Uptime of the device in seconds.
         * vendor - Manufacturer of the device.
         * model - Device model.
         * hostname - Hostname of the device
         * fqdn - Fqdn of the device
         * os_version - String with the OS version running on the device.
         * serial_number - Serial number of the device
         * interface_list - List of the interfaces of the device

        Example::

            {
            'uptime': 151005.57332897186,
            'vendor': u'Arista',
            'os_version': u'4.14.3-2329074.gaatlantarel',
            'serial_number': u'SN0123A34AS',
            'model': u'vEOS',
            'hostname': u'eos-router',
            'fqdn': u'eos-router',
            'interface_list': [u'Ethernet2', u'Management1', u'Ethernet1', u'Ethernet3']
            }

        """
        out_disable_pageing = self.device.send_command('screen-length disable')
        if 'configuration is disabled for current user' in out_disable_pageing:
            pass
        else:
            raise ValueError("Disable Pageing cli command error: {}".format(out_disable_pageing))
            sys.exit(" --- Exiting: try to workaround this ---")

        out_display_version = self.device.send_command("display version").split("\n")
        for line in out_display_version: 
            if "Software, Version " in line:
                ver_str = line.split("Version ")[-1]
            elif " uptime is " in line:
                uptime_str = line.split("uptime is ")[-1]
                # print("Uptime String : {}".format(uptime_str))
                # Exapmples of uptime_str
                # '57 weeks, 1 day, 7 hours, 53 minutes'
                # '2 years, 57 weeks, 1 day, 7 hours, 53 minutes'
                # '53 minutes'
                uptime = 0
                match = re.findall(r'(\d+)\s*(\w+){0,5}',uptime_str)
                for timer in match:
                    if 'year' in timer[1]:
                        uptime += int(timer[0]) * self._YEAR_SECONDS
                    elif 'week' in timer[1]:
                        uptime += int(timer[0]) * self._WEEK_SECONDS
                    elif 'day' in timer[1]:
                        uptime += int(timer[0]) * self._DAY_SECONDS
                    elif 'hour' in timer[1]:
                        uptime += int(timer[0]) * self._HOUR_SECONDS
                    elif 'minute' in timer[1]:
                        uptime += int(timer[0]) * self._MINUTE_SECONDS

        out_display_device = self.device.send_command("display device manuinfo")
        match = re.findall(r"""^Slot\s+(\d+):\nDEVICE_NAME\s+:\s+(.*)\nDEVICE_SERIAL_NUMBER\s+:\s+(.*)\nMAC_ADDRESS\s+:\s+([0-9A-F]{1,4}-[0-9A-F]{1,4}-[0-9A-F]{1,4})\nMANUFACTURING_DATE\s+:\s+(.*)\nVENDOR_NAME\s+:\s+(.*)""",out_display_device,re.M)
        snumber = set()
        vendor = set()
        hwmodel = set()
        for idx in match:
            slot,dev,sn,mac,date,ven = idx
            snumber.add(sn)
            vendor.add(ven)
            hwmodel.add(dev)
        
        out_display_current_config = self.device.send_command("display current-configuration")
        hostname = ''.join(re.findall(r'.*\s+sysname\s+(.*)\n',out_display_current_config,re.M))
        interfaces = re.findall(r'\ninterface\s+(.*)\n',out_display_current_config,re.M)
        facts = {
          "uptime": uptime,
          "vendor": py23_compat.text_type(','.join(vendor)),
          "os_version": py23_compat.text_type(ver_str),
          "serial_number": py23_compat.text_type(','.join(snumber)),
          "model": py23_compat.text_type(','.join(hwmodel)),
          "hostname": py23_compat.text_type(hostname),
          "fqdn": py23_compat.text_type(hostname),
          "interface_list": interfaces
        }
        return facts




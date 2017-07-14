"""
Napalm driver for HpComware Devices

Read https://napalm.readthedocs.io for more information.
"""
from netmiko import ConnectHandler, FileTransfer, InLineTransfer
from netmiko import __version__ as netmiko_version


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

    def is_alive(self):
        """ Returns a flag with the state of the SSH connection """
        return {
            'is_alive': self.device.remote_conn.trasport.is_active()
        }

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
        out_display_version = self.device.send_command("display version").split("\n")
	out_display_device = self.device.send_command("display device manuinfo").split("\n")

        for line in out_display_version: 
            if "Software, Version " in line:
                ver_str = line.split("Version")[-1]
            elif " uptime is " in line: 
                uptime_str = line.split("uptime is ")[-1]

        # display version 
        # HP Comware Platform Software
        # Comware Software, Version 5.20.105, Release 1809P10
        # Copyright (c) 2010-2015 Hewlett-Packard Development Company, L.P.
        # HP 5800-48G Switch with 1 Interface Slot uptime is 56 weeks, 5 days, 10 hours, 51 minutes

        # HP 5800-48G Switch with 1 Interface Slot with 2 Processors
        # 1024M   bytes SDRAM
        # 4M      bytes Nor Flash Memory
        # 512M    bytes Nand Flash Memory
        # Config Register points to Nand Flash

        # Hardware Version is Ver.B
        # CPLD Version is 003
        # BootRom Version is 301
        # [SubSlot 0] 48GE+4SFP Plus Hardware Version is Ver.B
        # [SubSlot 1] No Module

	# display device manuinfo
	# Slot 1:
	# DEVICE_NAME          : A5800-48G JC105A
	# DEVICE_SERIAL_NUMBER : CN1BBFT02S
	# MAC_ADDRESS          : B8AF-672E-6EA5
	# MANUFACTURING_DATE   : 2012-01-06
	# VENDOR_NAME          : HP
	# 
	# Power 1:
	# DEVICE_NAME          : NONE
	# DEVICE_SERIAL_NUMBER : NONE
	# MANUFACTURING_DATE   : NONE
	# VENDOR_NAME          : NONE
	# 
	# Fan 1:
	# DEVICE_NAME          : NONE
	# DEVICE_SERIAL_NUMBER : NONE
	# MANUFACTURING_DATE   : NONE
	# VENDOR_NAME          : NONE
	# 
	# Slot 2:
	# DEVICE_NAME          : A5800-48G JC105A
	# DEVICE_SERIAL_NUMBER : CN1BBFT01X
	# MAC_ADDRESS          : B8AF-672E-62C0
	# MANUFACTURING_DATE   : 2012-01-10
	# VENDOR_NAME          : HP
	# 
	# Power 1:
	# DEVICE_NAME          : NONE
	# DEVICE_SERIAL_NUMBER : NONE
	# MANUFACTURING_DATE   : NONE
	# VENDOR_NAME          : NONE
	# 
	# Fan 1:
	# DEVICE_NAME          : NONE
	# DEVICE_SERIAL_NUMBER : NONE
	# MANUFACTURING_DATE   : NONE
	# VENDOR_NAME          : NONE
	# 

        uptime = int(float(output_uptime))

        output = self.device.send_command("show version").split("\n")
        ver_str = [line for line in output if "Version" in line][0]
        version = self.parse_version(ver_str)

        sn_str = [line for line in output if "S/N" in line][0]
        snumber = self.parse_snumber(sn_str)

        hwmodel_str = [line for line in output if "HW model" in line][0]
        hwmodel = self.parse_hwmodel(hwmodel_str)

        output = self.device.send_command("show configuration")
        config = vyattaconfparser.parse_conf(output)

        if "host-name" in config["system"]:
            hostname = config["system"]["host-name"]
        else:
            hostname = None

        if "domain-name" in config["system"]:
            fqdn = config["system"]["domain-name"]
        else:
            fqdn = ""

        iface_list = list()
        for iface_type in config["interfaces"]:
            for iface_name in config["interfaces"][iface_type]:
                iface_list.append(iface_name)

        facts = {
          "uptime": int(uptime),
          "vendor": py23_compat.text_type("VyOS"),
          "os_version": py23_compat.text_type(version),
          "serial_number": py23_compat.text_type(snumber),
          "model": py23_compat.text_type(hwmodel),
          "hostname": py23_compat.text_type(hostname),
          "fqdn": py23_compat.text_type(fqdn),
          "interface_list": iface_list
        }

        return facts




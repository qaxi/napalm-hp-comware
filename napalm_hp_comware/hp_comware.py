"""
Napalm driver for HpComware Devices

Read https://napalm.readthedocs.io for more information.
"""
from netmiko import ConnectHandler, FileTransfer, InLineTransfer
from netmiko import __version__ as netmiko_version

import sys
import re


from napalm.base.utils import py23_compat
from napalm.base.base import NetworkDriver
from napalm.base.exceptions import (
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
        filename = '/var/tmp/ssh_proxy_'+ self.hostname
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


    def disable_pageing(self):
        """ Disable pageing on the device """
        out_disable_pageing = self.device.send_command('screen-length disable')
        if 'configuration is disabled for current user' in out_disable_pageing:
            pass
        else:
            raise ValueError("Disable Pageing cli command error: {}".format(out_disable_pageing))
            sys.exit(" --- Exiting: try to workaround this ---")


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
        self.disable_pageing()
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
        match = re.findall(r"""^Slot\s+(\d+):\nDEVICE_NAME\s+:\s+(.*)\nDEVICE_SERIAL_NUMBER\s+:\s+(.*)\nMAC_ADDRESS\s+:\s+([0-9a-fA-F]{1,4}-[0-9a-fA-F]{1,4}-[0-9a-fA-F]{1,4})\nMANUFACTURING_DATE\s+:\s+(.*)\nVENDOR_NAME\s+:\s+(.*)""",out_display_device,re.M)
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

    def get_mac_address_table(self):

        """
        Returns a lists of dictionaries. Each dictionary represents an entry in the MAC Address
        Table, having the following keys:
            * mac (string)
            * interface (string)
            * vlan (int)
            * active (boolean)
            * static (boolean)
            * moves (int)
            * last_move (float)

        However, please note that not all vendors provide all these details.
        E.g.: field last_move is not available on JUNOS devices etc.

        Example::

            [
                {
                    'mac'       : '00:1C:58:29:4A:71',
                    'interface' : 'Ethernet47',
                    'vlan'      : 100,
                    'static'    : False,
                    'active'    : True,
                    'moves'     : 1,
                    'last_move' : 1454417742.58
                },
                {
                    'mac'       : '00:1C:58:29:4A:C1',
                    'interface' : 'xe-1/0/1',
                    'vlan'       : 100,
                    'moves'     : 2,
                    'last_move' : 1453191948.11
                },
                {
                    'mac'       : '00:1C:58:29:4A:C2',
                    'interface' : 'ae7.900',
                    'vlan'      : 900,
                    'static'    : False,
                    'active'    : True,
                    'moves'     : None,
                    'last_move' : None
                }
            ]
        """
        # Disable Pageing of the device
        self.disable_pageing()

        # <device>display mac-address
        # MAC ADDR       VLAN ID  STATE          PORT INDEX               AGING TIME(s)
        # 2c41-3888-24a7 1        Learned        Bridge-Aggregation30     AGING
        # a036-9f00-1dfa 1        Learned        Bridge-Aggregation30     AGING
        # a036-9f00-29c5 1        Learned        Bridge-Aggregation31     AGING
        # a036-9f00-29c6 1        Learned        Bridge-Aggregation31     AGING
        # b8af-675c-0800 1        Learned        Bridge-Aggregation2      AGING
        out_mac_table = self.device.send_command('display mac-address')
        mactable = re.findall(r'^([0-9a-fA-F]{1,4}-[0-9a-fA-F]{1,4}-[0-9a-fA-F]{1,4})\s+(\d+)\s+(\w+)\s+([A-Za-z0-9-/]{1,40})\s+(.*)',out_mac_table,re.M)
        output_mactable = []
        record = {}
        for rec in mactable:
            mac,vlan,state,port,aging = rec
            record['mac'] = self.format_mac_cisco_way(mac)
            record['interface'] = self.normalize_port_name(port)
            record['vlan'] = vlan
            record['static'] = 'None'
            record['active'] = 'None'
            record['moves'] = 'None'
            record['last_move'] = 'None'
            output_mactable.append(record)
        return output_mactable     


    def format_mac_cisco_way(self,macAddress):
        """ 
        function formating mac address to cisco form 
        AA:BB:CC:DD:EE:FF
        """
        macAddress = macAddress.replace('-','')
        return macAddress[:2] +\
                ':'+macAddress[2:4]+\
                ':'+macAddress[4:6]+\
                ':'+macAddress[6:8]+\
                ':'+macAddress[8:10]+\
                ':'+macAddress[10:12]

    def get_arp_table(self):

        """
        Returns a list of dictionaries having the following set of keys:
            * interface (string)
            * mac (string)
            * ip (string)
            * age (float)

        Example::

            [
                {
                    'interface' : 'MgmtEth0/RSP0/CPU0/0',
                    'mac'       : '5C:5E:AB:DA:3C:F0',
                    'ip'        : '172.17.17.1',
                    'age'       : 1454496274.84
                },
                {
                    'interface' : 'MgmtEth0/RSP0/CPU0/0',
                    'mac'       : '5C:5E:AB:DA:3C:FF',
                    'ip'        : '172.17.17.2',
                    'age'       : 1435641582.49
                }
            ]

        """
        # Disable Pageing of the device
        self.disable_pageing()
        out_arp_table = self.device.send_command('display arp')
        arptable = re.findall(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F]{1,4}-[0-9a-fA-F]{1,4}-[0-9a-fA-F]{1,4})\s+(\d+)\s+([A-Za-z0-9-/]{1,40})\s+(\d+)\s+(\w+)\n',out_arp_table,re.M)
        output_arptable = []
        record = {}
        for rec in arptable:
            ip,mac,vlan,port,aging,arp_type = rec
            record['interface'] = self.normalize_port_name(port)
            record['mac'] = self.format_mac_cisco_way(mac)
            record['ip'] = ip
            record['vlan'] = vlan
            record['aging'] = aging 
            output_arptable.append(record)
        return output_arptable     


    def normalize_port_name(self,res_port):
        """ Convert Short HP interface names to long (ex: BAGG519 --> Bridge-Aggregation 519)"""
        if re.match('^BAGG\d+',res_port):
            # format port BAGG519 --> Bridge-Aggregation 519
            agg_port_name = res_port.replace('BAGG','Bridge-Aggregation ')
            return agg_port_name
        elif re.match('^Bridge-Aggregation\d*',res_port):
            agg_port_name = res_port
            return agg_port_name
        elif re.match('^XGE\d.*',res_port):
            # format port XGE1/2/0/7 --> Ten-GigabitEthernet 1/2/0/7
            port_name = res_port.replace('XGE','Ten-GigabitEthernet ')
            # print(" --- Port Name: "+'\x1b[1;32;40m' +"{}" .format(port_name)+'\x1b[0m')
            return port_name
        elif re.match('^GE\d.*',res_port):
            # format port GE1/5/0/19 --> GigabitEthernet 1/5/0/19
            port_name = res_port.replace('GE','GigabitEthernet ')
            # print(" --- Port Name: "+'\x1b[1;32;40m' +"{}" .format(port_name)+'\x1b[0m')
            return port_name
        elif re.match('^Vlan\d+',res_port):
            # format port Vlan4003 --> Vlan-interface4003
            port_name = res_port.replace('Vlan','Vlan-interface')
            # print(" --- Port Name: "+'\x1b[1;32;40m' +"{}" .format(port_name)+'\x1b[0m')
            return port_name
        else:
            return res_port 
            # print('\x1b[1;31;40m' + " --- Unknown Port Name: {} --- ".format(res_port)+'\x1b[0m')


    def get_interfaces_ip(self):

        """
        Returns all configured IP addresses on all interfaces as a dictionary of dictionaries.
        Keys of the main dictionary represent the name of the interface.
        Values of the main dictionary represent are dictionaries that may consist of two keys
        'ipv4' and 'ipv6' (one, both or none) which are themselvs dictionaries witht the IP
        addresses as keys.
        Each IP Address dictionary has the following keys:
            * prefix_length (int)

        Example::

            {
                u'FastEthernet8': {
                    u'ipv4': {
                        u'10.66.43.169': {
                            'prefix_length': 22
                        }
                    }
                },
                u'Loopback555': {
                    u'ipv4': {
                        u'192.168.1.1': {
                            'prefix_length': 24
                        }
                    },
                    u'ipv6': {
                        u'1::1': {
                            'prefix_length': 64
                        },
                        u'2001:DB8:1::1': {
                            'prefix_length': 64
                        },
                        u'2::': {
                            'prefix_length': 64
                        },
                        u'FE80::3': {
                            'prefix_length': u'N/A'
                        }
                    }
                },
                u'Tunnel0': {
                    u'ipv4': {
                        u'10.63.100.9': {
                            'prefix_length': 24
                        }
                    }
                }
            }
        """
        # Disable Pageing of the device
        self.disable_pageing()
       
        out_curr_config = self.device.send_command('display current-configuration')
        ipv4table = re.findall(r'^interface\s+([A-Za-z0-9-/]{1,40})\n.*\s+ip\s+address\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\n',out_curr_config,re.M)
        # TODO: get device with v6 and update above struct
        # ipv6table = re.findall(r'',out_curr_config,re.M)
        output_ipv4table = []
        iface = {}
        iface['ipv4'] = {}
        iface['ipv6'] = {}
        for rec in ipv4table:
            interface,ip,mask = rec
            norm_int = self.normalize_port_name(interface)
            iinterfaces = { norm_int : {'ipv4': {ip: { 'prefix_len': mask}}}}
            output_ipv4table.append(iinterfaces)

        return output_ipv4table     


    def get_lldp_neighbors(self):
        """
        Returns a dictionary where the keys are local ports and the value is a list of \
        dictionaries with the following information:
            * hostname
            * port

        Example::

            {
            u'Ethernet2':
                [
                    {
                    'hostname': u'junos-unittest',
                    'port': u'520',
                    }
                ],
            u'Ethernet3':
                [
                    {
                    'hostname': u'junos-unittest',
                    'port': u'522',
                    }
                ],
            u'Ethernet1':
                [
                    {
                    'hostname': u'junos-unittest',
                    'port': u'519',
                    },
                    {
                    'hostname': u'ios-xrv-unittest',
                    'port': u'Gi0/0/0/0',
                    }
                ],
            u'Management1':
                [
                    {
                    'hostname': u'junos-unittest',
                    'port': u'508',
                    }
                ]
            }
        """
        # Disable Pageing of the device
        self.disable_pageing()
       
        out_lldp = self.device.send_command('display lldp neighbor-information')
        lldptable = re.findall(r'^LLDP.*port\s+\d+\[(.*)\]:\s+.*\s+Update\s+time\s+:\s+(.*)\s+\s+.*\s+.*\s+.*\s+Port\s+ID\s+:\s+(.*)\s+Port\s+description\s:.*\s+System\s+name\s+:\s(.*)\n',out_lldp,re.M)
        output_lldptable = {} 
        for rec in lldptable:
            local_port,update_time,remote_port,neighbor = rec
            output_lldptable[local_port] = [{'hostname': neighbor, 'port': remote_port}]
        return output_lldptable     

    def cli(self, commands):
        """
        Will execute a list of commands and return the output in a dictionary format.

        Example::

            {
                u'display clock':  u''' '11:20:16 CET Mon 03/25/2019
                                        Time Zone : CET add 01:00:00'
                                     ''',
                u'display version'     :   u'''.....'''
            }
        """
        cli_output = dict()
        if type(commands) is not list:
            raise TypeError('Please enter a valid list of commands!')
        
        for command in commands:
            output = self._send_command(command)
            if 'Invalid input:' in output:
                raise ValueError(
                    'Unable to execute command "{}"'.format(command))
            cli_output.setdefault(command, {})
            cli_output[command] = output
        return cli_output

    def _send_command(self, command):
        """ Wrapper for self.device.send.command().
        If command is a list will iterate through commands until valid command.
        """
        try:
            if isinstance(command, list):
                for cmd in command:
                    output = self.device.send_command(cmd)
                    if "% Unrecognized" not in output:
                        break
            else:
                output = self.device.send_command(command)
            return output
        except (socket.error, EOFError) as e:
            raise ConnectionClosedException(str(e))


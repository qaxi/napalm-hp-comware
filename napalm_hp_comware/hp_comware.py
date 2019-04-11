"""
Napalm driver for HpComware Devices

Read https://napalm.readthedocs.io for more information.
"""
from netmiko import ConnectHandler, FileTransfer, InLineTransfer
from netmiko import __version__ as netmiko_version

import sys
import re
import logging
from json import dumps

from napalm.base.utils import py23_compat
from napalm.base.base import NetworkDriver
from napalm.base.exceptions import (
    ConnectionException,
    SessionLockedException,
    MergeConfigException,
    ReplaceConfigException,
    CommandErrorException,
    )
from napalm.base.helpers import (
    textfsm_extractor,
)
logger = logging.getLogger(__name__)


class HpComwarePrivilegeError(Exception):
    pass

class HpMacFormatError(Exception):
    pass

class HpNoMacFound(Exception):
    pass

class HpNoActiePortsInAggregation(Exception):
    pass


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
            'global_delay_factor': 3,
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
        out_disable_pageing = self._send_command('screen-length disable')
        if 'configuration is disabled for current user' in out_disable_pageing:
            pass
        else:
            raise ValueError("Disable Pageing cli command error: {}".format(out_disable_pageing))
            sys.exit(" --- Exiting: try to workaround this ---")

    def get_current_privilege(self):
        """ Get and set as property current privilege of the user """
        raw_out = self._send_command('display users', delay_factor=2)
        disp_usr_entries = textfsm_extractor(self, "display_users", raw_out)
        self.current_user_level = disp_usr_entries[0]['user_level']
        return self.current_user_level


    def privilege_escalation(self, os_version=''):
        """ Depends on Comware version 
       
        Permission Levels on Comware v5:  0-VISIT, 1-MONITOR, 2-SYSTEM, 3-MANAGE
        Check userlevel mode with command 'display users'

        <HP-Comware-v5>display users
        The user application information of the user interface(s):
          Idx UI      Delay    Type Userlevel
        + 29  VTY 0   00:00:00 SSH  1                   <----- THIS LEVEL SHOULD BE '3' in
                                                               order to be accessible 
                                                               most of the commands
        
        Following are more details.
        VTY 0   :
                User name: usernameX
                Location: 1xx.xx.xx.53
         +    : Current operation user.
         F    : Current operation user work in async mode.

        
        """
        os_version = os_version
        # check user level mode
        self.get_current_privilege()

        if self.current_user_level == '3': 
            msg = f' Already in user level: {self.current_user_level} ' 
            logger.info(msg); print(msg)
            return 0
        elif self.current_user_level in ['1', '2']: 
            # Escalate user level in order to have all commands available
            if os_version:
                os_version = os_version
            else:
                os_version = self.get_version()['os_version']
            if os_version.startswith('5.'):
                cmd = 'super'
                l1_password = self.device.password
                l2_password = self.device.secret
                self.device.send_command_expect(cmd, expect_string='assword:')
                self.device.send_command_timing(l2_password, strip_command=True)
                # Check and confirm user level mode
                if self.get_current_privilege() == '3': 
                    msg = f' --- Changed to user level: {self.current_user_level} ---' 
                    logger.info(msg); print(msg)
                    return 0
                else:
                    raise HpComwarePrivilegeError
            elif os_version.startswith('7.'):
                # super levles on Comware v5 0-VISIT, 1-MONITOR, 2-SYSTEM, 3-MANAGE
                cmd = 'system-view'
        

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

        self.get_version() returns
            {
             'os_version': '5.20.105',
             'os_version_release': '1808P21',
             'vendor': 'HP',
             'model': 'A5800-24G-SFP',
             'uptime': 14888460
             }
        self.get_interfaces() 
            'interface_list': [u'Ethernet2', u'Management1', u'Ethernet1', u'Ethernet3']
        from 'display device manuinfo'
            'serial_number': u'SN0123A34AS',
            'hostname': u'eos-router',
            'fqdn': u'eos-router',
        """
        self.disable_pageing()
        facts = self.get_version()
        facts['vendor'] = u'Hewlett-Packard'
        facts['interface_list'] = list(self.get_interfaces().keys())
        self.privilege_escalation(os_version=facts['os_version'])

        # get hardware and serial number
        out_display_device = self._send_command("display device manuinfo")
        match = re.findall(r"""^Slot\s+(\d+):\nDEVICE_NAME\s+:\s+(.*)\nDEVICE_SERIAL_NUMBER\s+:\s+(.*)\nMAC_ADDRESS\s+:\s+([0-9a-fA-F]{1,4}-[0-9a-fA-F]{1,4}-[0-9a-fA-F]{1,4})\nMANUFACTURING_DATE\s+:\s+(.*)\nVENDOR_NAME\s+:\s+(.*)""",out_display_device,re.M)
        snumber = set()
        vendor = set()
        hwmodel = set()
        for idx in match:
            slot,dev,sn,mac,date,ven = idx
            snumber.add(sn)
            vendor.add(ven)
            hwmodel.add(dev)
        out_display_current_config = self._send_command("display current-configuration")
        hostname = ''.join(re.findall(r'.*\s+sysname\s+(.*)\n',out_display_current_config,re.M))
        facts["hostname"] = py23_compat.text_type(hostname),
        facts["serial_number"] = py23_compat.text_type(','.join(snumber)),
        facts["model"] = py23_compat.text_type(','.join(hwmodel)),
        facts["fqdn"] = py23_compat.text_type(hostname),
        return facts


    def get_interfaces(self):
        """
        Returns a dictionary of dictionaries. The keys for the first dictionary will be the \
        interfaces in the devices. The inner dictionary will containing the following data for \
        each interface:

         * is_up (True/False)
         * is_enabled (True/False)
         * description (string)
         * last_flapped (float in seconds)
         * speed (int in Mbit)
         * mac_address (string)

        ifaces_entries_br output is list of dictionaries like:
             # The brief information of interface(s) under route mode:
             # Link: ADM - administratively down; Stby - standby
             # Protocol: (s) - spoofing
             #
             # The brief information of interface(s) under bridge mode:
             # Link: ADM - administratively down; Stby - standby
             # Speed or Duplex: (a)/A - auto; H - half; F - full
             # Type: A - access; T - trunk; H - hybrid
             # Interface            Link Speed   Duplex Type PVID Description
             #

	    {
             'interface': 'BAGG5',
             'interface_state': 'UP',           # (UP|DOWN|ADM|Stby)
             'interface_protocol_state': '',    # (UP|DOWN|UP\(s\)|DOWN\(s\))
             'ip_address': '',
             'description': 'la-la-la-sw01',
             'speed': '20G(a)',                 # (\d+|--|\d+G\(a\)|A|auto)
             'duplex': 'F(a)',                  # (A|F|F\(a\))
             'interface_mode': 'T',             # (A|T|H)\
             'pvid': '1'
             },
        """
        raw_out_brief = self._send_command('display interface brief')
        ifaces_entries_br = textfsm_extractor(self, "display_interface_brief", raw_out_brief)
        ifaces = dict()
        for row in ifaces_entries_br:
            for k,v in row.items():
                if k == 'interface':
                    key = self.normalize_port_name(v)
                    is_up = False
                    is_enabled = False
                    speed = str()
                    mac_address = str() 
                    description = str()
                    if row['interface_state'].lower() == 'up':
                        is_up = is_enabled = True
                    else:
                        is_up = is_enabled = False
                    if row['speed'] == '' or row['speed'] in ['auto', 'A']:
                        speed = ''
                    else:
                        m = re.findall(r'(\d+)([G|T|M])', row['speed'])
                        if m[0][1].upper() == 'M':
                            Xbytes = 1
                        elif m[0][1].upper() == 'G':
                            Xbytes = 1000
                        elif m[0][1].upper() == 'T':
                            Xbytes = 100000
                        speed = int(m[0][0]) * Xbytes
                    description = row['description']
                    ifaces[key] = { 
                            'is_up': is_up,
                            'is_enabled': is_enabled,
                            'last_flapped': -1.0,
                            'speed': speed,
                            'mac_address': mac_address,
                            'description': description,
                            'textFSM_display_interface_brief': row
                            }
        # TODO: fill mac_address  ... from 'display interface'
        # raw_out = self._send_command('display interface')
        # ifaces_entries = textfsm_extractor(self, "display_interface", raw_out)
        return ifaces


    def get_mac_address_table(self, raw_mac_table=None):

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
        if raw_mac_table is not None:
            if 'No mac address found' in raw_mac_table:
                return ['No mac address found']
            out_mac_table = raw_mac_table
        else:
            # Disable Pageing of the device
            self.disable_pageing()
        raw_out = self._send_command('display mac-address')
        mac_table_entries = textfsm_extractor(self, "display_mac_address_all", raw_out)
        # owerwrite some values in order to be compliant 
        for row in mac_table_entries:                                            
            row['mac'] = self.format_mac_cisco_way(row['mac'])                   
            row['interface'] = self.normalize_port_name(row['interface'])        
        return mac_table_entries
    
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
        out_arp_table = self._send_command('display arp')
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
       
        out_curr_config = self._send_command('display current-configuration')
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
        out_lldp = self._send_command('display lldp neighbor-information')
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
                    output = self.device.send_command_timing(command)
                    # output = self.device.send_command(cmd)
                    if "% Unrecognized" not in output:
                        break
            else:
                # output = self.device.send_command(command)
                output = self.device.send_command_timing(command)
            return output
        except (socket.error, EOFError) as e:
            raise ConnectionClosedException(str(e))


    def hp_mac_format(self, mac):
        """ return hp mac format """
        if ':' in mac:
            # 04:4b:ed:31:75:cd -> 044bed3175cd
            temp_mac = "".join(mac.split(':'))
        elif '-' in mac:
            # 04-4b-ed-31-75-cd -> 044bed3175cd
            # 044b-ed31-75cd -> 044bed3175cd
            temp_mac = "".join(mac.split('-'))
        else:
            # match '044bed3175cd'
            m = re.match(r'.*([a-f,A-F,0-9]{12})', mac)
            if m:
                temp_mac = mac
            else:
                raise HpMacFormatError(f'Unrecognised Mac format: {mac}')
        out_mac = ''
        for idx, value in enumerate(temp_mac):
            if idx in [4,8]:
                out_mac += '-'
            out_mac += value
        return str(out_mac)


    def get_active_physical_ports(self, aggregation_port):
        """ Return textFSM table with physical ports joined as "aggregation_port" """
        raw_out = self._send_command('display link-aggregation verbose ' + str(aggregation_port))
        port_entries = textfsm_extractor(self, "display_link_aggregation_verbose", raw_out)
        a_ports = list()
        for row in port_entries:
            # Return only active ports
            if row['status'].lower() == 's':
                a_ports.append(self.normalize_port_name(row['port_name']))
        
        if a_ports:
            print(f' --- Active ports of the aggregation_port {aggregation_port} ---')
            print(dumps(a_ports, sort_keys=True, indent=4, separators=(',', ': ')))
            return a_ports
        else:
            raise HpNoActiePortsInAggregation


    def trace_mac_address(self, mac_address):
        """ Search for mac_address, get switch port and return lldp/cdp
        neighbour of that port """
        result = { 
                'found': False,
                'cdp_answer': False,
                'lldp_answer': False,
                'local_port': '',
                'remote_port': '',
                'next_device': '',
                'next_device_descr': '',
                }
        try:
            mac_address = self.hp_mac_format(mac_address)
            raw_out = self._send_command('display mac-address ' + mac_address)
            if 'No mac address found' in raw_out:
                raise HpNoMacFound
            else:
                result['found'] = True
            msg = f' --- Found {mac_address} mac address --- \n'
            mac_table = textfsm_extractor(self, "display_mac_address", raw_out)
            print(msg); logger.info(msg)
            print(dumps(mac_table, sort_keys=True, indent=4, separators=(',', ': ')))
            for row in mac_table:
                for k,pname in row.items():
                    if k == 'interface' and pname != None:
                        # send lldp neighbour command
                        if ('BAGG' in pname) or ('Bridge-Aggregation' in pname):
                            # Check and format the interface name
                            agg_port_name = self.normalize_port_name(pname)
                            # get first physical port of the aggregated port
                            result['local_port'] = agg_port_name
                            physical_port = self.get_active_physical_ports(agg_port_name)[0]
                            lldp_neighbours = self.get_lldp_neighbors_detail(interface=physical_port)
                            cdp_neighbours = self.get_cdp_neighbors_detail(interface=physical_port)
                            if lldp_neighbours:
                                result['lldp_answer'] = True
                                result['remote_port'] = lldp_neighbours[0]["remote_port"]
                                result['next_device'] = lldp_neighbours[0]["remote_system_name"]
                                result['next_device_descr'] = lldp_neighbours[0]['remote_system_description']
                                msg = f' --- LLDP Neighbour System Name: {result["next_device"]}'
                            elif cdp_neighbours:
                                result['cdp_answer'] = True
                                result['remote_port'] = cdp_neighbours[0]["remote_port"]
                                result['next_device'] = cdp_neighbours[0]["remote_system_name"]
                                result['next_device_descr'] = cdp_neighbours[0]['remote_system_description']
                                msg = f' --- CDP Neighbour System Name: {result["next_device"]}'
                            print(msg); logger.info(msg)
                            return result
                        elif ('XGE' in pname) or ('GE' in pname):
                            pname = self.normalize_port_name(pname)
                            result['local_port'] = pname
                            from IPython import embed; embed()
                            from IPython.core import debugger; debug = debugger.Pdb().set_trace; debug()
                            lldp_neighbours = self.get_lldp_neighbors_detail(interface=pname)
                            cdp_neighbours = self.get_cdp_neighbors_detail(interface=pname)
                            if lldp_neighbours:
                                result['lldp_answer'] = True
                                result['remote_port'] = lldp_neighbours[0]["remote_port"]
                                result['next_device'] = lldp_neighbours[0]["remote_system_name"]
                                msg = f' --- LLDP Neighbour System Name: {result["next_device"]}'
                            elif cdp_neighbours:
                                result['cdp_answer'] = True
                                result['remote_port'] = cdp_neighbours[0]["remote_port"]
                                result['next_device'] = cdp_neighbours[0]["remote_system_name"]
                                msg = f' --- CDP Neighbour System Name: {result["next_device"]}'
                            print(msg); logger.info(msg)
                            return result
                        else:
                            raise NotImplementedError
        except HpMacFormatError as e:
            msg = f'Unrecognised Mac format: {mac_address}'
            logger.error(msg)
            print(msg)
            return result
        except HpNoMacFound as e:
            msg = f' --- No mac address {mac_address} found: {e} ---'
            print(msg)
            logger.info(msg)
            return result
        except Exception as e:
            raise e


    def get_version(self):
        """ Return Comware version, vendor, model and uptime. 
        Use it as part of get_facts
        {
         'os_version': '5.20.105',
         'os_version_release': '1808P21',
         'vendor': 'HP',
         'model': 'A5800-24G-SFP',
         'uptime': 14888460
         }
        """
        raw_out = self._send_command('display version')
        # get only first row of text FSM table
        version_entries = textfsm_extractor(self, "display_version", raw_out)[0]
        # convert uptime from '24 weeks, 4 days, 7 hours, 41 minutes to seconds
        uptime_str = version_entries['uptime']
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
        version_entries['uptime'] = uptime
        return version_entries


    def get_lldp_neighbors_detail(self, interface=""):
        """ lldp cli commands depends on comware version
        return diction format 
        { [
            'local_interface'    :'',
            'local_interface_idx'    :'',
            'remote_chassis_id'    :'',
            'remote_port'    :'',
            'remote_port_description'    :'',
            'remote_system_name'    :'',
            'remote_system_description'    :'',
            'remote_system_capab'    :'',
            'remote_system_enable_capab'    :'',
            ]
        }
        """
        version_dict = self.get_version()

        if interface:
            if version_dict['os_version'].startswith('5.'):
                command = 'display lldp neighbor-information interface ' + str(interface)
            elif version_dict['os_version'].startswith('7.'):
                command = 'display lldp neighbor-information interface ' + str(interface)+' verbose'
        else:
            # display all lldp neigh interfaces command
            command = "display lldp neighbor-information "
        raw_out = self._send_command(command)
        lldp_entries = textfsm_extractor(
                self, "display_lldp_neighbor_information_interface", raw_out )
        if len(lldp_entries) == 0:
            return {}
        return lldp_entries


    def get_cdp_neighbors_detail(self, interface=""):
        """ cdp cli commands depends on comware version
        return diction format 
        { [
            'local_interface'    :'',
            'local_interface_idx'    :'',
            'remote_chassis_id'    :'',
            'remote_port'    :'',
            'remote_port_description'    :'',
            'remote_system_name'    :'',
            'remote_system_description'    :'',
            'remote_system_capab'    :'',
            'remote_system_enable_capab'    :'',
            ]
        }
        """
        # TODO  not implemented 
        return False


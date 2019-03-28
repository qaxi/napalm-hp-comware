# 
# Parse 'display lldp neighbor-information interface INTERFACE'
# or 'display lldp neighbor-information'
#
#LLDP neighbor-information of port 284[GigabitEthernet4/0/17]:
#  Neighbor index   : 1
#  Update time      : 0 days,0 hours,18 minutes,2 seconds
#  Chassis type     : MAC address
#  Chassis ID       : e007-1b62-XXXX
#  Port ID type     : Locally assigned
#  Port ID          : 97
#  Port description : 2/45
#  System name        : remote_system_name
#  System description : HP J9728A 2920-48G Switch, revision WB.15.15.0012, ROM WB.15.05 (/ws/swbuildm/rel_nashville_qaoff/code/build/anm(swbuildm_rel_nashville_qaoff_rel_nashville))
#  System capabilities supported : Bridge,Router
#  System capabilities enabled   : Bridge
#
#  Management address type           : ipv4
#  Management address                : 10.17.4.7
#  Management address interface type : IfIndex
#  Management address interface ID   : Unknown
#  Management address OID            : 0
#
#  Port VLAN ID(PVID): 1
#
#  Auto-negotiation supported : Yes
#  Auto-negotiation enabled   : Yes
#  OperMau                    : speed(1000)/duplex(Full)
#
#  Power port class          : PSE
#  PSE power supported       : No
#  PSE power enabled         : No
#  PSE pairs control ability : No
#  Power pairs               : Signal
#  Port power classification : Class 0
Value LOCAL_INTERFACE (.*)
Value LOCAL_INTERFACE_IDX (\d+)
Value REMOTE_CHASSIS_ID (.*)
Value REMOTE_PORT (.*)
Value REMOTE_PORT_DESCRIPTION (.+)
Value REMOTE_SYSTEM_NAME (.*)
Value REMOTE_SYSTEM_DESCRIPTION (.+)
Value REMOTE_SYSTEM_CAPAB (.*)
Value REMOTE_SYSTEM_ENABLE_CAPAB (.*)

Start
  ^LLDP neighbor-information of port ${LOCAL_INTERFACE_IDX}\[${LOCAL_INTERFACE}\]
  ^\s+Chassis ID\s*?[:-]\s+${REMOTE_CHASSIS_ID}
  ^\s+Port ID\s*?[:-]\s+${REMOTE_PORT}
  ^\s+Port description\s*?[:-]\s+${REMOTE_PORT_DESCRIPTION}
  ^\s+System name\s*?[:-]\s+${REMOTE_SYSTEM_NAME}
  ^\s+System description\s*[:-]\s*${REMOTE_SYSTEM_DESCRIPTION}
  ^\s+System capabilities supported\s*?[:-]\s+${REMOTE_SYSTEM_CAPAB}
  ^\s+System capabilities enabled\s*?[:-]\s+${REMOTE_SYSTEM_ENABLE_CAPAB} -> Record

EOF

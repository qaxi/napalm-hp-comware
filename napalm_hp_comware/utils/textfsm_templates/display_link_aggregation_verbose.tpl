#
# Parse display link-aggregation verbose portname 
#
# Loadsharing Type: Shar -- Loadsharing, NonS -- Non-Loadsharing
# Port Status: S -- Selected, U -- Unselected
# Flags:  A -- LACP_Activity, B -- LACP_Timeout, C -- Aggregation,
#         D -- Synchronization, E -- Collecting, F -- Distributing,
#         G -- Defaulted, H -- Expired
#
# Aggregation Interface: Bridge-Aggregation63
# Aggregation Mode: Dynamic
# Loadsharing Type: Shar
# System ID: 0x8000, d07e-28cf-XXXX
# Local:
#   Port             Status  Priority Oper-Key  Flag
# --------------------------------------------------------------------------------
#   GE4/0/17         S       32768    40        {ACDEF}
#   GE3/0/17         S       32768    40        {ACDEF}
# Remote:
#   Actor            Partner Priority Oper-Key  SystemID               Flag
# --------------------------------------------------------------------------------
#   GE4/0/17         97      0        210       0xf20b, e007-1b62-xxxx {ACDEF}
#   GE3/0/17         45      0        210       0xf20b, e007-1b62-xxxx {ACDEF}
Value Filldown PORT_NAME (\S+)
Value Filldown STATUS (\S+)
Value Filldown PRIORITY (\d+)
Value OPER_KEY (\S+)
Value FLAG (\S+)

Start
  ^Local\:
  ^\s+Port\s+Status\s+Priority\s+Oper-Key\s+Flag
  ^-------------------------------------------------------------------------------- -> LOCAL_PORTS

LOCAL_PORTS
  ^\s+${PORT_NAME}\s+${STATUS}\s+${PRIORITY}\s+${OPER_KEY}\s+${FLAG} -> Record
  ^Remote\: -> EOF

EOF

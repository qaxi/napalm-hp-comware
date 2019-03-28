# 
# Parse comware display version
# 
# HP Comware Platform Software
# Comware Software, Version 5.20.105, Release 1808P21
# Copyright (c) 2010-2014 Hewlett-Packard Development Company, L.P.
# HP A5800-24G-SFP Switch with 1 Interface Slot uptime is 24 weeks, 4 days, 7 hours, 19 minutes
# 
# HP A5800-24G-SFP Switch with 1 Interface Slot with 2 Processors
# 1024M   bytes SDRAM
# 4M      bytes Nor Flash Memory
# 512M    bytes Nand Flash Memory
# Config Register points to Nand Flash
# 
# Hardware Version is Ver.B
# CPLDA Version is 003, CPLDB Version is 003
# BootRom Version is 220
# [SubSlot 0] 24SFP+4SFP Plus Hardware Version is Ver.B
# [SubSlot 1] 16SFP Hardware Version is Ver.A
Value OS_VERSION (\S+)
Value OS_VERSION_RELEASE (\S+)
Value VENDOR (HP|hp)
Value MODEL (\S+)
Value UPTIME (.*$)

Start
  ^Comware\s+Software,\s+Version\s+${OS_VERSION},\s+Release\s+${OS_VERSION_RELEASE}
  ^${VENDOR}\s+${MODEL}\s+Switch\s+\S+\s+\S+\s+\S+\s+\S+\s+uptime\s+is\s+${UPTIME} -> Record

EOF

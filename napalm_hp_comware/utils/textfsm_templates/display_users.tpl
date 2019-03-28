# 
# HP Comware v5.x 'display users' 
#
# The user application information of the user interface(s):   
#   Idx UI      Delay    Type Userlevel                        
# + 29  VTY 0   00:00:00 SSH  1                                
#                                                              
# Following are more details.                                  
# VTY 0   :                                                    
#         User name: userY
#         Location: 1yy.yy.yy.yy
#  +    : Current operation user.                              
#  F    : Current operation user work in async mode.           
#
Value INDEX (\S+)
Value UI (\S+\s+\S+)
Value DELAY (\S+)
Value TYPE (\S+)
Value USER_LEVEL (\d+)
Value USER_NAME (\S+)

Start
  ^\s+Idx\s+UI\s+Delay\s+Type\s+Userlevel
  ^\S+\s+${INDEX}\s+${UI}\s+${DELAY}\s+${TYPE}\s+${USER_LEVEL}
  ^\s+User\s+name\:\s+${USER_NAME} -> Record

EOF

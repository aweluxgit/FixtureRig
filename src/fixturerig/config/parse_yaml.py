#
# This module contains the code that parses the yaml files into the configuration model
#
# 
# Example config:
# --- 
# - fixture: 
#     name: "Can" 
#     class: ... 
# - testcase: 
#     name: "sometest" 
#     class: .... 
#     parametermap: 
#       volt: 4.5 
#       limit: 6.0 
# - testgroup: 
#   - testcase: 
#       name: "foo" 
#       class: .... 
#       parameterlist: 
#         - param: {name: "...", value: 4} 
#         - param: {name: "...", value: 4, type= "fstring"}
#         - path: {name: "somepath", path = ..., relto = ..., basepath = ... } 
#       parameterpath: 
#         somepath: {path = ..., relto = ... } 
# --- 
# - parametermap: 
#     some 


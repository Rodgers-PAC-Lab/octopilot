#!/bin/bash
# Argument number 1 is the task name, which should correspond to a json
# in config/task/*.json
source ~/.venv/octopilot/bin/activate 
python3 -m octopilot.pi.start_cli $1

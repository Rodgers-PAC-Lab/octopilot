## Main script that runs on each Pi to run behavior
# The flow is:
# - PiMarshaller on the desktop starts an SSH process
# - start_cli.sh in this directory is started in that SSH process
# - start_cli.sh activates the conda environment and then runs this script

import os
import argparse
from . import daemons
from ..shared import load_params
from . import agent


## TODO: use argparse to get the `agent_name` here, so it doesn't have to 
## come from a config file
parser = argparse.ArgumentParser(
    description="""
    Start octopilot on the Pi. 
    Generally this is called by an SSH process, not directly by the user.
    """)

# Add each argument
parser.add_argument(
    'task', 
    nargs='?',
    type=str, 
    help=(
        """The name of the task to run. 
        There must be a matching json in configs/task/*.json
        """
        ),
    )

# Parse the args
args = parser.parse_args()


## Loading parameters of this Pi
params = load_params.load_pi_params()

# Load params of the corresponding box, to get the desktop IP and port
box_params = load_params.load_box_params(params['box'])
params['gui_ip'] = box_params['desktop_ip']
params['zmq_port'] = box_params['zmq_port']

# Same for bonsai IP and port
# TODO: add a default here if these aren't set
params['bonsai_ip'] = box_params['bonsai_ip']
params['bonsai_port'] = box_params['bonsai_port']

# Load the json for the task specified on the command line
task_params = load_params.load_task_params(args.task)

# Get the agent name from the task params
params['agent_name'] = task_params['agent_name']


## Handle daemons
# Kill any pre-existing pigpiod and jackd
daemons.kill_pigpiod(verbose=True)
daemons.kill_jackd(verbose=True)

# Start pigpiod and jackd
daemons.start_pigpiod(verbose=True)
jackd_proc = daemons.start_jackd(verbose=True)


## Start the main loop
# TODO: if there is an error in agent.Agent.__init__, this script will hang
# after printing "jackd successfully killed"
try:
    # Choose the proper agent based on the task
    # Use 'agent_name' to get the correct object from the agent module
    try:
        agent_obj = agent.__dict__[params['agent_name']]
    except KeyError:
        raise ValueError(f"unrecognized agent_name: {params['agent_name']}")
    
    # log
    print(f"starting an agent named {params['agent_name']}: {agent_obj}")
    print(f"using params: {params}")
    
    # Instantiate
    hc = agent_obj(params=params, start_networking=True)
    
    # Start the agent
    hc.main_loop()

except:
    raise

finally:
    ## Terminate daemons
    # TODO: move this to HardwareController? Should it be in charge of its own
    # daemons?

    # A good test is to comment out the rest of this script, which is essentially
    # what happens if the script fails
    # It should still be able to run next time
    # Or try killing pigpiod or jackd outside of this process

    # Terminate pigpiod
    daemons.kill_pigpiod(verbose=True)

    # Terminate jackd
    jackd_proc.terminate()

    # Pull out stdout and stderr
    stdout, stderr = jackd_proc.communicate()

    if jackd_proc.returncode == 0:
        print('jackd successfully killed')
    else:
        print('could not kill jackd; dump follows:')
        print(f'returncode: {jackd_proc.returncode}')
        print(f'stdout: {stdout}')
        print(f'stderr: {stderr}')
        
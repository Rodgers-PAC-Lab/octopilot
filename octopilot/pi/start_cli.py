## Main script that runs on each Pi to run behavior

import os
from . import daemons
from ..shared import load_params
from . import agent


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

# Get the agent name, which right now is fixed per box (because we have to
# start the agent before we can talk to the Dispatcher)
# TODO: need some way to allow multiple agent_name per box, eg to allow
# different tasks per box
params['agent_name'] = box_params['agent_name']


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
    # TODO: use the string to find the object
    if params['agent_name'] == 'WheelTask':
        hc = agent.WheelTask(params=params, start_networking=True)
    elif params['agent_name'] == 'SoundSeekingAgent':
        hc = agent.SoundSeekingAgent(params=params, start_networking=True)
    else:
        raise ValueError(f"unrecognized agent_name: {params['agent_name']}")
    
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
        
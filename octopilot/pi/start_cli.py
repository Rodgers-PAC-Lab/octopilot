## Main script that runs on each Pi to run behavior

import os
from . import daemons
from ..shared import load_params
from . import agent


## Loading parameters of this Pi
params = load_params.load_pi_params()

# Load params of the corresponding box, to get the desktop IP
box_params = load_params.load_box_params(params['box'])
params['gui_ip'] = box_params['desktop_ip']
params['zmq_port'] = box_params['zmq_port']


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
    hc = agent.Agent(params=params, start_networking=True)
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
        
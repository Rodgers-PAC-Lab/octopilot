## Main script that runs on each Pi to run behavior

import os
from . import daemons
from ..shared import load_params
from . import agent


## LOADING PARAMETERS FOR THE PI 
params = load_params.load_pi_params(verbose=False)
pins = load_params.load_pins(verbose=False)


## Handle daemons
# Kill any pre-existing pigpiod and jackd
daemons.kill_pigpiod(verbose=True)
daemons.kill_jackd(verbose=True)

# Start pigpiod and jackd
daemons.start_pigpiod(verbose=True)
jackd_proc = daemons.start_jackd(verbose=True)


## Start the main loop
try:
    hc = agent.Agent(pins=pins, params=params, start_networking=True)
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
        
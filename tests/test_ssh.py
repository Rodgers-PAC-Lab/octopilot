# Test ability to start a long-running ssh process on the rpi
#
# If the process completes (either successfully or with error):
#   We want to know that, and be able to capture its entire output
# If we terminate the process
#   We want to be able to end it remotely (from here)
# If this python script dies
#   We want the process to end too
#
# Test cases
# * Run this script as-is: 
#    returncode 0
#    stderr contains "Connection to 192.168.0.101 closed."
# * Run this script as-is, but introduce an error into remote script: 
#    returncode 1
#    the Exception is printed on stdout
#    the process immediately closes on the remote end
#    stderr contains "Connection to 192.168.0.101 closed."
# * Run this script as-is, and kill the process remotely
#   Note that you must kill the remote process beginning with python3, not bash
#    returncode 143 (with kill)
#    returncode 137 (with kill -9)
#    stderr contains "Connection to 192.168.0.101 closed."
# * Run this script as-is, and hit CTRL+C locally
#    this script responds to CTRL+C, proc will have returncode 0, threads
#    will not be alive
#    nothing on stderr
# * Run this script with the code block "test proc.terminate" uncommented
#    returncode 0 with proc.terminate, -9 with proc.kill
#    nothing on stderr
#
# In no case should the process continue on the remote end after this script
# has finished, whether successfully or in error.
# In all cases, the output should appear on stdout in real time.
#
# This will get the pid of the remote: ps aux | grep test_ssh_pi | grep python3

import subprocess
import threading
import time

# Open proc
# It will begin immediately
# -tt is necessary to be able to read from stdout and stderr interactively
# -tt is also necessary to have the process end if the proc is closed by CTRL+C 
#    (and maybe if it's killed in other ways, not sure)
# "bash -i shell_script.sh" is necessary to have it be able to find the
#    Python module, for some reason (setting "env" doesn't work, probably
#    it's inside some kind of virtualenv)
#    The shell script should just call python3 python_script.py
print('Beginning process...')
proc = subprocess.Popen(
    ['ssh', '-tt', 'pi@192.168.0.101', 'bash', '-i', '/home/pi/dev/paclab_sukrith/tests/test_ssh_pi.sh'], 
    stdin=subprocess.PIPE, 
    stdout=subprocess.PIPE, 
    stderr=subprocess.PIPE, 
    text=True, 
    universal_newlines=True,
    )

# Define functions to capture the output in threads
stdout_l = []
def capture_stdout():
    # Iterate through the lines of stdout until the sentinel value of ''
    # is returned
    for line in iter(proc.stdout.readline, ''):
        print('stdout: ' + line.strip())
        stdout_l.append(line.strip())

stderr_l = []
def capture_stderr():
    # Iterate through the lines of stderr until the sentinel value of ''
    # is returned
    for line in iter(proc.stderr.readline, ''):
        print('stderr: ' + line.strip())
        stderr_l.append(line.strip())

# Start the thread to capture the stdout
thread_stdout = threading.Thread(target=capture_stdout)
thread_stdout.start()

# Start the thread to capture the stderr
thread_stderr = threading.Thread(target=capture_stderr)
thread_stderr.start()

# This is where long-running stuff would go
while True:
    proc.poll()
    if proc.returncode is not None:
        print(f'proc has returned with returncode {proc.returncode}')
        break
    
    #~ # Test proc.terminate
    #~ if len(stdout_l) > 4:
        #~ proc.terminate()
    
    time.sleep(.3)

# Once the proc has returned, the threads should be done
assert not thread_stdout.is_alive()
assert not thread_stderr.is_alive()

# Join the threads - this waits until they have completed - this doesn't 
# seem necessary
#~ print('joining stdout thread')
#~ thread_stdout.join()
#~ print('joining stderr thread')
#~ thread_stderr.join()


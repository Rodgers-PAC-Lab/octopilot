# Test ability to start a long-running ssh process on the rpi

import subprocess


# Open proc
proc = subprocess.Popen(
    ['ssh', '-tt', 'pi@192.168.0.101', 'bash', '-i', '/home/pi/dev/paclab_sukrith/tests/test_ssh_pi.sh'], 
    stdin=subprocess.PIPE, 
    stdout=subprocess.PIPE, 
    stderr=subprocess.PIPE, 
    text=True, 
    universal_newlines=True,
    )

print(proc.communicate())
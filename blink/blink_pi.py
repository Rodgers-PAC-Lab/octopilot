import zmq
import pigpio
import time
import os

## Killing previous pigpiod and jackd background processes
os.system('sudo killall pigpiod')
# Wait long enough to make sure they are killed
time.sleep(1)

## Starting pigpiod and jackd background processes
# Start pigpiod
os.system('sudo pigpiod -t 0 -l -x 1111110000111111111111110000')
time.sleep(1)

def flash():
    pi.set_mode(22, pigpio.OUTPUT)
    pi.write(22, 1)
    pi.set_mode(11, pigpio.OUTPUT)
    pi.write(11, 1)
    time.sleep(0.25)
    pi.write(22, 0)
    pi.write(11, 0)

# Setting up ZMQ context to send and receive information about poked ports
context = zmq.Context()
sub = context.socket(zmq.SUB)
sub.connect("tcp://192.168.0.213:5562")  # Change Port number if you want to run multiple instances
sub.subscribe(b"")  # Subscribe to all topics
print("Starting...")

# Create a poller object to handle the socket
poller = zmq.Poller()
poller.register(sub, zmq.POLLIN)

# Initialize pigpio
pi = pigpio.pi()

# Main loop to receive messages
try:
    while True:
        # Poll for incoming messages with a timeout of 100ms
        socks = dict(poller.poll(100))

        if sub in socks and socks[sub] == zmq.POLLIN:
            msg = sub.recv_string()
            msg_str = msg.decode('utf-8')
            
            if msg_str == 'blink':
                print("Received 'blink' message")
                flash()
            
            elif msg_str == 'waiting':
                print("Waiting for 'blink' message")
                pass

except KeyboardInterrupt:
    print("sub script interrupted by user")

finally:
    sub.close()
    context.term()   
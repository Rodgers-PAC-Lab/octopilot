import zmq
import pigpio
import time

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
receiver = context.socket(zmq.SUB)
receiver.connect("tcp://192.168.0.213:5557")  # Change Port number if you want to run multiple instances

# Create a poller object to handle the socket
poller = zmq.Poller()
poller.register(receiver, zmq.POLLIN)

# Initialize pigpio
pi = pigpio.pi()

# Main loop to receive messages
try:
    while True:
        # Poll for incoming messages with a timeout of 100ms
        socks = dict(poller.poll(100))

        if receiver in socks and socks[receiver] == zmq.POLLIN:
            msg = receiver.recv_string()
            
            if msg.startswith("blink"):
                flash()
            
            else:
                pass

except KeyboardInterrupt:
    print("Receiver script interrupted by user")

finally:
    receiver.close()
    context.term()   
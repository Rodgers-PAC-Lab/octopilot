import zmq
import pigpio
import numpy as np
import os
import jack
import time
import threading

# Killing previous pigpiod and jackd background processes
os.system('sudo killall pigpiod')
os.system('sudo killall jackd')
time.sleep(1)

# Starting pigpiod and jackd background processes
os.system('sudo pigpiod -t 0 -l -x 1111110000111111111111110000')
time.sleep(1)
os.system('jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -r192000 -n3 -s &')
time.sleep(1)

class JackClient:
    def __init__(self, name='jack_client', outchannels=None):
        self.name = name
        self.set_channel = 'none'  # 'left', 'right', or 'none'
        self.lock = threading.Lock()  # Lock for thread-safe set_channel() updates
        self.chunk_duration = 0.01  # Duration of each chunk in seconds
        self.pause_duration = 0.1  # Pause duration between chunk in seconds
        self.amplitude = 0.01
        self.last_chunk_time = time.time()  # Variable to store the time of the last burst

        # Creating a jack client
        self.client = jack.Client(self.name)

        # Pull these values from the initialized client
        # These come from the jackd daemon
        self.blocksize = self.client.blocksize
        self.fs = self.client.samplerate
        print("Received blocksize {} and fs {}".format(self.blocksize, self.fs))

        # Set the number of output channels
        if outchannels is None:
            self.outchannels = [0, 1]
        else:
            self.outchannels = outchannels

        # Set mono_output
        if len(self.outchannels) == 1:
            self.mono_output = True
        else:
            self.mono_output = False

        # Register outports
        if self.mono_output:
            # One single outport
            self.client.outports.register('out_0')
        else:
            # One outport per provided outchannel
            for n in range(len(self.outchannels)):
                self.client.outports.register('out_{}'.format(n))

        # Process callback to self.process
        self.client.set_process_callback(self.process)

        # Activate the client
        self.client.activate()

        ## Hook up the outports (data sinks) to physical ports
        # Get the actual physical ports that can play sound
        target_ports = self.client.get_ports(
            is_physical=True, is_input=True, is_audio=True)

        # Depends on whether we're in mono mode
        if self.mono_output:
            ## Mono mode
            # Hook up one outport to all channels
            for target_port in target_ports:
                self.client.outports[0].connect(target_port)
        
        else:
            ## Not mono mode
            # Error check
            if len(self.outchannels) > len(target_ports):
                raise ValueError(
                    "Cannot connect {} ports, only {} available".format(
                    len(self.outchannels),
                    len(target_ports),))
            
            # Hook up one outport to each channel
            for n in range(len(self.outchannels)):
                # This is the channel number the user provided in OUTCHANNELS
                index_of_physical_channel = self.outchannels[n]
                
                # This is the corresponding physical channel
                # I think this will always be the same as index_of_physical_channel
                physical_channel = target_ports[index_of_physical_channel]
                
                # Connect virtual outport to physical channel
                self.client.outports[n].connect(physical_channel)

    # Process callback function (used to play sound)
    def process(self, frames):
        with self.lock: # Making process() thread-safe
            current_time = time.time()

            # Initialize data with zeros (silence)
            data = np.zeros((self.blocksize, 2), dtype='float32')

            # Check if time for chunk or gap
            if current_time - self.last_chunk_time >= self.chunk_duration + self.pause_duration:
                self.last_chunk_time = current_time  # Updating the last chunk time
            elif current_time - self.last_chunk_time >= self.chunk_duration:
                pass  # Silence is playing
            else:
                # Generate random noise for the chunks
                if self.set_channel == 'left': # Play sound from left channel
                    data = self.amplitude * np.random.uniform(-1, 1, (self.blocksize, 2)) # Random noise using numpy
                    data[:, 1] = 0  # Blocking out the right channel 
                elif self.set_channel == 'right':
                    data = self.amplitude * np.random.uniform(-1, 1, (self.blocksize, 2))
                    data[:, 0] = 0  # Blocking out the left channel

        # Write
        self.write_to_outports(data)

    def write_to_outports(self, data):
        if data.ndim == 1:
            ## 1-dimensional sound provided
            # Write the same data to each channel
            for outport in self.client.outports:
                buff = outport.get_array()
                buff[:] = data

        elif data.ndim == 2:
            # Error check
            # Making sure the number of channels in data matches the number of outports
            if data.shape[1] != len(self.client.outports):
                raise ValueError(
                    "data has {} channels "
                    "but only {} outports in pref OUTCHANNELS".format(
                    data.shape[1], len(self.client.outports)))

            # Write one column to each channel
            for n_outport, outport in enumerate(self.client.outports):
                buff = outport.get_array()
                buff[:] = data[:, n_outport]

        else:
            raise ValueError("data must be 1D or 2D") 

    # Function to set which channel to play sound from
    def set_set_channel(self, mode):
        with self.lock:
            self.set_channel = mode

    def run(self):
        # Placeholder for any additional setup if needed
        pass

# Define a client to play sounds
jack_client = JackClient(name='jack_client')
jack_client_thread = threading.Thread(target=jack_client.run) # Creating a thread for the jack client
jack_client_thread.start() # Starting the thread

# Raspberry Pi's identity (Change this to the identity of the Raspberry Pi you are using)
pi_identity = b"rpi27"

# Creating a ZeroMQ context and socket for communication with the central system
context = zmq.Context()
socket = context.socket(zmq.DEALER)
socket.identity = pi_identity # Setting the identity of the socket

# Connect to the server
router_ip = "tcp://192.168.0.207:5555" # Connecting to Laptop IP address (192.168.0.99 for laptop, 192.168.0.207 for seaturtle)
socket.connect(router_ip) 
socket.send_string("rpi22") # Send the identity of the Raspberry Pi to the server
print(f"Connected to router at {router_ip}")  # Print acknowledgment

# Pigpio configuration
a_state = 0
count = 0
nosepoke_pinL = 8
nosepoke_pinR = 15

# Global variables for which nospoke was detected
left_poke_detected = False
right_poke_detected = False

# Callback function for nosepoke pin (When the nosepoke is completed)
# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inL(pin, level, tick):
    global a_state, left_poke_detected
    a_state = 0
    if left_poke_detected:
        # Write to left pin
        print("Left poke detected!")
        pi.set_mode(17, pigpio.OUTPUT)
        pi.write(17, 0)

    # Reset poke detected flags
    left_poke_detected = False

# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inR(pin, level, tick):
    global a_state, right_poke_detected
    a_state = 0
    if right_poke_detected:
        # Write to left pin
        print("Right poke detected!")
        pi.set_mode(10, pigpio.OUTPUT)
        pi.write(10, 1)

    # Reset poke detected flags
    right_poke_detected = False

# Callback functions for nosepoke pin (When the nosepoke is detected)
def poke_detectedL(pin, level, tick): 
    global a_state, count, left_poke_detected
    a_state = 1
    count += 1
    left_poke_detected = True
    # Your existing poke_detectedL code here
    print("Poke Completed (Left)")
    print("Poke Count:", count)
    nosepoke_idL = 1  # Set the left nosepoke_id here according to the pi
    pi.set_mode(17, pigpio.OUTPUT)
    pi.write(17, 1)
    try:
        print(f"Sending nosepoke_id = {nosepoke_idL} to the Laptop") 
        socket.send_string(str(nosepoke_idL))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

def poke_detectedR(pin, level, tick): 
    global a_state, count, right_poke_detected
    a_state = 1
    count += 1
    right_poke_detected = True
    # Your existing poke_detectedR code here
    print("Poke Completed (Right)")
    print("Poke Count:", count)
    nosepoke_idR = 3  # Set the right nosepoke_id here according to the pi
    pi.set_mode(10, pigpio.OUTPUT)
    pi.write(10, 0)
    # Sending nosepoke_id wirelessly
    try:
        print(f"Sending nosepoke_id = {nosepoke_idR} to the Laptop") 
        socket.send_string(str(nosepoke_idR))
    except Exception as e:
        print("Error sending nosepoke_id:", e)

# Set up pigpio and callbacks
pi = pigpio.pi()
pi.callback(nosepoke_pinL, pigpio.FALLING_EDGE, poke_inL)
pi.callback(nosepoke_pinL, pigpio.RISING_EDGE, poke_detectedL)
pi.callback(nosepoke_pinR, pigpio.FALLING_EDGE, poke_inR)
pi.callback(nosepoke_pinR, pigpio.RISING_EDGE, poke_detectedR)

# Main loop to keep the program running and exit when it receives an exit command
try:
    # Initialize reward_pin variable
    reward_pin = None
    current_pin = None  # Track the currently active LED
    
    while True:
        
        # Check for incoming messages
        try:
            msg = socket.recv_string()
            if msg == 'exit': # Condition to terminate the main loop
                pi.write(17, 0)
                pi.write(10, 0)
                pi.write(27, 0)
                pi.write(9, 0)
                print("Received exit command. Terminating program.")
                break  # Exit the loop
            
            elif msg.startswith("Reward Port:"):
                print(msg)
                # Extract the integer part from the message
                msg_parts = msg.split()
                if len(msg_parts) != 3 or not msg_parts[2].isdigit():
                    print("Invalid message format.")
                    continue
                
                value = int(msg_parts[2])  # Extract the integer part
                
                # Reset the previously active LED if any
                if current_pin is not None:
                    pi.write(current_pin, 0)
                
                # Manipulate pin values based on the integer value
                if value == 1:
                    reward_pin = 27  # Example pin for case 1 (Change this to the actual)
                    pi.set_mode(reward_pin, pigpio.OUTPUT)
                    pi.set_PWM_frequency(reward_pin, 1)
                    pi.set_PWM_dutycycle(reward_pin, 50)
                    # Playing sound from the left speaker
                    jack_client.set_set_channel('left')
                    print("Turning Nosepoke 5 Green")

                    current_pin = reward_pin

                elif value == 3:
                    reward_pin = 9  # Example pin for case 2
                    pi.set_mode(reward_pin, pigpio.OUTPUT)
                    pi.set_PWM_frequency(reward_pin, 1)
                    pi.set_PWM_dutycycle(reward_pin, 50)
                    # Playing sound from the right speaker
                    jack_client.set_set_channel('right')
                    print("Turning Nosepoke 7 Green")

                    current_pin = reward_pin

                else:
                    print(f"Current Reward Port: {value}") # Current Reward Port
            
            elif msg == "Reward Poke Completed":
                # Turn off the currently active LED
                if current_pin is not None:
                    pi.write(current_pin, 0)
                    print("Turning off currently active LED.")
                    current_pin = None  # Reset the current LED
                else:
                    print("No LED is currently active.")
                # Reset play mode to 'none'
                jack_client.set_set_channel('none')
            else:
                print("Unknown message received:", msg)

        except zmq.Again:
            pass  # No messages received
        
except KeyboardInterrupt:
    pi.stop()
finally:
    socket.close()
    context.term()

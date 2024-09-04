## Main script that runs on each Pi to run behavior

import zmq
import pigpio
import numpy as np
import os
import jack
import time
import threading
import random
import json
import socket as sc
import itertools
import queue
import multiprocessing as mp
import pandas as pd
import scipy.signal
from datetime import datetime
import collections


## Killing previous pigpiod and jackd background processes
os.system('sudo killall pigpiod')
os.system('sudo killall jackd')

# Wait long enough to make sure they are killed
time.sleep(1)

## Starting pigpiod and jackd background processes
# Start pigpiod
# TODO: document these parameters
os.system('sudo pigpiod -t 0 -l -x 1111110000111111111111110000')
time.sleep(1)

# Start jackd
# TODO: document these parameters
# TODO: Use subprocess to keep track of these background processes
os.system(
    'jackd -P75 -p16 -t2000 -dalsa -dhw:sndrpihifiberry -P -r192000 -n3 -s &')
time.sleep(1)


## Load parameters for this pi
# Get the hostname of this pi and use that as its name
pi_hostname = sc.gethostname()
pi_name = str(pi_hostname)

# Load the config parameters for this pi
# TODO: document everything in params
param_directory = f"pi/configs/pis/{pi_name}.json"
with open(param_directory, "r") as p:
    params = json.load(p)    

class Noise:
    """Class to define bandpass filtered white noise."""
    def __init__(self, blocksize=1024, fs=192000, duration = 0.01, amplitude=0.01, channel=None, 
        highpass=None, lowpass=None, attenuation_file=None, **kwargs):
        """Initialize a new white noise burst with specified parameters.
        
        The sound itself is stored as the attribute `self.table`. This can
        be 1-dimensional or 2-dimensional, depending on `channel`. If it is
        2-dimensional, then each channel is a column.
        
        Args:
            duration (float): duration of the noise
            amplitude (float): amplitude of the sound as a proportion of 1.
            channel (int or None): which channel should be used
                If 0, play noise from the first channel
                If 1, play noise from the second channel
                If None, send the same information to all channels ("mono")
            highpass (float or None): highpass the Noise above this value
                If None, no highpass is applied
            lowpass (float or None): lowpass the Noise below this value
                If None, no lowpass is applied       
            attenuation_file (string or None)
                Path to where a pd.Series can be loaded containing attenuation
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        # Set duraiton and amplitude as float
        self.blocksize = blocksize
        self.fs = fs
        self.duration = float(duration)
        self.amplitude = float(amplitude)
        
        # Save optional parameters - highpass, lowpass, channel
        if highpass is None:
            self.highpass = None
        else:
            self.highpass = float(highpass)
        
        if lowpass is None:
            self.lowpass = None
        else:
            self.lowpass = float(lowpass)
        
        # Save attenuation
        if attenuation_file is not None:
            self.attenuation = pd.read_table(
                attenuation_file, sep=',').set_index('freq')['atten']
        else:
            self.attenuation = None        
        
        # Save channel
        # Currently only mono or stereo sound is supported
        if channel is None:
            self.channel = None
        try:
            self.channel = int(channel)
        except TypeError:
            self.channel = channel
        
        if self.channel not in [0, 1]:
            raise ValueError(
                "audio channel must be 0 or 1, not {}".format(
                self.channel))

        # Initialize the sound itself
        self.chunks = None
        self.initialized = False
        self.init_sound()

    def init_sound(self):
        """Defines `self.table`, the waveform that is played. 
        
        The way this is generated depends on `self.server_type`, because
        parameters like the sampling rate cannot be known otherwise.
        
        The sound is generated and then it is "chunked" (zero-padded and
        divided into chunks). Finally `self.initialized` is set True.
        """
        # Calculate the number of samples
        self.nsamples = int(np.rint(self.duration * self.fs))
        
        # Generate the table by sampling from a uniform distribution
        # The shape of the table depends on `self.channel`
        # The table will be 2-dimensional for stereo sound
        # Each channel is a column
        # Only the specified channel contains data and the other is zero
        data = np.random.uniform(-1, 1, self.nsamples)
        
        # Highpass filter it
        if self.highpass is not None:
            bhi, ahi = scipy.signal.butter(
                2, self.highpass / (self.fs / 2), 'high')
            data = scipy.signal.filtfilt(bhi, ahi, data)
        
        # Lowpass filter it
        if self.lowpass is not None:
            blo, alo = scipy.signal.butter(
                2, self.lowpass / (self.fs / 2), 'low')
            data = scipy.signal.filtfilt(blo, alo, data)
        
        # Assign data into table
        self.table = np.zeros((self.nsamples, 2))
        assert self.channel in [0, 1]
        self.table[:, self.channel] = data
        
        # Scale by the amplitude
        self.table = self.table * self.amplitude
        
        # Convert to float32
        self.table = self.table.astype(np.float32)
        
        # Apply attenuation
        if self.attenuation is not None:
            # To make the attenuated sounds roughly match the original
            # sounds in loudness, multiply table by np.sqrt(10) (10 dB)
            # Better solution is to encode this into attenuation profile,
            # or a separate "gain" parameter
            self.table = self.table * np.sqrt(10)
        
        # Break the sound table into individual chunks of length blocksize
        self.chunk()

        # Flag as initialized
        self.initialized = True

    def chunk(self):
        """Break the sound in self.table into chunks of length blocksize
        
        The sound in self.table is zero-padded to a length that is a multiple
        of `self.blocksize`. Then it is broken into `self.chunks`, a list 
        of chunks each of length `blocksize`.
        
        TODO: move this into a superclass, since the same code can be used
        for other sounds.
        """
        # Zero-pad the self.table to a new length that is multiple of blocksize
        oldlen = len(self.table)
        
        # Calculate how many blocks we need to contain the sound
        n_blocks_needed = int(np.ceil(oldlen / self.blocksize))
        
        # Calculate the new length
        newlen = n_blocks_needed * self.blocksize

        # Pad with 2d array of zeros
        to_concat = np.zeros(
            (newlen - oldlen, self.table.shape[1]), 
            np.float32)

        # Zero pad
        padded_sound = np.concatenate([self.table, to_concat])
        
        # Start of each chunk
        start_samples = range(0, len(padded_sound), self.blocksize)
        
        # Break the table into chunks
        self.chunks = [
            padded_sound[start_sample:start_sample + self.blocksize, :] 
            for start_sample in start_samples]

class SoundQueue:
    """This is a class used to continuously generate frames of audio and add them to a queue. 
    It also handles updating the parameters of the sound to be played. """
    def __init__(self):
        
        ## Initialize sounds
        # Each block/frame is about 5 ms
        # Longer is more buffer against unexpected delays
        # Shorter is faster to empty and refill the queue
        self.target_qsize = 60

        # Some counters to keep track of how many sounds we've played
        self.n_frames = 0

        # Instancing noise parameters
        self.blocksize = 1024
        self.fs = 192000
        self.amplitude = -0.075
        self.target_rate = 4
        self.target_temporal_log_std = -1.5
        self.center_freq = 10000
        self.bandwidth = 3000
        self.target_lowpass = self.center_freq + (self.bandwidth / 2)
        self.target_highpass = self.center_freq - (self.bandwidth / 2)
        
        # State of channels
        self.left_on = False
        self.right_on = False
        
        # State variable to stop appending frames 
        self.running = False
        
        # Fill the queue with empty frames
        # Sounds aren't initialized till the trial starts
        # Using False here should work even without sounds initialized yet
        self.initialize_sounds(self.blocksize, self.fs, self.amplitude, self.target_highpass,  self.target_lowpass)
        self.set_sound_cycle()

        # Use this to keep track of generated sounds
        self.current_audio_times_df = None
    
    """Object to choose the sounds and pauses for this trial"""
    def update_parameters(self, rate_min, rate_max, irregularity_min, irregularity_max, amplitude_min, amplitude_max, center_freq_min, center_freq_max, bandwidth):
        """Method to update sound parameters dynamically"""
        self.target_rate = random.uniform(rate_min, rate_max)
        self.target_temporal_log_std = random.uniform(irregularity_min, irregularity_max)
        self.amplitude = random.uniform(amplitude_min, amplitude_max)
        self.center_freq = random.uniform(center_freq_min, center_freq_max)
        self.bandwidth = bandwidth
        self.target_lowpass = self.center_freq + (self.bandwidth / 2)
        self.target_highpass = self.center_freq - (self.bandwidth / 2)

        # Debug message
        parameter_message = (
            f"Current Parameters - Amplitude: {self.amplitude}, "
            f"Rate: {self.target_rate} Hz, "
            f"Irregularity: {self.target_temporal_log_std}, "
            f"Center Frequency: {self.center_freq} Hz, "
            f"Bandwidth: {self.bandwidth}"
            )

        #print(parameter_message)
        return parameter_message

    """Method to choose which sound to initialize based on the target channel"""
    def initialize_sounds(self, blocksize, fs, target_amplitude, target_highpass,  target_lowpass):
        """Defines sounds that will be played during the task"""
        ## Define sounds
        # Left and right target noise bursts
        self.left_target_stim = Noise(blocksize, fs,
            duration=0.01, amplitude= self.amplitude, channel=0, 
            lowpass=self.target_lowpass, highpass=self.target_highpass
            )       
        
        self.right_target_stim = Noise(blocksize, fs,
            duration=0.01, amplitude= self.amplitude, channel=1, 
            lowpass=self.target_lowpass, highpass=self.target_highpass
            )  


    def set_sound_cycle(self):
        """Define self.sound_cycle, to go through sounds
        
        params : dict
            This comes from a message on the net node.
            Possible keys:
                left_on
                right_on
                left_mean_interval
                right_mean_interval
        """
        # Array to attach chunked sounds
        self.sound_block = []

        # Helper function
        def append_gap(gap_chunk_size=30):
            """Append `gap_chunk_size` silent chunks to sound_block"""
            for n_blank_chunks in range(gap_chunk_size):
                self.sound_block.append(
                    np.zeros((1024, 2), dtype='float32'))

        # Extract params or use defaults
        left_on = self.left_on
        right_on = self.right_on
        left_target_rate = self.target_rate 
        right_target_rate = self.target_rate 
        
        #print(self.target_rate)
        #print(left_on)
        #print(right_on)
        
        # Global params
        target_temporal_std = 10 ** self.target_temporal_log_std 
        
        ## Generate intervals 
        # left target
        if left_on and left_target_rate > 1e-3:
            # Change of basis
            mean_interval = 1 / left_target_rate
            var_interval = target_temporal_std ** 2

            # Change of basis
            gamma_shape = (mean_interval ** 2) / var_interval
            gamma_scale = var_interval / mean_interval

            # Draw
            left_target_intervals = np.random.gamma(
                gamma_shape, gamma_scale, 100)
        else:
            left_target_intervals = np.array([])

        # right target
        if right_on and right_target_rate > 1e-3:
            # Change of basis
            mean_interval = 1 / right_target_rate
            var_interval = target_temporal_std ** 2

            # Change of basis
            gamma_shape = (mean_interval ** 2) / var_interval
            gamma_scale = var_interval / mean_interval

            # Draw
            right_target_intervals = np.random.gamma(
                gamma_shape, gamma_scale, 100)
        else:
            right_target_intervals = np.array([])              
        
        #print(left_target_intervals)
        #print(right_target_intervals)

        
        ## Sort all the drawn intervals together
        # Turn into series
        left_target_df = pd.DataFrame.from_dict({
            'time': np.cumsum(left_target_intervals),
            'side': ['left'] * len(left_target_intervals),
            'sound': ['target'] * len(left_target_intervals),
            })
        right_target_df = pd.DataFrame.from_dict({
            'time': np.cumsum(right_target_intervals),
            'side': ['right'] * len(right_target_intervals),
            'sound': ['target'] * len(right_target_intervals),
            })

        # Concatenate them all together and resort by time
        both_df = pd.concat([
            left_target_df, right_target_df], axis=0).sort_values('time')

        # Calculate the gap between sounds
        both_df['gap'] = both_df['time'].diff().shift(-1)
        
        # Drop the last row which has a null gap
        both_df = both_df.loc[~both_df['gap'].isnull()].copy()

        # Keep only those below the sound cycle length
        both_df = both_df.loc[both_df['time'] < 10].copy()
        
        # Nothing should be null
        assert not both_df.isnull().any().any() 

        # Calculate gap size in chunks
        both_df['gap_chunks'] = (both_df['gap'] * (self.fs / self.blocksize))
        both_df['gap_chunks'] = both_df['gap_chunks'].round().astype(int)
        
        # Floor gap_chunks at 1 chunk, the minimal gap size
        # This is to avoid distortion
        both_df.loc[both_df['gap_chunks'] < 1, 'gap_chunks'] = 1
        
        # Save
        self.current_audio_times_df = both_df.copy()
        self.current_audio_times_df = self.current_audio_times_df.rename(
            columns={'time': 'relative_time'})

        
        ## Depends on how long both_df is
        # If both_df has a nonzero but short length, results will be weird,
        # because it might just be one noise burst repeating every ten seconds
        # This only happens with low rates ~0.1Hz
        #print(both_df)
        if len(both_df) == 0:
            # If no sound, then just put gaps
            append_gap(100)
        else:
            # Iterate through the rows, adding the sound and the gap
            # TODO: the gap should be shorter by the duration of the sound,
            # and simultaneous sounds should be possible
            for bdrow in both_df.itertuples():
                # Append the sound
                if bdrow.side == 'left' and bdrow.sound == 'target':
                    for frame in self.left_target_stim.chunks:
                        self.sound_block.append(frame)
                        #print(frame.shape)
                        assert frame.shape == (1024, 2)
                elif bdrow.side == 'right' and bdrow.sound == 'target':
                    for frame in self.right_target_stim.chunks:
                        self.sound_block.append(frame)
                        #print(frame.shape)
                        assert frame.shape == (1024, 2)                        
                else:
                    raise ValueError(
                        "unrecognized side and sound: {} {}".format(
                        bdrow.side, bdrow.sound))
                
                # Append the gap
                append_gap(bdrow.gap_chunks)
        
        
        ## Cycle so it can repeat forever
        self.sound_cycle = itertools.cycle(self.sound_block)        

    def play(self):
        """A single stage"""
        # Don't want to do a "while True" here, because we need to exit
        # this method eventually, so that it can respond to END
        # But also don't want to change stage too frequently or the debug
        # messages are overwhelming
        for n in range(10):
            # Add stimulus sounds to queue as needed
            self.append_sound_to_queue_as_needed()

            # Don't want to iterate too quickly, but rather add chunks
            # in a controlled fashion every so often
            #time.sleep(0.1)
    
        ## Continue to the next stage (which is this one again)
        # If it is cleared, then nothing happens until the next message
        # from the Parent (not sure why)
        # If we never end this function, then it won't respond to END
        #self.stage_block.set()
    
    def append_sound_to_queue_as_needed(self, verbose=False):
        """Dump frames from `self.sound_cycle` into queue

        The queue is filled until it reaches `self.target_qsize`

        This function should be called often enough that the queue is never
        empty.
        """        
        # TODO: as a figure of merit, keep track of how empty the queue gets
        # between calls. If it's getting too close to zero, then target_qsize
        # needs to be increased.
        # Get the size of queue now
        qsize = len(self.sound_queue)
        start_qsize = qsize

        # Add frames until target size reached
        # TODO: append 10 extra frames, for a bit of stickiness
        while qsize < self.target_qsize:
            # Add a frame from the sound cycle
            frame = next(self.sound_chooser)
            self.sound_queue.appendleft(frame)
            
            # Update qsize
            qsize = len(self.sound_queue)
        
        if verbose:
            if start_qsize != qsize:
                print('topped up qsize: {} to {}'.format(start_qsize, qsize))
            
    def empty_queue(self, tosize=5):
        """Empty queue
        
        Pop frames off the left side of sound_queue (that is, the newest
        frames) until sound_queue has size `tosize`.
        
        tosize : int
            This many frames of audio from before `empty_queue` was called
            will still be played. 
            As this gets larger, the sound takes longer to stop.
            As this gets smaller, we risk running out of frames and
            causing an xrun.
        """
        # Continue until we're at or below the target size
        while len(self.sound_queue) > tosize:
            try:
                self.sound_queue.popleft()
            except IndexError:
                # This shouldn't really happen as long as tosize is 
                # significantly more than 0
                print('warning: sound queue was prematurely emptied')
                break

    def __next__(self):
        return self.sound_queue.pop()
    
    def set_channel(self, mode):
        """Controlling which channel the sound is played from """
        if mode == 'none':
            self.left_on = False
            self.right_on = False
        if mode == 'left':
            self.left_on = True
            self.right_on = False
        if mode == 'right':
            self.left_on = False
            self.right_on = True

# Define a JackClient, which will play sounds in the background
# Rename to SoundPlayer to avoid confusion with jack.Client
class SoundPlayer(object):
    """Reads frames of audio from a queue and provides them to a jack.Client

    This object must be initialized with a `sound_queue` argument that provides
    a frame of audio via `sound_queue.get()`. It should also implement
    `sound_queue.empty()`. The SoundQueue object provides this functionality. 
    
    The `process` method of this object may be provided to jack.Client, which
    will call it every ~5 ms to request new audio. 
    
    Attributes
    ----------
    name : str
        This is only passed to jack.Client, which requires it.
    
    """
    def __init__(self, sound_queuer, name='jack_client', verbose=True):
        """Initialize a new JackClient

        This object has one job: get frames of audio out of sound_queue
        and into jack.Client. All logic relating to the frames of audio that
        go into the sound_queue should be handled by something else, such
        as SoundQueuer.

        This object contains a jack.Client object that actually plays audio.
        It provides methods to send sound to its jack.Client, notably a 
        `process` function which is called every 5 ms or so.
        
        Arguments
        ----------
        name : str
            Required by jack.Client
        
        sound_queue : deque-like object
            Should produce a frame of audio on request
        
        Flow
        ----
        * Initialize self.client as a jack.Client 
        * Register outports
        * Set client's process callback to self.process
        * Activate client
        * Hook up outports to target ports
        """
        ## Store provided arguments
        self.name = name
        self.sound_queuer = sound_queuer
        self.verbose = verbose
        
        # Keep track of time of last warning
        self.dt_last_warning = None
        self.frame_rate_warning_already_issued = False
        
        
        ## Create the contained jack.Client
        # Creating a jack client
        self.client = jack.Client(self.name)

        # Debug message
        if self.verbose:
            print(
                "New jack.Client initialized with blocksize " + 
                "{} and samplerate {}".format(
                self.client.blocksize, self.client.samplerate))


        ## Set up outports and register callbacks and activate client
        # Set up outchannels
        self.client.outports.register('out_0')
        self.client.outports.register('out_1')

        # Set up the process callback
        # This will be called on every block and must provide data
        self.client.set_process_callback(self.process)

        # Activate the client
        # Strangely, this must be done before hooking up the outports
        self.client.activate()

        # Get the actual physical ports that can play sound
        target_ports = self.client.get_ports(
            is_physical=True, is_input=True, is_audio=True)
        assert len(target_ports) == 2

        # Hook up the outports (data sinks) to physical ports
        self.client.outports[0].connect(target_ports[0])
        self.client.outports[1].connect(target_ports[1])
    
    def process(self, frames, verbose=False):
        """Write a frame of audio from self.sound_queue to self.client.outports
        
        This function is called by self.client every 5 ms or whenever new
        audio is needed.
        
        Flow
        * A frame of audio is popped from self.sound_queue
        * If sound_queue is empty, a frame of zeros is generated. This should
          not happen, so a warning is printed, but not more than once per
          second.
        * If the frame is not of shape (blocksize, 2), raises ValueError
        * Frame is converted to float32
        * Each column of frame is written to the outports
        """
        # Optional debug message
        if verbose:
            print('process called')
        
        # Try to get audio data from self.sound_queue
        queue_is_empty = False
        try:
            data = next(self.sound_queuer)
        except IndexError:
            # The queue is empty
            # Play zeros and set the flag
            queue_is_empty = True
            data = np.zeros((self.client.blocksize, 2), dtype='float32')
        
        # Warn if the queue was empty
        if queue_is_empty:
            # Calculate how long it's been since the last warning
            dt_now = datetime.datetime.now()
            if self.dt_last_warning is not None:
                warning_thresh = (self.dt_last_warning + 
                    datetime.timedelta(seconds=1))
            
            # If it's been long enough since the warning, or if warning
            # has never been issued, warn now
            if self.dt_last_warning is None or dt_now > warning_thresh:
                # Set time of last warning
                self.dt_last_warning = dt_now
                
                # Warn
                # This is the last thing we check, so that verbose can be 
                # changed and everything will still be up to date
                if self.verbose:
                    print(
                        "warning: sound_queue is empty, playing silence and "
                        "silencing warnings for 1 s")
        
        # Make sure audio data has the correct shape
        if data.shape != (self.client.blocksize, 2):
            raise ValueError(
                "error: process received data of shape {} ".format(data.shape) + 
                "but it should have been {}".format((self.client.blocksize, 2))
                )
        
        # Ensure it is the correct dtype
        data = data.astype('float32')
        
        # Write one column to each channel
        self.client.outports[0].get_array()[:] = data[:, 0]
        self.client.outports[1].get_array()[:] = data[:, 1]

# Defining a common queue to be used by both classes 
# Initializing queues to be used by sound player
sound_queue = collections.deque()
nonzero_blocks = collections.deque()

# Lock for thread-safe set_channel() updates
qlock = mp.Lock()
nb_lock = mp.Lock()

# Define a client to play sounds
sound_chooser = SoundQueue()
sound_player = SoundPlayer(name='sound_player')

# Raspberry Pi's identity (Change this to the identity of the Raspberry Pi you are using)
# TODO: what is the difference between pi_identity and pi_name? # They are functionally the same, this line is from before I imported 
pi_identity = params['identity']

## Creating a ZeroMQ context and socket for communication with the central system
# TODO: what information travels over this socket? Clarify: do messages on
# this socket go out or in?

poke_context = zmq.Context()
poke_socket = poke_context.socket(zmq.DEALER)

# Setting the identity of the socket in bytes
poke_socket.identity = bytes(f"{pi_identity}", "utf-8") 


## Creating a ZeroMQ context and socket for receiving JSON files
# TODO: what information travels over this socket? Clarify: do messages on
# this socket go out or in?
#  - This socket only receives messages sent from the GUI regarding the parameters 
json_context = zmq.Context()
json_socket = json_context.socket(zmq.SUB)

## Creating a ZeroMQ context and socket for communication with bonsai
bonsai_context = zmq.Context()
bonsai_socket = bonsai_context.socket(zmq.SUB)
router_ip3 = "tcp://" + f"{params['gui_ip']}" + f"{params['bonsai_port']}"
bonsai_socket.connect(router_ip3)

# Subscribe to all incoming messages
bonsai_socket.subscribe(b"")

## Connect to the server
# Connecting to IP address (192.168.0.99 for laptop, 192.168.0.207 for seaturtle)
router_ip = "tcp://" + f"{params['gui_ip']}" + f"{params['poke_port']}" 
poke_socket.connect(router_ip) 

# Send the identity of the Raspberry Pi to the server
poke_socket.send_string(f"{pi_identity}") 

# Print acknowledgment
print(f"Connected to router at {router_ip}")  

## Connect to json socket
router_ip2 = "tcp://" + f"{params['gui_ip']}" + f"{params['config_port']}"
json_socket.connect(router_ip2) 

# Subscribe to all incoming messages
json_socket.subscribe(b"")

# Print acknowledgment
print(f"Connected to router at {router_ip2}")  

## Pigpio configuration
# TODO: move these methods into a Nosepoke object. That object should be
# defined in another script and imported here
a_state = 0
count = 0
nosepoke_pinL = 8
nosepoke_pinR = 15
nosepokeL_id = params['nosepokeL_id']
nospokeR_id = params['nosepokeR_id']

# Global variables for which nospoke was detected
left_poke_detected = False
right_poke_detected = False
current_port_poked = None
poke_time = None

# Callback function for nosepoke pin (When the nosepoke is completed)
def poke_inL(pin, level, tick):
    global a_state, left_poke_detected
    a_state = 0
    if left_poke_detected:
        # Write to left pin
        print("Left poke detected!")
        pi.set_mode(17, pigpio.OUTPUT)
        if params['nosepokeL_type'] == "901":
            pi.write(17, 1)
        elif params['nosepokeL_type'] == "903":
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
        if params['nosepokeR_type'] == "901":
            pi.write(10, 1)
        elif params['nosepokeR_type'] == "903":
            pi.write(10, 0)
            
    # Reset poke detected flags
    right_poke_detected = False

# Callback functions for nosepoke pin (When the nosepoke is detected)
def poke_detectedL(pin, level, tick): 
    global a_state, count, left_poke_detected, current_port_poked, poke_time
    
    a_state = 1
    count += 1
    left_poke_detected = True

    print("Poke Completed (Left)")
    print("Poke Count:", count)
    nosepoke_idL = params['nosepokeL_id']  # Set the left nosepoke_id here according to the pi
    current_port_poked = nosepoke_idL
    pi.set_mode(17, pigpio.OUTPUT)
    if params['nosepokeL_type'] == "901":
        pi.write(17, 0)
    elif params['nosepokeL_type'] == "903":
        pi.write(17, 1)
        
    # Get current datetime
    poke_time = datetime.now()
        
    # Sending nosepoke_id wirelessly with datetime
    try:
        print(f"Sending nosepoke_id = {nosepoke_idL} at {poke_time}") 
        poke_socket.send_string(f"{nosepoke_idL}")
        poke_socket.send_string(f"Poke Time: {poke_time}")
    except Exception as e:
        print("Error sending nosepoke_id:", e)

def poke_detectedR(pin, level, tick): 
    global a_state, count, right_poke_detected, current_port_poked, poke_time 
    
    a_state = 1
    count += 1
    right_poke_detected = True
    
    print("Poke Completed (Right)")
    print("Poke Count:", count)
    nosepoke_idR = params['nosepokeR_id']  # Set the right nosepoke_id here according to the pi
    current_port_poked = nosepoke_idR
    pi.set_mode(10, pigpio.OUTPUT)
    if params['nosepokeR_type'] == "901":
        pi.write(10, 0)
    elif params['nosepokeR_type'] == "903":
        pi.write(10, 1)
    
    # Get current datetime
    poke_time = datetime.now()
    
    # Sending nosepoke_id wirelessly with datetime
    try:
        print(f"Sending nosepoke_id = {nosepoke_idR} at {poke_time}") 
        poke_socket.send_string(f"{nosepoke_idR}")
        poke_socket.send_string(f"Poke Time: {poke_time}")
    except Exception as e:
        print("Error sending nosepoke_id:", e)


def open_valve(port):
    """Open the valve for port
    
    port : TODO document what this is
    TODO: reward duration needs to be a parameter of the task or mouse # It is in the test branch
    """
    reward_value = config_data['reward_value']
    if port == int(params['nosepokeL_id']):
        pi.set_mode(6, pigpio.OUTPUT)
        pi.write(6, 1)
        time.sleep(reward_value)
        pi.write(6, 0)
    
    if port == int(params['nosepokeR_id']):
        pi.set_mode(26, pigpio.OUTPUT)
        pi.write(26, 1)
        time.sleep(reward_value)
        pi.write(26, 0)

# TODO: document this function
def flash():
    pi.set_mode(22, pigpio.OUTPUT)
    pi.write(22, 1)
    pi.set_mode(11, pigpio.OUTPUT)
    pi.write(11, 1)
    time.sleep(0.5)
    pi.write(22, 0)
    pi.write(11, 0)  

# Function with logic to stop session
def stop_session():
    global reward_pin, current_pin, prev_port
    flash()
    current_pin = None
    prev_port = None
    pi.write(17, 0)
    pi.write(10, 0)
    pi.write(27, 0)
    pi.write(9, 0)
    sound_chooser.running = False
    sound_chooser.set_channel('none')
    sound_chooser.empty_queue()

## Set up pigpio and callbacks
# TODO: rename this variable to pig or something; "pi" is ambiguous
pi = pigpio.pi()
pi.callback(nosepoke_pinL, pigpio.FALLING_EDGE, poke_inL)
pi.callback(nosepoke_pinL, pigpio.RISING_EDGE, poke_detectedL)
pi.callback(nosepoke_pinR, pigpio.FALLING_EDGE, poke_inR)
pi.callback(nosepoke_pinR, pigpio.RISING_EDGE, poke_detectedR)

## Create a Poller object
# TODO: document .. What is this?
poller = zmq.Poller()
poller.register(poke_socket, zmq.POLLIN)
poller.register(json_socket, zmq.POLLIN)
poller.register(bonsai_socket, zmq.POLLIN)

## Initialize variables for sound parameters
# These are not sound parameters .. TODO document
pwm_frequency = 1
pwm_duty_cycle = 50

# Duration of sounds
rate_min = 0.0
rate_max = 0.0

# Duration of pauses
irregularity_min = 0.0
irregularity_max = 0.0

# Range of amplitudes
# TODO: these need to be received from task, not specified here # These were all initial values set incase a task was not selected
amplitude_min = 0.0
amplitude_max = 0.0

# Storing the type of task (mainly for poketrain)
task = None

## Main loop to keep the program running and exit when it receives an exit command
try:
    ## TODO: document these variables and why they are tracked
    # Initialize reward_pin variable
    reward_pin = None
    
    # Track the currently active LED
    current_pin = None  
    
    # Track prev_port
    prev_port = None

    # Keeping track of the bonsai parameters to change the volume of the sound
    msg2 = None
    last_msg2 = None
    
    ## Loop forever
    while True:
        ## Wait for events on registered sockets
        # TODO: how long does it wait? # Can be set, currently not sure

        # Initial logic when bonsai is started
        if last_msg2 == None:
            if msg2 == "True":
                # Reducing volume of the sound
                #sound_chooser.running = False    
                sound_chooser.amplitude = 0.25 * sound_chooser.amplitude
            
                # Emptying queue and setting sound to play
                sound_chooser.empty_queue()

                # Setting sound to play 
                sound_chooser.initialize_sounds(sound_player.blocksize, sound_player.fs, 
                    sound_chooser.amplitude, sound_chooser.target_highpass, sound_chooser.target_lowpass)
                sound_chooser.set_sound_cycle()
                sound_chooser.append_sound_to_queue_as_needed()
            elif msg2 == "False" or None:
                sound_chooser.amplitude = sound_chooser.amplitude
        
        # Appending sound to queue 
        sound_chooser.append_sound_to_queue_as_needed()

        socks = dict(poller.poll(100))
        socks2 = dict(poller.poll(100))
        socks3 = dict(poller.poll(100))

        ## Check for incoming messages on json_socket
        # If so, use it to update the acoustic parameters
        if json_socket in socks and socks[json_socket] == zmq.POLLIN:
            ## Data was received on json_socket
            # Receive the data (this is blocking) # Forgot to remove comment after implementing poller
            # TODO: what does blocking mean here? How long does it block?
            json_data = json_socket.recv_json()
            
            # Deserialize JSON data
            config_data = json.loads(json_data)
            
            # Debug print
            print(config_data)

            # Update parameters from JSON data
            task =  config_data['task']
            rate_min = config_data['rate_min']
            rate_max = config_data['rate_max']
            irregularity_min = config_data['irregularity_min']
            irregularity_max = config_data['irregularity_max']
            amplitude_min = config_data['amplitude_min']
            amplitude_max = config_data['amplitude_max']
            center_freq_min = config_data['center_freq_min']
            center_freq_max = config_data['center_freq_max']
            bandwidth = config_data['bandwidth']
            
            # Update the jack client with the new acoustic parameters
            new_params = sound_chooser.update_parameters(
                rate_min, rate_max, irregularity_min, irregularity_max, 
                amplitude_min, amplitude_max, center_freq_min, center_freq_max, bandwidth)
            poke_socket.send_string(new_params)
            sound_chooser.initialize_sounds(sound_player.blocksize, sound_player.fs, 
                sound_chooser.amplitude, sound_chooser.target_highpass, sound_chooser.target_lowpass)
            sound_chooser.set_sound_cycle()
            
            # Debug print
            print("Parameters updated")

        # Logic to handle messages from the bonsai socket
        if bonsai_socket in socks2 and socks2[bonsai_socket] == zmq.POLLIN:
            msg2 = bonsai_socket.recv_string()  
            
            # Different messages have different effects
            if msg2 == "True": 
                if last_msg2 == "False" or last_msg2 == None:
                    print("Decreasing the volume of the sound")
                    # Condition to start the task
                    sound_chooser.amplitude = 0.25 * sound_chooser.amplitude
                    sound_chooser.empty_queue()

                    # Setting sound to play 
                    sound_chooser.initialize_sounds(sound_player.blocksize, sound_player.fs, 
                        sound_chooser.amplitude, sound_chooser.target_highpass, sound_chooser.target_lowpass)
                    
                    sound_chooser.set_sound_cycle()
                    sound_chooser.append_sound_to_queue_as_needed()
                    last_msg2 = msg2
                else:
                    last_msg2 = msg2

            elif msg2 == "False":
                # Testing amplitude
                if last_msg2 == "True":
                    print("Increasing the volume of the sound")
                    sound_chooser.amplitude = 4 * sound_chooser.amplitude
                    sound_chooser.empty_queue()

                    # Setting sound to play 
                    sound_chooser.initialize_sounds(sound_player.blocksize, sound_player.fs, 
                        sound_chooser.amplitude, sound_chooser.target_highpass, sound_chooser.target_lowpass)
                    
                    sound_chooser.set_sound_cycle()
                    sound_chooser.append_sound_to_queue_as_needed()
                    last_msg2 = msg2
                else:
                    last_msg2 = msg2

        # Separate logic for Poketrain task
        if task == 'Poketrain':
            if left_poke_detected == True or right_poke_detected == True:
                open_valve()
        
        ## Check for incoming messages on poke_socket
        # TODO: document the types of messages that can be sent on poke_socket 
        if poke_socket in socks2 and socks2[poke_socket] == zmq.POLLIN:
            # Blocking receive: #flags=zmq.NOBLOCK)  
            # Non-blocking receive
            msg = poke_socket.recv_string()  
    
            # Different messages have different effects
            if msg == 'exit': 
                # Condition to terminate the main loop
                # TODO: why are these pi.write here? # To turn the LEDs on the Pi off when the GUI is closed
                stop_session()
                print("Received exit command. Terminating program.")
                
                # Wait for the client to finish processing any remaining chunks
                # TODO: why is this here? It's already deactivated 
                ##time.sleep(sound_player.noise.target_rate + sound_player.noise.target_temporal_log_std)
                
                # Stop the Jack client
                # TODO: Probably want to leave this running for the next
                # session
                sound_player.client.deactivate()
                
                # Exit the loop
                break  
            
            # Receiving message from stop button 
            if msg == 'stop':
                stop_session()
                
                # Sending stop signal wirelessly to stop update function
                try:
                    poke_socket.send_string("stop")
                except Exception as e:
                    print("Error stopping session", e)

                print("Stop command received. Stopping sequence.")
                continue

            # Communicating with start button to restart session
            if msg == 'start':
                try:
                    poke_socket.send_string("start")
                except Exception as e:
                    print("Error stopping session", e)
            
            elif msg.startswith("Reward Port:"):    
                ## This specifies which port to reward
                # Debug print
                print(msg)
                
                # Extract the integer part from the message
                msg_parts = msg.split()
                if len(msg_parts) != 3 or not msg_parts[2].isdigit():
                    print("Invalid message format.")
                    continue
                
                # Extract the integer part
                value = int(msg_parts[2])  
                
                # Turn off the previously active LED if any
                if current_pin is not None:
                    pi.write(current_pin, 0)
                
                # Manipulate pin values based on the integer value
                if value == int(params['nosepokeL_id']):
                    # Starting sound
                    sound_chooser.running = True
                    
                    # Reward pin for left
                    # TODO: these reward pins need to be stored as a parameter,
                    # not hardcoded here
                    reward_pin = 27  
                    
                    # TODO: what does this do? Why not just have reward pin
                    # always be set to output? # These are for the LEDs to blink
                    pi.set_mode(reward_pin, pigpio.OUTPUT)
                    pi.set_PWM_frequency(reward_pin, pwm_frequency)
                    pi.set_PWM_dutycycle(reward_pin, pwm_duty_cycle)
                    
                    # Playing sound from the left speaker
                    sound_chooser.empty_queue()
                    sound_chooser.set_channel('left')
                    sound_chooser.set_sound_cycle()
                    sound_chooser.append_sound_to_queue_as_needed()
                    
                    # Debug message
                    print(f"Turning port {value} green")

                    # Keep track of which port is rewarded and which pin
                    # is rewarded
                    prev_port = value
                    current_pin = reward_pin # for LED only 

                elif value == int(params['nosepokeR_id']):
                    # Starting sound
                    sound_chooser.running = True
                    
                    # Reward pin for right
                    # TODO: these reward pins need to be stored as a parameter,
                    # not hardcoded here                    
                    reward_pin = 9
                    
                    # TODO: what does this do? Why not just have reward pin
                    # always be set to output? # LED blinking
                    pi.set_mode(reward_pin, pigpio.OUTPUT)
                    pi.set_PWM_frequency(reward_pin, pwm_frequency)
                    pi.set_PWM_dutycycle(reward_pin, pwm_duty_cycle)
                    
                    # Playing sound from the right speaker
                    sound_chooser.empty_queue()
                    sound_chooser.set_channel('right')
                    sound_chooser.set_sound_cycle()
                    sound_chooser.append_sound_to_queue_as_needed()

                    # Debug message
                    print(f"Turning port {value} green")
                    
                    # Keep track of which port is rewarded and which pin
                    # is rewarded
                    prev_port = value
                    current_pin = reward_pin
                
                else:
                    # TODO: document why this happens
                    # Current Reward Port
                    prev_port = value
                    print(f"Current Reward Port: {value}")
                
            elif msg.startswith("Reward Poke Completed"):
                # This seems to occur when the GUI detects that the poked
                # port was rewarded. This will be too slow. The reward port
                # should be opened if it knows it is the rewarded pin. 
                
                # Emptying the queue completely
                sound_chooser.running = False
                sound_chooser.set_channel('none')
                sound_chooser.empty_queue()

                # Opening Solenoid Valve
                flash()
                open_valve(prev_port)

                # Verifying state from bonsai 
                if last_msg2 == "True":
                    sound_chooser.amplitude = 4 * sound_chooser.amplitude
                elif last_msg2 == "False":
                    sound_chooser.amplitude = sound_chooser.amplitude
                
                # Adding an inter trial interval
                time.sleep(1)
                
                # Updating Parameters
                # TODO: fix this; rate_min etc are not necessarily defined
                # yet, or haven't changed recently
                # Reset play mode to 'none'

                new_params = sound_chooser.update_parameters(
                    rate_min, rate_max, irregularity_min, irregularity_max, 
                    amplitude_min, amplitude_max, center_freq_min, center_freq_max, bandwidth)
                poke_socket.send_string(new_params)
                
                # Turn off the currently active LED
                if current_pin is not None:
                    pi.write(current_pin, 0)
                    print("Turning off currently active LED.")
                    current_pin = None  # Reset the current LED
                else:
                    print("No LED is currently active.")
           
            else:
                print("Unknown message received:", msg)

except KeyboardInterrupt:
    # Stops the pigpio connection
    pi.stop()

finally:
    # Close all sockets and contexts
    poke_socket.close()
    poke_context.term()
    json_socket.close()
    json_context.term()
        
    























        
    

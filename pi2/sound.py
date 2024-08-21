import numpy as np
import os
import jack
import time
import random
import itertools
import queue
import pandas as pd
import scipy.signal


## SETTING UP CLASSES USED TO GENERATE AUDIO
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
        
        ## I think this can be removed because mono isn't being used(?)
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
            
            # Apply the attenuation to each column
            # for n_column in range(self.table.shape[1]):
            #     self.table[:, n_column] = apply_attenuation(
            #         self.table[:, n_column], self.attenuation, self.fs)
        
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

class SoundQueuer:
    """Continuously generate frames of audio and add them to a queue. 
    
    It also handles updating the parameters of the sound to be played. 
    """
    def __init__(self):
        # Initializing queues 
        self.sound_queue = mp.Queue()
        self.nonzero_blocks = mp.Queue()

        # Lock for thread-safe set_channel() updates
        self.qlock = mp.Lock()
        self.nb_lock = mp.Lock()



        
        ## Initialize sounds
        # Each block/frame is about 5 ms
        # Longer is more buffer against unexpected delays
        # Shorter is faster to empty and refill the queue
        self.target_qsize = 200

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
            f"Rate: {self.target_rate} s, "
            f"Irregularity: {self.target_temporal_log_std} s, "
            f"Center Frequency: {self.center_freq} Hz, "
            f"Bandwidth: {self.bandwidth}"
            )

        print(parameter_message)
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
        
        ## Debug Prints
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
    
    def append_sound_to_queue_as_needed(self):
        """Dump frames from `self.sound_cycle` into queue

        The queue is filled until it reaches `self.target_qsize`

        This function should be called often enough that the queue is never
        empty.
        """        
        # TODO: as a figure of merit, keep track of how empty the queue gets
        # between calls. If it's getting too close to zero, then target_qsize
        # needs to be increased.
        # Get the size of queue now
        qsize = sound_queue.qsize()

        # Add frames until target size reached
        while self.running ==True and qsize < self.target_qsize:
            with qlock:
                # Add a frame from the sound cycle
                frame = next(self.sound_cycle)
                #frame = np.random.uniform(-.01, .01, (1024, 2)) 
                sound_queue.put_nowait(frame)
                
                # Keep track of how many frames played
                self.n_frames = self.n_frames + 1
            
            # Update qsize
            qsize = sound_queue.qsize()
            
    def empty_queue(self, tosize=0):
        """Empty queue"""
        while True:
            # I think it's important to keep the lock for a short period
            # (ie not throughout the emptying)
            # in case the `process` function needs it to play sounds
            # (though if this does happen, there will be an artefact because
            # we just skipped over a bunch of frames)
            with qlock:
                try:
                    data = sound_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Stop if we're at or below the target size
            qsize = sound_queue.qsize()
            if qsize < tosize:
                break
        
        qsize = sound_queue.qsize()
    
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
    def __init__(self, name='jack_client'):
        """Initialize a new JackClient

        This object contains a jack.Client object that actually plays audio.
        It provides methods to send sound to its jack.Client, notably a 
        `process` function which is called every 5 ms or so.
        
        name : str
            Required by jack.Client
        # 
        sound_queue : mp.Queue
            Should produce a frame of audio on request after filling up to qsize
        
        This object should focus only on playing sound as precisely as
        possible.
        """
        ## Store provided parameters
        self.name = name
        
        ## Create the contained jack.Client
        # Creating a jack client
        self.client = jack.Client(self.name)

        # Pull these values from the initialized client
        # These come from the jackd daemon
        # `blocksize` is the number of samples to provide on each `process`
        # call
        self.blocksize = self.client.blocksize
        
        # `fs` is the sampling rate
        self.fs = self.client.samplerate
        
        # Debug message
        print("Received blocksize {} and fs {}".format(self.blocksize, self.fs))

        ## Set up outchannels
        self.client.outports.register('out_0')
        self.client.outports.register('out_1')
        
        ## Set up the process callback
        # This will be called on every block and must provide data
        self.client.set_process_callback(self.process)

        ## Activate the client
        self.client.activate()

        ## Hook up the outports (data sinks) to physical ports
        # Get the actual physical ports that can play sound
        target_ports = self.client.get_ports(
            is_physical=True, is_input=True, is_audio=True)
        assert len(target_ports) == 2

        # Connect virtual outport to physical channel
        self.client.outports[0].connect(target_ports[0])
        self.client.outports[1].connect(target_ports[1])
    
    def process(self, frames):
        """Process callback function (used to play sound)
        Fills frames of sound into the queue and plays stereo output from either the right or left channel
        """
        # Check if the queue is empty
        if sound_queue.empty():
            # No sound to play, so play silence 
            # Although this shouldn't be happening
            for n_outport, outport in enumerate(self.client.outports):
                buff = outport.get_array()
                buff[:] = np.zeros(self.blocksize, dtype='float32')
            
        else:
            # Queue is not empty, so play data from it
            data = sound_queue.get()
            if data.shape != (self.blocksize, 2):
                print(data.shape)
            assert data.shape == (self.blocksize, 2)

            # Write one column to each channel for stereo
            for n_outport, outport in enumerate(self.client.outports):
                buff = outport.get_array()
                buff[:] = data[:, n_outport]

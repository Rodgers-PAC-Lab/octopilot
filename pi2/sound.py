import numpy as np
import os
import jack
import time
import random
import itertools
import queue
import pandas as pd
import scipy.signal
import collections
import datetime

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


class SoundChooser_IntermittentBursts(object):
    """Determines the sounds to play on this trial and loads a sound_cycle
    
    This object should know about the audio logic of the task (e.g.,
    what center frequencies to play). It shouldn't have to worry about 
    real-time issues like loading sounds into a queue. It just has to set
    up sound_cycle once.
    """
    def __init__(self, blocksize, fs):
        # Store jack client parameters
        self.blocksize = blocksize
        self.fs = fs
        
        # Initialize a cycle that always generates silence
        # So that this object can respond to `next` even before it knows
        # what sound to play
        self.cycle_of_audio_frames = itertools.cycle(
            [np.zeros((self.blocksize, 2))])
    
    def set_left_sound(self, left_params):
        # Generate the left sound
        if left_params['silenced']:
            self.left_sound = None
        else:
            lowpass = left_params['center_frequency'] - left_params['bandwidth'] / 2
            highpass = left_params['center_frequency'] + left_params['bandwidth'] / 2
            self.left_sound = Noise(
                blocksize=self.blocksize,
                fs=self.fs,
                duration=left_params['duration'],
                amplitude=left_params['amplitude'],
                channel=0,
                lowpass=lowpass,
                highpass=highpass,
                )
    
    def set_right_sound(self, right_params):
        # Generate the right sound
        if right_params['silenced']:
            self.right_sound = None
        else:
            lowpass = right_params['center_frequency'] - right_params['bandwidth'] / 2
            highpass = right_params['center_frequency'] + right_params['bandwidth'] / 2
            self.right_sound = Noise(
                blocksize=self.blocksize,
                fs=self.fs,
                duration=right_params['duration'],
                amplitude=right_params['amplitude'],
                channel=0,
                lowpass=lowpass,
                highpass=highpass,
                )       

    def set_left_intervals(self, left_params):
        """Sets self.left_intervals according to left_params"""
        # Intervals for left
        if left_params['silenced']:
            self.left_intervals = np.array([])
        
        else:
            # Change of basis
            mean_interval = 1 / left_params['rate']
            var_interval = left_params['temporal_std'] ** 2
            gamma_shape = (mean_interval ** 2) / var_interval
            gamma_scale = var_interval / mean_interval

            # Draw from distribution
            self.left_intervals = np.random.gamma(
                gamma_shape, gamma_scale, 100)

    def set_right_intervals(self, right_params):
        """Sets self.right_intervals according to right_params"""        
        # Intervals for right
        if right_params['silenced']:
            self.right_intervals = np.array([])
        
        else:
            # Change of basis
            mean_interval = 1 / right_params['rate']
            var_interval = right_params['temporal_std'] ** 2
            gamma_shape = (mean_interval ** 2) / var_interval
            gamma_scale = var_interval / mean_interval

            # Draw from distribution
            self.right_intervals = np.random.gamma(
                gamma_shape, gamma_scale, 100)        

    def set_stereo_audio_times(self):
        """Set stereo_audio_times by interleaving left and right sounds"""
        ## Combine left_target_intervals and right_target_intervals
        # Turn into series
        left_target_df = pd.DataFrame.from_dict({
            'time': np.cumsum(left_target_intervals),
            'side': ['left'] * len(left_target_intervals),
            })
        right_target_df = pd.DataFrame.from_dict({
            'time': np.cumsum(right_target_intervals),
            'side': ['right'] * len(right_target_intervals),
            })

        # Concatenate them all together and resort by time
        self.stereo_audio_times = pd.concat([
            left_target_df, right_target_df], axis=0).sort_values('time')

        # Calculate the gap between sounds
        self.stereo_audio_times['gap'] = self.stereo_audio_times['time'].diff().shift(-1)
        
        # Drop the last row which has a null gap
        self.stereo_audio_times = self.stereo_audio_times.loc[
            ~self.stereo_audio_times['gap'].isnull()].copy()

        # Keep only those below the sound cycle length
        self.stereo_audio_times = self.stereo_audio_times.loc[
            self.stereo_audio_times['time'] < 10].copy()
        
        # Nothing should be null
        assert not self.stereo_audio_times.isnull().any().any() 

        # Calculate gap size in chunks
        self.stereo_audio_times['gap_chunks'] = (
            self.stereo_audio_times['gap'] * (self.fs / self.blocksize))
        self.stereo_audio_times['gap_chunks'] = (
            self.stereo_audio_times['gap_chunks'].round().astype(int))
        
        # Floor gap_chunks at 1 chunk, the minimal gap size
        # This is to avoid distortion
        self.stereo_audio_times.loc[
            self.stereo_audio_times['gap_chunks'] < 1, 'gap_chunks'] = 1

    def set_one_cycle_of_audio_frames(self):
        """Set one_cycle_of_audio_frames from stereo_audio_times"""
        # This will contain one complete pass through the audio to play
        # Each entry will be a frame of audio
        self.one_cycle_of_audio_frames = []

        # Helper function
        def append_gap(gap_chunk_size=30):
            """Append `gap_chunk_size` silent chunks to sound_block"""
            for n_blank_chunks in range(gap_chunk_size):
                self.one_cycle_of_audio_frames.append(
                    np.zeros((self.blocksize, 2), dtype='float32'))           
        
        if len(self.stereo_audio_times) == 0:
            # TODO: what happens if len(self.stereo_audio_times) == 1?
            # If no sound, then just put gaps
            append_gap(100)

        else:
            # Iterate through the rows, adding the sound and the gap
            # TODO: the gap should be shorter by the duration of the sound,
            # and simultaneous sounds should be possible
            for bdrow in self.stereo_audio_times.itertuples():
                # Append the appropriate sound
                if bdrow.side == 'left':
                    # Append a left sound
                    for frame in self.left_sound.chunks:
                        self.one_cycle_of_audio_frames.append(frame)
                        assert frame.shape == (1024, 2)

                elif bdrow.side == 'right':
                    # Append a right sound
                    for frame in self.right_target_stim.chunks:
                        self.sound_block.append(frame)
                        assert frame.shape == (1024, 2)                        
                
                else:
                    raise ValueError(
                        "unrecognized side and sound: {} {}".format(
                        bdrow.side, bdrow.sound))
                
                # Append the gap between sounds
                append_gap(bdrow.gap_chunks)        

    def generate_sound_cycle(self, left_params, right_params):
        """Define self.sound_cycle, to go through sounds
        
        params : dict
            This comes from a message on the net node.
            Possible keys:
                left_on
                right_on
                left_mean_interval
                right_mean_interval
        """
        ## Generate the stimuli to use (one per channel)
        # Presently, exactly zero or one kind of Noise can be played from
        # each speaker
        # This sets self.left_sound and self.right_sound
        self.set_left_sound(left_params)
        self.set_right_sound(right_params)
   

        ## Generate the times at which to play each Noise (one per channel)
        # This sets self.left_intervals and self.right_intervals
        self.set_left_intervals(left_params)
        self.set_right_intervals(right_params)

        # Combine the two into self.stereo_audio_times
        self.set_stereo_audio_times()
        
        
        ## Set self.cycle_of_audio_frames
        # Generate self.one_cycle_of_audio_frames, which will by cycled over
        self.set_one_cycle_of_audio_frames()
        
        # Generate a cycle that will repeat one_cycle_of_audio_frames forever
        self.cycle_of_audio_frames = itertools.cycle(
            self.one_cycle_of_audio_frames)           

    def __next__(self):
        """Return the next frame of audio"""
        return next(self.cycle_of_audio_frames)

class SoundQueuer:
    """Continuously generate frames of audio and add them to a queue. 
    
    It also handles updating the parameters of the sound to be played. 
    
    Attributes
    ----------
    sound_queue : deque
        A queue of frames of audio that is shared with jack.Client
        Frames are taken from sound_cycle and put into sound_queue as needed,
        and then they are removed from sound_queue by jack.Client
    """
    def __init__(self, sound_chooser):
        # This object must provide cycle_of_audio_frames
        self.sound_chooser = sound_chooser
        
        # Initializing queue
        # This object will keep sound_queue topped up with frames from
        # self.sound_chooser
        self.sound_queue = collections.deque()
        
        # TODO: pull in the doc for this
        self.target_qsize = 100
        
        # This is for counting frames of silence
        self.n_frames = 0

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
        qsize = len(self.sound_queue)

        # Add frames until target size reached
        while qsize < self.target_qsize:
            # Add a frame from the sound cycle
            frame = next(self.sound_chooser)
            self.sound_queue.appendleft(frame)
            
            # Keep track of how many frames played
            self.n_frames = self.n_frames + 1
            
            # Update qsize
            qsize = len(self.sound_queue)
            
    def empty_queue(self, tosize=0):
        """Empty queue"""
        while True:
            # I think it's important to keep the lock for a short period
            # (ie not throughout the emptying)
            # in case the `process` function needs it to play sounds
            # (though if this does happen, there will be an artefact because
            # we just skipped over a bunch of frames)
            try:
                data = sound_queue.pop()
            except IndexError:
                break
            
            # Stop if we're at or below the target size
            qsize = len(sound_queue)
            if qsize < tosize:
                break
        
        qsize = len(sound_queue)

class DummySoundQueue(object):
    """Dummy sound queue for testing. Always empty"""
    def __init__(self):
        pass
    
    def empty(self):
        return True

class DummySoundQueuer(object):
    """Dummy sound queuer for testing. Always empty"""
    def __init__(self):
        self.sound_queue = DummySoundQueue()
    
    def append_sound_to_queue_as_needed(self):
        pass

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
    def __init__(self, sound_queue, name='jack_client', verbose=True):
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
        self.sound_queue = sound_queue
        self.verbose = verbose
        
        # Keep track of time of last warning
        self.dt_last_warning = None
        
        
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
            data = self.sound_queue.pop()
        except IndexError:
            # The queue is empty
            # Play zeros and set the flag
            queue_is_empty = True
            data = np.zeros((self.client.blocksize, 2), dtype='float32')
        
        # Warn if needed
        dt_now = datetime.datetime.now()
        if (self.dt_last_warning is None or 
                dt_now > self.dt_last_warning + datetime.timedelta(seconds=1)):
            self.dt_last_warning = dt_now
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

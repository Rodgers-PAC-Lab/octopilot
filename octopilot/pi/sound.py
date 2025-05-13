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

## Helper function for attenuation
def apply_attenuation(sig, attenuation, sample_rate):
    ## Apply the attenuation
    fft = np.fft.fft(sig)
    fft_freqs = np.fft.fftfreq(len(sig)) * sample_rate

    # Remove negative frequencies
    # This assertion seems to be exactly valid, whereas the alternative calculation
    # of adding sample_rate (modulo arithmetic) is numerically slightly off
    # So this is probably how the symmetry is supposed to work
    # fft_freqs[0] is 0, and fft_freqs[len(fft_freqs) // 2] is -(sample_rate / 2)
    assert (
        fft_freqs[1:len(fft_freqs) // 2] == 
        -fft_freqs[len(fft_freqs) // 2 + 1:][::-1]
        ).all()

    # However this is not numerically exact for some reason
    assert np.allclose(
        fft[1:len(fft_freqs) // 2],
        np.conjugate(fft[len(fft_freqs) // 2 + 1:][::-1])
        )

    # Let's just use the first half and then make it exactly symmetric
    fft_half = fft[:len(fft_freqs) // 2]
    fft_freqs_half = fft_freqs[:len(fft_freqs) // 2]

    # interpolate
    assert attenuation.index.values.min() <= np.min(fft_freqs_half)
    assert attenuation.index.values.max() > np.max(fft_freqs_half)
    attenuation_interpolated = np.interp(
        fft_freqs_half, attenuation.index.values, attenuation.values)

    # apply interpolated attenuation
    fft_half_corrected = fft_half * 10 ** (-attenuation_interpolated / 20)

    # reconstruct the rest of the fft
    # Not sure how to handle the point in the middle, so just leave it as it 
    # was originally, it does not seem to be equal to the DC point
    fft_corrected = np.concatenate([
        fft_half_corrected, 
        [fft[len(fft_freqs) // 2]],
        np.conjugate(fft_half_corrected)[1:][::-1]
        ])

    # Invert
    corrected_signal = np.real(np.fft.ifft(fft_corrected))
    
    return corrected_signal
    

## Classes for each type of audio
class Noise:
    """Class to define bandpass filtered white noise."""
    def __init__(self, blocksize=1024, fs=192000, duration=0.01, amplitude=0.01, channel=None, 
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
            for n_column in range(self.table.shape[1]):
                self.table[:, n_column] = apply_attenuation(
                    self.table[:, n_column], self.attenuation, self.fs)
        
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

class SoundGenerator_IntermittentBursts(object):
    """Creates the frames of audio to play, given acoustic parameters.
    
    Upstream objects should decide the parameters of the sounds to play
    (e.g., center frequency, repetition rate, etc). This object uses those
    parameters to generate actual audio samples to play on left and right
    channels. A downstream `SoundQueuer` object will pull frames of audio 
    from this object using its `__next__` method. 
    
    Currently, this is implemented internally using an itertools.cycle object.
    This allows us to generate a fixed duration of audio once, but to loop
    through it forever. 
    
    This object will only generate audio that is a sequence of intermittent
    bursts of bandpass-filtered white noise (the `Noise` object) separated
    by gaps of silence. If other types of audio are desired, probably we
    need to create a new `SoundGenerator`, but right now I'm not sure what
    that would be.
    
    Methods
    -------
    set_audio_parameters : Use this to specify the acoustic and timing
        parameters of the sounds to generate.
    __next__ : Use this to get the next frame of audio.
    """
    def __init__(self, blocksize, fs, report_method=None, attenuation_file=None, 
        cycle_length_seconds=10):
        """Initalize sound generator
        
        blocksize : numeric, should match jackd initialization
        fs : sample rate
        report_method : method or None
            if not None, then this method is called every time a new
            `stereo_audio_times` DataFrame is generated
        attenuation_file : path or None
            If not None, it should be a path containing equalization
            parameters that are understood by `Noise`
        cycle_length_seconds: numeric
            How many seconds long before repeating
        """
        # Store jack client parameters
        self.blocksize = blocksize
        self.fs = fs
        
        # Store report_method
        self.report_method = report_method
        
        # Equalization parameters
        self.attenuation_file = attenuation_file
        if not os.path.exists(attenuation_file):
            print(
                "error: attenuation file does not exist "
                "at {}".format(attenuation_file)
                )
            self.attenuation_file = None
        
        # How long the cycle will be in seconds
        # TODO: The actual length will always be less than this, which
        # will become significant for very low sound rates
        self.cycle_length_seconds = cycle_length_seconds
        
        # Initialize a cycle that always generates silence
        # So that this object can respond to `next` even before it knows
        # what sound to play
        self.cycle_of_audio_frames = itertools.cycle(
            [np.zeros((self.blocksize, 2))])
    
    def _make_sound(self, params, channel):
        """Used to make a Noise according to params
        
        If len(params) == 0: returns None
        Otherwise, returns a Noise with the specified params.
        
        Arguments
        ---------
        params : dict with the keys
            duration : optional, default 0.010
            log_amplitude : required
            center_freq : required
            bandwidth : optional, default 3000

            duration : float, duration of noise burst in seconds
            amplitude : float, amplitude of noise burst
            center_freq : float, center frequency in Hz
            bandwidth : float, bandwidth (not half-bandwidth) in Hz
        
        Returns : Noise
        """
        # Generate the sound
        if len(params) == 0:
            sound = None
        
        else:
            # This one can reasonably be defaulted
            duration = params.get('duration', .010)
            bandwidth = params.get('bandwidth', 3000)
            
            try:
                params['center_freq']
                params['log_amplitude']
            except KeyError:
                raise ValueError(f'received malformed params: {params}')
            
            lowpass = params['center_freq'] + bandwidth / 2
            highpass = params['center_freq'] - bandwidth / 2
            sound = Noise(
                blocksize=self.blocksize,
                fs=self.fs,
                duration=duration,
                amplitude=(10 ** params['log_amplitude']),
                channel=channel,
                lowpass=lowpass,
                highpass=highpass,
                attenuation_file=self.attenuation_file,
                )
        
        
        return sound
    
    def _make_intervals(self, params, n_intervals=100):
        """Generates sound_intervals according to params
        
        If len(params) == 0: returns np.array([])
        Otherwise, returns an array of intervals between sounds. Each
        entry in the array is drawn from the gamma distribution.
        
        Arguments
        ---------
        params : dict with the keys
            rate : float
                Rate in Hz
            temporal_log_std : float
                Standard deviation of intervals in seconds

            rate : float, rate of sounds in Hz
            temporal_std : float, standard deviation of inter-sound intervals
        
        Returns : np.array of length `n_intervals`        
        """
        # Intervals for left
        if len(params) == 0:
            intervals = np.array([])
        
        else:
            # Change of basis
            mean_interval = 1 / params['rate']
            var_interval = (10 ** params['temporal_log_std']) ** 2
            gamma_shape = (mean_interval ** 2) / var_interval
            gamma_scale = var_interval / mean_interval

            # Draw from distribution
            intervals = np.random.gamma(gamma_shape, gamma_scale, n_intervals)
        
        return intervals
    
    def _set_stereo_audio_times(self):
        """Set stereo_audio_times by interleaving left and right sounds
        
        Takes the cumsum of self.left_intervals and the cumsum of
        self.right_intervals and sorts them together. Calculates the
        gap in time between each sound (whether left or right). Keeps 
        only those sounds that are within self.cycle_length_seconds. 
        Enforces that there is always at least one chunk of silence between
        sounds.
        
        Sets self.stereo_audio_times, a DataFrame with columns
            time : time in seconds
            side : 'left' or 'right'
            gap : the length of time until the next sound
            gap_chunks : `gap` converted to an integer number of chunks
        """
        ## Combine left_intervals and right_intervals
        # Turn into series
        left_df = pd.DataFrame.from_dict({
            'time': np.cumsum(self.left_intervals),
            'side': ['left'] * len(self.left_intervals),
            })
        right_df = pd.DataFrame.from_dict({
            'time': np.cumsum(self.right_intervals),
            'side': ['right'] * len(self.right_intervals),
            })

        # Concatenate them all together and resort by time
        self.stereo_audio_times = pd.concat([
            left_df, right_df], axis=0).sort_values('time')

        # Calculate the gap between sounds
        self.stereo_audio_times['gap'] = (
            self.stereo_audio_times['time'].diff().shift(-1))
        
        # Drop the last row which has a null gap
        self.stereo_audio_times = self.stereo_audio_times.loc[
            ~self.stereo_audio_times['gap'].isnull()].copy()

        # Keep only those below the sound cycle length
        self.stereo_audio_times = self.stereo_audio_times.loc[
            self.stereo_audio_times['time'] < self.cycle_length_seconds
            ].copy()
        
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

        # Report
        if self.report_method is not None:
            self.report_method(self.stereo_audio_times)

    def _set_one_cycle_of_audio_frames(self):
        """Set one_cycle_of_audio_frames from stereo_audio_times
        
        For each row in self.stereo_audio_time, appends the sound specified
        in that row (self.left_sound or self.right_sound) followed by a
        gap of silence specified in that row.
        """
        # This will contain one complete pass through the audio to play
        # Each entry will be a frame of audio
        self.one_cycle_of_audio_frames = []

        # Helper function
        def append_gap(gap_chunk_size=30):
            """Append `gap_chunk_size` silent chunks to one_cycle_of_audio_frames"""
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
                    for frame in self.right_sound.chunks:
                        self.one_cycle_of_audio_frames.append(frame)
                        assert frame.shape == (1024, 2)                        
                
                else:
                    raise ValueError(
                        "unrecognized side and sound: {} {}".format(
                        bdrow.side, bdrow.sound))
                
                # Append the gap between sounds
                append_gap(bdrow.gap_chunks)        
        
        print('cycle')
        print(self.one_cycle_of_audio_frames)

    def set_audio_parameters(self, left_params, right_params):
        """Define self.sound_cycle, to go through sounds
        
        Call this method to set the acoustic parameters and timing
        parameters of sounds on the left and right channels.
        
        TODO: instead of harcoding left_params and right_params, accept
        a list of params.
        
        left_params and right_params : dict with keys
            See _make_sound and _make_intervals for details
            If this is empty, no sound is played
        """
        ## Generate the stimuli to use (one per channel)
        # Presently, exactly zero or one kind of Noise can be played from
        # each speaker. These will be None if len(params) == 0
        self.left_sound = self._make_sound(left_params, channel=0)
        self.right_sound = self._make_sound(right_params, channel=1)
   
        print('left')
        print(self.left_sound)
        print('right')
        print(self.right_sound)
   
        # Generate the times at which to play each Noise (one per channel)
        # These will be empty arrays if len(params) == 0
        self.left_intervals = self._make_intervals(left_params)
        self.right_intervals = self._make_intervals(right_params)

        # Combine the two into self.stereo_audio_times
        self._set_stereo_audio_times()
        
        
        ## Set self.cycle_of_audio_frames
        # Generate self.one_cycle_of_audio_frames, which will by cycled over
        self._set_one_cycle_of_audio_frames()
        
        # Generate a cycle that will repeat one_cycle_of_audio_frames forever
        self.cycle_of_audio_frames = itertools.cycle(
            self.one_cycle_of_audio_frames)           

    def __next__(self):
        """Return the next frame of audio
        
        This is the correct/only way to get output from this object.
        Generally, a SoundQueuer will call this method to get the next frame.
        """
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
    def __init__(self, sound_generator):
        # This object must provide cycle_of_audio_frames
        self.sound_generator = sound_generator
        
        # Initializing queue
        # This object will keep sound_queue topped up with frames from
        # self.sound_generator
        self.sound_queue = collections.deque()
        
        # Each block/frame is about 5 ms
        # Longer is more buffer against unexpected delays
        # Shorter is faster to empty and refill the queue
        self.target_qsize = 100        

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
            frame = next(self.sound_generator)
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
    def __init__(self, sound_queuer, pigpio_handle=None, report_method=None, 
        name='jack_client', verbose=True):
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
        
        sound_queuer : iterator 
            `next(sound_queuer)` should provide a frame of audio
        
        pigpio_handle : pigpio.pi or None
            If not None, we use this to pulse a pin whenever we receive
            a frame of non-zero audio
        
        report_method : function or None
            If not None, we call this method with information about sound
            timing whenever we receive a frame of non-zero audio
        
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
        
        # For reporting
        self.pigpio_handle = pigpio_handle
        self.report_method = report_method
        
        # Keep track of time of last warning
        self.dt_last_warning = None
        self.frame_rate_warning_already_issued = False
        
        
        ## Left/right weighting for wheel task
        self.lr_weight = 0.5
        
        
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
    
    def process(self, frames, verbose=True):
        """Write a frame of audio from self.sound_queue to self.client.outports
        
        This function is called by self.client every 5 ms or whenever new
        audio is needed.
        
        TODO: what happens if an exception occurs in this function? Is it
        ignored or does it crash the thread?
        
        Flow
        * A frame of audio is popped from self.sound_queue
        * If sound_queue is empty, a frame of zeros is generated. This should
          not happen, so a warning is printed, but not more than once per
          second.
        * If the frame is not of shape (blocksize, 2), raises ValueError
        * Frame is converted to float32
        * Each column of frame is written to the outports
        """
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
        
        
        ## This is for the wheel task only
        ## Take the left column as mono input, and apply L/R variable weighting
        # self.lr_weight == 0 : all on the left
        # self.lr_weight == 0.5 : equal
        # self.lr_weight == 1 : all on the right
        mono = data[:, 0]
        data = np.transpose([
            mono * (1 - self.lr_weight),
            mono * self.lr_weight,
            ])
        
        ## Report when a sound plays
        # Get the std of the data: a loud sound has data_std .03
        data_std = data.std()
        
        # Only report if we're playing sound
        if data_std > 1e-12:
            # Report by pulsing a pin
            if self.pigpio_handle is not None:
                # Pulse the pin
                # Use BCM 23 (board 16) = LED - C - Blue because we're not using it
                self.pigpio_handle.write(23, True)
            
            # Report by calling a function
            if self.report_method is not None:
                # Get the current time
                # lft is the only precise one, and it's at the start of the process
                # block
                # fscs is approx number of frames since then until now
                # dt is about now
                # later, using lft, fscs, and dt, we can reconstruct the approx
                # relationship between frame times and clock time
                # this will get screwed up on every xrun
                lft = self.client.last_frame_time
                fscs = self.client.frames_since_cycle_start
                dt = datetime.datetime.now().isoformat()

                # TODO: multiprocessing.queue these reports instead
                # Report
                self.report_method(
                    data=data,
                    last_frame_time=lft,
                    frames_since_cycle_start=fscs,
                    dt=dt,
                    )
        
        else:
            # Unpulse the pin
            if self.pigpio_handle is not None:
                self.pigpio_handle.write(23, False)
        
        # Write one column to each channel
        self.client.outports[0].get_array()[:] = data[:, 0]
        self.client.outports[1].get_array()[:] = data[:, 1]

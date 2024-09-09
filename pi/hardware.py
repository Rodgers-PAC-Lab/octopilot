"""Defines objects to control hardware such as nosepokes.

These objects handle low-level operations on GPIO. They should not contain
task logic. A PiController might use these objects and tell them what 
methods to call upon certain events, such as nosepokes.
"""

import time
import pigpio
import zmq
from . import sound
from ..shared import networking
from ..shared.logtools import NonRepetitiveLogger
from ..shared.misc import RepeatedTimer
import logging
import threading
import numpy as np
import datetime

class Nosepoke(object):
    """Controls a nosepoke object using pigpio.
    
    This object encapsulates all the GPIO-level logic used for interacting
    with a nosepoke. 
    
    The typical way to interact with this object is to append a method to its
    instance variable `self.handles_poke_out`. Then that method will be called
    after every poke. 
    
    Instance variables
    ------------------
    reward_armed : bool
        Whether to give a reward upon poke
    handles_poke_in, handles_poke_out, handles_reward : list
        These methods are called upon poke in, poke out, and reward, 
        respectively.
    
    Methods
    -------
    __init__
    autopoke_start : For debugging, tell it to spuriously report pokes
    autopoke_stop : Stop spurious reporting pokes
    reward : Open the reward valve
        Usually this is called automatically as a result of a poke
    poke_in : The method that pigpio calls upon poke start
        Will call all methods in `self.handles_poke_in`
        If `self.reward_armed`, will issue reward and call all methods
        in `self.handles_reward`
    poke_out : The method that pigpio calls upon poke stop
        Will call all methods in `self.hanldes_poke_out`
    start_flashing
    """
    def __init__(self, name, pig, poke_pin, poke_sense, solenoid_pin, 
        red_pin, green_pin, blue_pin):
        """Init a new Nosepoke
        
        Arguments
        ---------
        name : str
            How it refers to itself in messages. Typical piname_L etc
        pig : pigpio.pi
        poke_pin, solenoid_pin, {red|green|blue}_pin : pin numbers 0-53
        poke_sense : bool
            True if we should call the callback on a RISING_EDGE,
            False if we should call the callback on a FALLING_EDGE
            TODO: which is 901 and which is 903
        """
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.INFO)
        
        
        ## Save attributes
        self.name = name
        self.pig = pig
        self.poke_pin = poke_pin
        self.poke_sense = poke_sense
        self.solenoid_pin = solenoid_pin
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.blue_pin = blue_pin
        
        # Whether to reward
        self.reward_armed = False
        
        # Whether to autopoke
        self.rt = None
        
        
        ## Set up lists of handles to call on events
        self.handles_poke_in = []
        self.handles_poke_out = []
        self.handles_reward = []
        
        # Set up pig direction
        # TODO: use locks in these functions
        self.pig.set_mode(self.poke_pin, pigpio.INPUT)
        self.pig.set_mode(self.solenoid_pin, pigpio.OUTPUT)
        self.pig.set_mode(self.red_pin, pigpio.OUTPUT)
        self.pig.set_mode(self.green_pin, pigpio.OUTPUT)
        self.pig.set_mode(self.blue_pin, pigpio.OUTPUT)
        
        # Set up pig call backs
        if poke_sense:
            self.pig.callback(self.poke_pin, pigpio.RISING_EDGE, self.poke_in) 
        else:
            self.pig.callback(self.poke_pin, pigpio.FALLING_EDGE, self.poke_in) 
    
    def autopoke_start(self, rate=0.3, interval=0.1):
        """Create spurious pokes at a rate of `rate` per second.
        
        rate : float
            Expected rate of pokes
        interval : float
            How often the timer is called, in seconds. Higher numbers offer more 
            precision but take more processing time.
        """
        # Calculate the probability to use to achieve the rate
        prob = rate * interval
        
        # Set up a RepeatedTimer to run every `interval` seconds
        self.rt = RepeatedTimer(interval, self._autopoke, prob=prob)
    
    def autopoke_stop(self):
        if self.rt is not None:
            self.rt.stop()
    
    def _autopoke(self, prob=1):
        self.logger.debug('autopoke')
        if np.random.random() < prob:
            self.poke_in(pin=self.poke_pin, level=pigpio.HIGH, tick=0)
    
    def reward(self, duration=.050):
        """Open the solenoid valve for port to deliver reward
        *port : port number to be rewarded (1,2,3..etc.)
        *reward_value: how long the valve should be open (in seconds) [imported from task parameters sent to the pi] 
        """
        # TODO: thread this instead of sleeping
        #self.pig.write(valve_l, 1) # Opening valve
        time.sleep(duration)
        #self.pig.write(valve_l, 0) # Closing valve
        self.logger.info('reward delivered')
    
    def poke_in(self, pin, level, tick):
        # Get time right away
        dt_now = datetime.datetime.now()
        
        # Determine whether to reward
        # If so, immediately disarm
        # TODO: use lock here to prevent multiple rewards
        if self.reward_armed:
            self.reward_armed = False
            do_reward = True
        else:
            do_reward = False
        
        # Any handles associated with pokes
        # This almost always includes HardwareController.report_poke
        for handle in self.handles_poke_in:
            handle(self.name, dt_now)

        if do_reward:
            # Actually deliver the reward
            self.reward()
            
            # Any handles associated with reward
            # This almost always includes HardwareController.report_reward
            for handle in self.handles_reward:
                handle(self.name, dt_now)

        # log
        if len(self.handles_poke_in) == 0:
            self.logger.info('poke detected but nothing to do about it')
        else:
            self.logger.info(
                f'poke detected pin={pin} level={level} tick={tick}')

    def poke_out(self, pin, level, tick):
        # Handle the pokes
        for handle in self.handles_poke_out:
            handle(self.name, dt_now)        

    def start_flashing(self, led_pin, pwm_frequency=1, pwm_duty_cycle=50):
        # Writing to the LED pin such that it blinks acc to the parameters 
        self.pig.set_mode(led_pin, pigpio.OUTPUT)
        self.pig.set_PWM_frequency(led_pin, pwm_frequency)
        self.pig.set_PWM_dutycycle(led_pin, pwm_duty_cycle)


"""Functions to set up networking

In order to communicate with the GUI, we create two sockets: 
    poke_socket and json_socket
Both these sockets use different ZMQ contexts and are used in different 
parts of the code, this is why two network ports need to be used 
    * poke_socket: Used to send and receive poke-related information.
        - Sends: Poked Port, Poke Times 
        - Receives: Reward Port for each trial, Commands to Start/Stop the 
        session, Exit command to end program
    * json_socket: Used to strictly receive task parameters from the GUI 
    (so that audio parameters can be set for each trial)


The Dispatcher can send the following messages to the Agent
    start
        Start a session. This tells the Agent to expect set_trial_parameters.
    set_trial_parameters
        Sets the acoustic and reward parameters for the next trial, which
        will start immediately. 
        If the Agent does not think a session is running, it will do 
        nothign and produce an error message.
    stop
        Stop a session. This tells the Agent to stop expecting 
        set_trial_parameters
    exit
        Tells the Agent to close the process.
    are_you_alive
        TODO: tell the Agent to respond if it is alive.
        This message should only be sent while a session is running.
        If the Agent does not respond, the Dispatcher knows something 
        has gone wrong.
        If the Agent thinks a session is running but it does not receive
        periodic alive requests, it will know that the Dispatcher has 
        crashed, and eventually it will shut itself down.


The Agent can send the following messages to the Dispatcher
    hello
        The Agent has just started up and is ready to go.
    poke
        A poke has occurred
    reward
        A reward has been delivered
    sound
        A sound has been played
    alive
        This message is only sent in response to an alive request from 
        the Dispatcher. If a session is not running, the Agent will 
        log and error.
    goodbye
        This message is sent when the Agent shuts down.

Right now there is an issue if the Agent is already running and the 
Dispatcher is restarted, there is no way for the Dispatcher to know about
the existence of the Agent. However, rather than have the Agent continuously
ping the Dispatcher (which could fill up a queue and cause problems), instead
the Dispatcher should be able to stop and start the Agent process. For now
this is done manually by the user.

Messages can "build up" in the Agent's queue if the Dispatcher is not running,
and they will be delivered (I think?) once the Dispatcher starts.
I'm not sure if messages can build up in the Dispatcher's queue when the 
Agent is not running.
"""

import logging
import datetime
import threading
import numpy as np
import zmq
from ..shared.logtools import NonRepetitiveLogger

## Shared methods
def parse_params(token_l):
    """Parse `token_l` into a dict
    
    Iterates over strings in token_l, parses them as KEY=VALUE=DTYPE,
    and stores in a dict to return. Raises ValueError if unparseable.
    
    TODO: replace this with json
    
    token_l : list
        Each entry should be a str, '{KEY}={VALUE}={DTYPE}'
        where KEY is the key, VALUE is the value, and DTYPE is
        either 'int', 'float', or 'str'
    
    Returns : dict d
        d[KEY] will be VALUE of type DTYPE
    """
    # Parse each token
    params = {}
    for tok in token_l:
        # Strip
        strip_tok = tok.strip()
        split_tok = strip_tok.split('=')
        
        # Skip if empty
        if strip_tok == '':
            # This happens if the message ends with a semicolon,
            # which is fine
            continue
        
        # Error if it's not KEY=VAL=DTYP
        try:
            key, val, dtyp = split_tok
        except ValueError:
            raise ValueError('unparseable token: {}'.format(tok))
        
        # Convert value
        if dtyp == 'int':
            conv_val = int(val)
        elif dtyp == 'float':
            conv_val = float(val)
        elif dtyp == 'str':
            conv_val = val
        elif dtyp == 'bool':
            if val == 'True':
                conv_val = True
            elif val == 'False':
                conv_val = False
            else:
                raise ValueError(f'cannot convert {val} to bool')
        else:
            # Error if DTYP unrecognized
            raise ValueError('unrecognized dtyp: {}'.format(dtyp))
        
        # Store
        params[key] = conv_val
    
    return params

## Instantiated by Dispatcher
class DispatcherNetworkCommunicator(object):
    """Handles communication with the Pis"""
    def __init__(self, pi_names, zmq_port):
        """Initialize object to communicate with the Pis.
        
        Arguments
        ---------
        expected_identies : list of str
            Each entry is the identity of a Pi
            The session can't start until all expected identities connect
        zmq_port : int
            The port to be used in initializing the socket.
        
        Flow
        ----
        * Create context and socket using zmq.ROUTER
        * Bind to tcp://*{zmq_port}
        * Initialize empty self.connected_agents
        """
        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)


        # Store provided params
        # This is who we expect to connect
        self.pi_names = pi_names

        # Set of identities of all pis connected to that instance of ther GUI 
        self.connected_agents = set() 
        
        # Set up the method to call on each command
        self.command2method = {}
        
        # Set up sockets
        self.init_socket(zmq_port)
    
    def init_socket(self, zmq_port):
        """Initialize a ZMQ socket on port `zmq_port`.
        
        The ZMQ socket is a ROUTER on the desktop and a DEALER on the pi.
        """
        # Set up a lock
        # Note that ZMQ sockets cannot be shared across threads
        # The use of a lock is discouraged, but I'm not sure if it's known
        # to not work, or they just don't like it
        self.zmq_socket_lock = threading.Lock()
        
        self.context = zmq.Context()
        self.zmq_socket = self.context.socket(zmq.ROUTER)
        self.zmq_socket.bind(f"tcp://*:{zmq_port}")
    
    def check_if_all_pis_connected(self):
        """"Returns True if all pis in self.expected_identies are connected"""
        # Iterate over identies
        # Return False if any is missing
        all_connected = True
        for identity in self.pi_names:
            if identity not in self.connected_agents:
                all_connected = False
                break
        
        return all_connected
    
    def send_message_to_pi(self, msg, identity):
        """Send msg to identity"""
        # Convert to bytes
        self.logger.info(f'sending to {identity}: {msg}')
        msg_bytes = bytes(msg, 'utf-8')
        identity_bytes = bytes(identity, 'utf-8')
        
        # Use a lock to prevent multiple threads from accessing zmq_socket
        with self.zmq_socket_lock:
            self.zmq_socket.send_multipart([identity_bytes, msg_bytes])
    
    def send_message_to_all(self, msg):
        """"Send msg to all identities in self.connected_agents"""
        self.logger.info(
            f'sending message to all connected ({self.connected_agents})'
            )
        
        # Send to all
        for identity in self.connected_agents:
            self.send_message_to_pi(msg, identity)
    
        self.logger.info(f'above message was sent to {self.connected_agents}')    
    
    def send_start(self):
        self.logger.info('sending start message to all connected pis')
        self.send_message_to_all('start')
    
    def send_alive_request(self):
        #~ self.logger.info('sending are_you_alive message to all connected pis')
        self.send_message_to_all('are_you_alive')
    
    def send_trial_parameters_to_pi(self, identity, **kwargs):
        """Encode a set_trial_parameters message and send to `identity`
        
        The message will begin with "set_trial_parameters;"
        Each keyword argument will be converted into "{key}={value}={dtyp}"
        (dtyp is inferred from value)
        
        TODO: do this with json instead
        """
        msg = "set_trial_parameters;"
        for key, value in kwargs.items():
            if key == 'left_reward':
                print(f'the type of left_reward is {type(value)}')
                
            # Infer dtyp
            if hasattr(value, '__len__'):
                dtyp = 'str'
            elif isinstance(value, bool) or isinstance(value, np.bool_):
                # Note that bool is an instance of int
                dtyp = 'bool'
            elif isinstance(value, int):
                # https://stackoverflow.com/a/48940855/1676378
                dtyp = 'int'
            else:
                dtyp = 'float'
            
            # Append
            msg += f"{key}={value}={dtyp};"
        
        self.send_message_to_pi(msg, identity)
    
    def check_for_messages(self):
        """Check self.zmq_socket for messages.
        
        If a message is available: return identity, messages
        Otherwise: return None
        """
        ## Check for messages
        message_received = True
        try:
            # Without NOBLOCK, this will hang until a message is received
            # TODO: use Poller here?
            identity, message = self.zmq_socket.recv_multipart(
                flags=zmq.NOBLOCK)
        except zmq.error.Again:
            message_received = False

        # If there's no message received, there is nothing to do
        if message_received:
            self.handle_message(identity, message)
    
    def handle_message(self, identity, message):
        """Handle a message received on poke_socket
        
        In the present design, it seems that these messages are handled
        sequentially, so there is no need for a thread lock. To test,
        put a time.sleep(10) in a handling function.
        
        Arguments
        ---------
        msg : str
            A ';'-separated list of strings
            The first string is the "command"
            The remaining strings should be in the format {KEY}={VALUE}={DTYP}
            The method self.command2method[command] is called with a dict
            of arguments formed from the remaining strings.
        """        
        # Decode the message
        # TODO: in the future support bytes
        identity_str = identity.decode('utf-8')
        message_str = message.decode('utf-8')

        # Debug print identity and message
        # Squelch the sound methods which are too frequent
        # TODO: make squelch a param
        if 'data_hash' not in message_str:
            self.logger.debug(f'received from {identity}: {message}')

        
        ## Handle message
        if message_str == 'hello':
            # Special case 'hello', which is the only message handled
            # directly and exclusively by NetworkCommunicator
            # If this agent is expected and not yet connected, it will
            # be added.
            # Otherwise an error will be logged
            self.handle_hello(identity_str)
        
        elif identity_str not in self.connected_agents:
            # A non-hello message from an unconnected agent
            self.handle_message_from_unconnected_agent(identity_str)
 
        else:
            # Handle a non-hello message from a connected agent
            # Split on semicolon
            tokens = message_str.strip().split(';')
            
            # The command is the first token
            # This will always run, but command could be ''
            command = tokens[0]
            
            # Get the params
            # This will always run, but could return {}
            msg_params = parse_params(tokens[1:])
            
            # Insert identity into msg_params
            msg_params['identity'] = identity_str
            
            # Find associated method
            meth = None
            try:
                meth = self.command2method[command]
            except KeyError:
                self.logger.error(
                    f'unrecognized command: {command}. ' +
                    'I only recognize: ' +
                    ' '.join(self.command2method.keys())
                    )
            
            # Call the method
            if meth is not None:
                # Squelch the sound methods which are too frequent
                # TODO: make squelch a param
                if 'data_hash' not in msg_params:
                    self.logger.debug(
                        f'calling method {meth} with params {msg_params}')
                meth(**msg_params)

    def handle_hello(self, identity_str):
        """Handle `hello` from `identity_str`
        
        If it is not connected:
            If it is expected: add it
            If it is not expected: error
        If it is connected: error
        """
        if identity_str not in self.connected_agents:
            # A new Agent has made contact
            if identity_str in self.pi_names:
                # It was expected, add it
                self.logger.info(
                    f'received hello from {identity_str}, '
                    'adding to connected_agents')
                self.connected_agents.add(identity_str)
            else:
                # It was not expected, error
                self.logger.error(
                    f'received hello from {identity_str}, '
                    f'ignore because I only expect to connect to: '
                    ' '.join(self.pi_names))
        
        else:
            # This Agent has already made contact
            self.logger.error(
                f'received hello from {identity_str}, '
                f'but we were already connected')
            
            # TODO: call received_double_hello here        

    def handle_message_from_unconnected_agent(self, identity_str):
        """Handle non-hello message from unconnected agent
        
        If it is from an expected agent: error
        Otherwise: error
        """
        if identity_str in self.pi_names:
            # This is a known agent, but it's not connected
            # TODO: call received_message_without_hello here
            self.logger.error(
                'received message from known but unconnected agent '
                f'{identity_str}'
                )
        
        else:
            # This is an unknown agent
            self.logger.error(
                'received message from unknown agent '
                f'{identity_str}'
                )        

    def remove_identity_from_connected(self, identity):
        if identity not in self.connected_agents:
            self.logger.error(
                f'{identity} said goodbye but it was not connected')
        else:
            self.connected_agents.remove(identity)

## This class is instantiated by HardwareController
class PiNetworkCommunicator(object):
    """Handles communication with GUI
    
    This object sets up sockets to communicate with GUI, receives messages
    from the GUI, and can be set to call specific methods upon receiving
    specific messages.
    
    Generally, this object is instantiated by and contained by a 
    HardwareController, which provides its own methods to be called upon
    receiving specific messages.
    
    This object should focus on network communication (sockets etc) and
    parsing messages, not on task-specific logic. 
    
    Methods
    -------
    __init__ : Calls set_up_poke_socket and also creates a Poller and registers
        sockets with it
    set_up_poke_socket : Creates sockets and connects to the GUI
    """
    def __init__(self, identity, gui_ip, zmq_port):
        """Init a new NetworkCommunicator
        
        This object will communicate with the GUI using a DEALER socket called
        poke_socket and a SUB socket called json_socket. The SUB socket
        can only receive information. The DEALER socket can only send 
        information (??)
        
        Arguments
        ---------
        identity : str
        gui_ip : str
            IP address of GUI
        zmq_port : int
        
        Flow
        ----
        * Set up self.poke_socket. This also sends a message to the GUI.
        * Set up self.poller and register the scokets.
        """
        ## Store required arguments
        self.gui_ip = gui_ip
        self.zmq_port = zmq_port
        self.identity = identity

        ## Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)
        
        ## Set up the method to call on each command
        self.command2method = {}

        ## Set up sockets
        self.socket_is_open = False
        self.init_socket()
        
        # Creating a poller object for both sockets that will be used to 
        # continuously check for incoming messages
        self.poller = zmq.Poller()
        self.poller.register(self.poke_socket, zmq.POLLIN)
        
        ## Bonsai init
        self.bonsai_ip = "192.168.0.213"
        self.bonsai_port = 5557
        
        self.init_bonsai_socket()
        
        # Create a second poller object 
        self.bonsai_poller = zmq.Poller()
        self.bonsai_poller.register(self.bonsai_socket, zmq.POLLIN)
        
        # Making a state variable to keep track of information on bonsai socket
        self.bonsai_state = None
        self.prev_bonsai_state = None
    
    def init_socket(self):
        """Create `self.poke_socket` and connect to GUI
        
        Flow
        * Create self.poke_context and self.poke_socket (a zmq.DEALER).
          Identity of self.poke_socket is self.identity
          The socket's "identity" will be reported to the ROUTER
        * Connect to the router IP by combining GUI IP with poke_port
        * Send our identity to the GUI, which also adds this pi to the GUI's
          list of known identities.
        
        This doesn't appear to be blocking: even if there is nothing running
        on the GUI computer, this function will successfully complete.
        """
        ## Create socket
        # Creating a DEALER socket for communication regarding poke and poke times
        self.poke_context = zmq.Context()
        self.poke_socket = self.poke_context.socket(zmq.DEALER)

        # Setting the identity of the socket in bytes
        self.poke_socket.identity = bytes(f"{self.identity}", "utf-8") 

        # Set LINGER to 100 ms
        # During context.term(), this is how long it will wait to send 
        # remaining messages before closing. The default value is to wait
        # forever, which means that whenever the server is closed first,
        # then closing the Pi will hang.
        # https://github.com/zeromq/pyzmq/issues/102
        self.poke_socket.setsockopt(zmq.LINGER, 100)


        ## Connect to the server
        # Connecting to the GUI IP address stored in params
        self.router_ip = f"tcp://{self.gui_ip}:{self.zmq_port}"
        self.poke_socket.connect(self.router_ip) 

        # Print acknowledgment
        self.socket_is_open = True
        print(f"Connected to router at {self.router_ip}")  

    def init_bonsai_socket(self):
        """Create `self.bonsai_socket` and connect to Bonsai PC

        """
        ## Create socket
        # Creating a SUB socket for communication regarding poke and poke times
        self.bonsai_context = zmq.Context()
        self.bonsai_socket = self.bonsai_context.socket(zmq.SUB)


        ## Connect to the server
        # Connecting to the GUI IP address stored in params
        self.bonsai_tcp = f"tcp://{self.bonsai_ip}:{self.bonsai_port}"
        self.bonsai_socket.connect(self.bonsai_tcp) 
        
        # Subscribe to all incomign messages from  bonsai
        self.bonsai_socket.subscribe(b"")

        # Print acknowledgment
        print(f"Connected to Bonsai at {self.bonsai_tcp}")  

    def send_hello(self):
        # Send the identity of the Raspberry Pi to the server
        self.logger.debug('sending hello')
        self.poke_socket.send_string(f"hello")

    def check_socket(self):
        # Get time
        dt_now = datetime.datetime.now().isoformat()

        # Wait for events on registered sockets. 
        # Currently polls every 100ms to check for messages 
        socks = dict(self.poller.poll(100))

        # Check for incoming messages on poke_socket
        if self.poke_socket in socks and socks[self.poke_socket] == zmq.POLLIN:
            # Waiting to receive message strings that control the main loop
            # Is this blocking?
            # I think the 'if' is only satisfied if there is something to
            # receive, so it doesn't matter if it's blocking
            msg = self.poke_socket.recv_string()  
            
            # Receive message
            self.logger.debug(
                f'{dt_now} - Received message {msg} on poke socket')
    
            # Handle message
            self.handle_message(msg)

    def check_bonsai_socket(self):
        # Get time
        dt_now = datetime.datetime.now().isoformat()

        # Wait for events on registered sockets.
        socks2 = dict(self.bonsai_poller.poll(100))

        # Check for incoming messages on bonsai_socket and log states 
        if self.bonsai_socket in socks2 and socks2[self.bonsai_socket] == zmq.POLLIN:
            msg2 = self.bonsai_socket.recv_string()
            self.bonsai_state = msg2
            #print("Checking for bonsai messages")
            
            # Log only if the message has changed
            if self.bonsai_state == 'True' and self.prev_bonsai_state == 'False' or None:
                self.logger.debug(
                    f'{dt_now} - Received message {self.bonsai_state} on bonsai socket')
                self.prev_bonsai_state = self.bonsai_state
            if self.bonsai_state == 'False' and self.prev_bonsai_state == 'True' or None:
                self.logger.debug(
                    f'{dt_now} - Received message {self.bonsai_state} on bonsai socket')
                self.prev_bonsai_state = self.bonsai_state


            # Handle message
            #self.handle_message(msg)
    
    def handle_message(self, msg):
        """Handle a message received on poke_socket
        
        Arguments
        ---------
        msg : str
            A ';'-separated list of strings
            The first string is the "command"
            The remaining strings should be in the format {KEY}={VALUE}={DTYP}
            The method self.command2method[command] is called with a dict
            of arguments formed from the remaining strings.
        """
        # Log
        self.logger.debug(f'received message: {msg}')
        
        # Split on semicolon
        tokens = msg.strip().split(';')
        
        # The command is the first token
        # This will always run, but command could be ''
        command = tokens[0]
        
        # Get the params
        # This will always run, but could return {}
        msg_params = parse_params(tokens[1:])
        
        # Find associated method
        meth = None
        try:
            meth = self.command2method[command]
        except KeyError:
            self.logger.error(
                f'unrecognized command: {command}. '
                f'I only recognize: {list(self.command2method.keys())}'
                )
        
        # Call the method
        if meth is not None:
            self.logger.debug(f'calling method {meth} with params {msg_params}')
            meth(**msg_params)

    def send_goodbye(self):
        """Send goodbye message to GUI
        
        """
        self.logger.info('sending goodbye')
        self.poke_socket.send_string(f"goodbye") 
    
    def send_alive(self):
        """Send alive message to Dispatcher"""
        if self.socket_is_open:
            #~ self.logger.debug('sending alive')
            self.poke_socket.send_string('alive')
        else:
            self.logger.error('alive requested but socket is closed')
    
    def close(self):
        """Close all sockets and contexts"""
        # Prevent sending
        self.socket_is_open = False
        
        # Close
        self.poke_socket.close()
        
        # Gets stuck here if the GUI was closed and more messages were sent
        self.poke_context.term()

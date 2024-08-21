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
"""

## INITIALIZING NETWORK CONNECTION
import zmq


def set_up_poke_socket(params):
    """Connect to poke_socket and json_socket
    

    """
    ## Create socket
    # Creating a DEALER socket for communication regarding poke and poke times
    poke_context = zmq.Context()
    poke_socket = poke_context.socket(zmq.DEALER)

    # Setting the identity of the socket in bytes
    poke_socket.identity = bytes(f"{pi_identity}", "utf-8") 


    ## Connect to the server
    # Connecting to the GUI IP address stored in params
    router_ip = "tcp://" + f"{params['gui_ip']}" + f"{params['poke_port']}" 
    poke_socket.connect(router_ip) 

    # Send the identity of the Raspberry Pi to the server
    poke_socket.send_string(f"{params['identity']}") 

    # Print acknowledgment
    print(f"Connected to router at {router_ip}")  

    return poke_socket


def set_up_json_socket(params):
    ## Create socket
    # Creating a SUB socket and socket for receiving task parameters 
    # (stored in json files)
    json_context = zmq.Context()
    json_socket = json_context.socket(zmq.SUB)

    
    ## Connect
    router_ip2 = "tcp://" + f"{params['gui_ip']}" + f"{params['config_port']}"
    json_socket.connect(router_ip2) 

    # Subscribe to all incoming messages containing task parameters 
    json_socket.subscribe(b"")

    # Print acknowledgment
    print(f"Connected to router at {router_ip2}")
    
    return json_socket
    
    
    

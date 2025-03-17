"""Functions to communicate with watchtower to control video

"""
import json
import urllib3
import requests

def watchtower_setup(watchtowerurl, logger):
    """Log in to watchtower and get api token.
    
    Returns: watchtower_connection_up, apit
        watchtower_connection_up : bool
            True if connection worked
            False if it timed out
        
        apit : api token
            None if it timed out
    """
    # Disable the "insecure requests" warning
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # login and obtain API token
    username = 'mouse'
    password = 'whitemattertest'
    
    # Wrap all requests in case of timeout
    watchtower_connection_up = True
    try:
        # Try to log in
        r = requests.post(
            watchtowerurl + '/api/login', 
            data={'username': username, 'password': password}, 
            verify=False,
            timeout=1,
            )
    except (requests.ConnectTimeout, requests.exceptions.ConnectionError):
        # If no connection available, log error and set
        # watchtower_connection_up to False to disable further
        # attemps in this session
        logger.debug(
            "error: cannot connect to watchtower at {}".format(
            watchtowerurl))
        watchtower_connection_up = False
    
    # Extract the token
    if watchtower_connection_up:
        j = json.loads(r.text)
        apit = j['apitoken']
    else:
        apit = None
    
    return watchtower_connection_up, apit

def watchtower_start_save(watchtowerurl, apit, camera_name, logger):
    """Tell watchtower to start saving.
    
    Returns watchtower_connection_up
    """
    # Until proven False
    watchtower_connection_up = True
    
    # Wrap all requests
    try:
        response = requests.post(
            watchtowerurl+'/api/cameras/action', 
            data={
                'SerialGroup[]': [camera_name], 
                'Action': 'RECORDGROUP', 
                'apitoken': apit,
            }, 
            timeout=1,            
            verify=False)
        logger.debug('video start save command sent')
    
    except requests.ConnectTimeout:
        # If timeout, log the error and disable further
        # attempts to communicate during this session
        logger.debug(  
            'error: cannot connect to watchtowerurl at '
            '{} to start save'.format(
            watchtowerurl))
        response = None
        watchtower_connection_up = False
    
    # This logs an error if we were able to communicate with
    # watchtower, but the response was an error
    if response is not None and not response.ok:
        logger.debug(
            'error: response after start save command: ' +
            str(response.text))
    
    return watchtower_connection_up
    
def watchtower_stop_save(watchtowerurl, apit, camera_name, logger):
    """Tell watchtower to stop saving.
    
    Returns watchtower_connection_up
    """  
    # Until proven False
    watchtower_connection_up = True
    
    # Wrap all requests
    try:
        response = requests.post(
            watchtowerurl+'/api/cameras/action', 
            data={
                'SerialGroup[]': [camera_name], 
                'Action': 'STOPRECORDGROUP', 
                'apitoken': apit,
            }, 
            verify=False,
            timeout=1,
            )
        logger.debug('video stop save command sent')
    
    except requests.ConnectTimeout:
        # If timeout, log the error and disable further
        # attempts to communicate during this session
        logger.debug(  
            'error: cannot connect to watchtowerurl at '
            '{} to stop save'.format(
            watchtowerurl))
        response = None
        watchtower_connection_up = False                        

    # This logs an error if we were able to communicate with
    # watchtower, but the response was an error
    if response is not None and not response.ok:
        logger.debug(
            'error: response after stop save command: ' +
            str(response.text))      
    
    return watchtower_connection_up
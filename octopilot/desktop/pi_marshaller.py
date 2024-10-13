import os
import time
import subprocess
import threading
import logging
from ..shared.logtools import NonRepetitiveLogger

class PiMarshaller(object):
    """Connects to each Pi over SSH and starts the Agent.
    
    """
    def __init__(
        self, agent_names, ip_addresses, sandbox_path,
        shell_script='/home/pi/dev/octopilot/octopilot/pi/start_cli.sh',
        ):
        """Init a new PiMarshaller to connect to each in `ip_addresses`.
        
        Arguments
        ---------
        agent_names : list of str
            Each entry should be the name of an Agent
        ip_addresses : list of str
            Each entry should be an IP address of a Pi
            This list should be the same length and correspond one-to-one
            with `agent_names`.
        sandbox_path : path
            The output files from each SSH will be stored here
        shell_script : path on Pi
            This is the script that is started by SSH
        """
        # Init logger
        self.logger = NonRepetitiveLogger("test")
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.setLevel(logging.DEBUG)
        
        # Save arguments
        self.agent_names = agent_names
        self.ip_addresses = ip_addresses
        self.shell_script = shell_script
        self.sandbox_path = sandbox_path
    
    def start(self):
        """Open an ssh connection each Agent in self.agent_names
        
        TODO: provide a handle that is called whenever the ssh proc closes,
        especially unexpectedly.
        
        Flow
        * For each agent:
            * A Popen is used to maintain the ssh connection in the background
            * That ssh connection is used to run `start_cli.sh` on the Pi,
              which starts the Agent
            * A thread is used to collect data from each of stdout and stderr
            * That data is also written to a logger, prepended with agent name
        """
        # This function is used only as a thread target
        def capture(buff, buff_name, agent_name, logger, output_filename):
            """Thread target: read from `buff` and write out
            
            Read lines from `buff`. Write them to `logger` and to
            `output_filename`. This is blocking so it has to happen in 
            a thread. I think these operations are all thread-safe, even
            the logger.
            
            buff : a process's stdout or stderr
                Lines of text will be read from this
            buff_name : str, like 'stdout' or 'stderr'
                Prepended to the line in the log
            agent_name : str
                Prepended to the line in the log
            logger : Logger
                Lines written to here, with agent_name and buff_name prepended
            output_filename: path
                Lines written to here
            """
            # Open output filename
            with open(output_filename, 'w') as fi:
                # Iterate through the lines in buff, with '' indicating
                # that buff has closed
                for line in iter(buff.readline, ''):
                    # Log the line
                    # TODO: make the loglevel configurable
                    logger.debug(
                        f'  from {agent_name} {buff_name}: {line.strip()}')
                    
                    # Write the line to the file
                    fi.write(line)  
        
        # Iterate over agents
        self.agent2proc = {}
        self.agent2thread_stdout = {}
        self.agent2thread_stderr = {}
        for agent_name, ip_address in zip(self.agent_names, self.ip_addresses):
            self.logger.info(
                f'starting ssh proc to {agent_name} at {ip_address}')
            # Create the ssh process
            # https://stackoverflow.com/questions/76665310/python-run-subprocess-popen-with-timeout-and-get-stdout-at-runtime
            # -tt is used to make it interactive, and to ensure it closes
            #    the remote process when the ssh ends.
            # PIPE is used to collect data in threads
            # text, universal_newlines ensures we get text back
            proc = subprocess.Popen(
                ['ssh', '-tt', '-o', 'ConnectTimeout=2', f'pi@{ip_address}', 
                'bash', '-i', self.shell_script], 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True,
                )
            
            time.sleep(.1)
            proc.poll()
            if proc.returncode is not None:
                print(f'error, cannot start proc to {agent_name}')
                continue
            
            # Start threads to capture output
            output_filename = os.path.join(
                self.sandbox_path, f'{agent_name}_stdout.output')
            thread_stdout = threading.Thread(
                target=capture, 
                kwargs={
                    'buff': proc.stdout, 
                    'buff_name': 'stdout',
                    'agent_name': agent_name,
                    'logger': self.logger,
                    'output_filename': output_filename,
                    },
                )

            output_filename = os.path.join(
                self.sandbox_path, f'{agent_name}_stderr.output')
            thread_stderr = threading.Thread(
                target=capture, 
                kwargs={
                    'buff': proc.stderr, 
                    'buff_name': 'stderr',
                    'agent_name': agent_name,
                    'logger': self.logger,
                    'output_filename': output_filename,
                    },
                )
            
            # Start
            thread_stdout.start()
            thread_stderr.start()      
            
            # Store
            self.agent2proc[agent_name] = proc
            self.agent2thread_stdout[agent_name] = thread_stdout
            self.agent2thread_stderr[agent_name] = thread_stderr
    
    def stop(self):
        """Close ssh proc to agent"""
        # Wait until it's had time to shut down naturally because we probably
        # just sent the stop command
        time.sleep(1)
        
        # Iterate over agents
        for agent, proc in self.agent2proc.items():
            # Poll to see if done
            # TODO: do this until returncode
            proc.poll()
            
            # Kill if needed
            if proc.returncode is None:
                self.logger.warning(
                    f"ssh proc to {agent} didn't end naturally, killing")
                
                # Kill
                proc.terminate()
                
                # Time to kill
                time.sleep(.5)
            
            # Log
            self.logger.info(
                f'proc_ssh_to_agent returncode: {proc.returncode}')


## SAVING TERMINAL INFO
"""
This function was implemented to save logs for test sessions or sessions that weren't saved due to crashes. 
It logs all the terminal information being printed on the GUI side of the code and saves it to a txt file. 
This implementation hasn't been done for the terminal information on the pi side. (currently does not use the logging library - maybe can be included later)
"""
# Function to print to terminal and store log files as txt
def print_out(*args, **kwargs):
    global current_task, current_time
    
    # Naming the txt file according to the current task and time and saving it to a log folder 
    output_filename = params['save_directory'] + f"/terminal_logs/{current_task}_{current_time}.txt"
    
    # Joining the arguments into a single string
    statement = " ".join(map(str, args))
    
    # Print the statement to the console
    print(statement, **kwargs)
    
    # Write the statement to the file
    with open(output_filename, 'a') as outputFile:
            outputFile.write(statement + "\n")
import os
import pandas as pd
import numpy and np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Listing the mice we want to plot
mouse_names = ["earthworm176", "earthworm177", "flamingo178", "flamingo179"]

# Defining log directory location (Change based on where you're saving logs)
data_directory = "/home/mouse/octopilot/behaviorbox_logs"
start_date = "2024-12-04"  # Date from which all columns and rows were labelled 

def load_sessions_from_date(data_directory, mouse_name, start_date):
    """Function that goes through all the subdirectories in the main behavior log
    directory and loads pokes.csv and trials.csv files to make data frames to use 
    with pandas.
    """
    trials_data_frames = []
    pokes_data_frames = []
    session_dates = []
    
    # Changing the start date string to a date time object 
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
    
    # Checking if the name of each mouse name found in the root directory under the behavior logs folder
    for root, dirs, files in os.walk(data_directory):
        if mouse_name in root:
            relative_path = os.path.relpath(root, data_directory)
            path_parts = relative_path.split(os.sep)
            
            if len(path_parts) >= 3:
                session_folder = path_parts[2]
                
                # Getting datetime from the session folder name and making it a datetime object
                try:
                    date_part = session_folder.split('_')[0]
                    session_date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                    
                    # If the session is after the specified start date, then append it to the list of dates to be plotted 
                    if session_date_obj >= start_date_obj:
                        session_dates.append(session_date_obj)
                        
                        # Making a big dataframe of from all pokes.csv files under listed dates
                        if "pokes.csv" in files:
                            file_path = os.path.join(root, "pokes.csv")
                            try:
                                df = pd.read_csv(file_path)
                                
                                # Check if there is only one row (the header) in the CSV file
                                if len(df) <= 1:
                                    print(f"Skipping {file_path} - contains only header or no data")
                                    continue  # Skip this file if it only has a header
                                
                                # Add a column with the date of session 
                                df['session_date'] = session_date_obj
                                
                                # Append the DataFrame to the list for full data
                                pokes_data_frames.append(df)
                            except Exception as e:
                                print(f"Error reading {file_path}: {e}")

                        # Making a big dataframe of from all trials.csv files under listed dates
                        if "trials.csv" in files:
                            file_path = os.path.join(root, "trials.csv")
                            try:
                                df = pd.read_csv(file_path)
                                
                                # Skip file if it only has a header row
                                if len(df) <= 1:
                                    print(f"Skipping {file_path} - contains only header or no data")
                                    continue
                                
                                df['session_date'] = session_date_obj
                                trials_data_frames.append(df)
                            except Exception as e:
                                print(f"Error reading {file_path}: {e}")

                except ValueError:
                    print(f"Could not parse date from folder name: {session_folder}")

    # Exclude empty or all-NA columns before concatenation
    trials_data_frames = [df.dropna(axis=1, how='all') for df in trials_data_frames if not df.empty]
    pokes_data_frames = [df.dropna(axis=1, how='all') for df in pokes_data_frames if not df.empty]

    trials_full_data = pd.concat(trials_data_frames, ignore_index=True) if trials_data_frames else pd.DataFrame()
    pokes_full_data = pd.concat(pokes_data_frames, ignore_index=True) if pokes_data_frames else pd.DataFrame()

    return trials_full_data, pokes_full_data, session_dates

def plot_combined(data_directory, mouse_names, start_date):
    """Function to create a shared figure with common x-axis and legend for each mouse across three plots.
       Adds an overall daily average line in the first subplot.
    """
    fig, axs = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    
    # Initialize a dictionary to store daily averages across sessions for overall trace in plot_n_ports_poked
    overall_daily_avg = {}

    # Initialize a list to store handles and labels for the combined legend
    handles = []
    labels = []
    
    for mouse_name in mouse_names:
        # Load the data for each mouse
        trials_data, pokes_data, session_dates = load_sessions_from_date(data_directory, mouse_name, start_date)
        
        # Plot n_ports_poked and add to handles for the combined legend
        # Plot n_ports_poked and add to handles for the combined legend
        handles_0, labels_0 = plot_n_ports_poked(data_directory, mouse_name, start_date, axs[0], label=mouse_name, overall_daily_avg=overall_daily_avg)
        handles_1, labels_1 = plot_poke_count(pokes_data, session_dates, axs[1], label=mouse_name)
        handles_2, labels_2 = plot_trial_count(trials_data, session_dates, axs[2], label=mouse_name)
        
        # Collect handles and labels for the first plot's legend
        handles += handles_0
        labels += labels_0

    # Calculate the overall daily average across all traces and plot as a dotted line on the first subplot
    if overall_daily_avg:
        avg_dates = sorted(overall_daily_avg.keys())
        avg_values = [sum(vals) / len(vals) for vals in [overall_daily_avg[date] for date in avg_dates]]
        axs[0].plot(avg_dates, avg_values, marker='o', linestyle='--', color='black', label='Overall Daily Average')

    # Add a common legend outside the subplots
    fig.legend(handles, labels, loc='upper center', ncol=len(mouse_names), fontsize=10, bbox_to_anchor=(0.5, 0.96))
    
    # Adding common labels and formatting
    fig.text(0.5, 0.04, 'Date (MM-DD)', ha='center', fontsize=11)
    for ax in axs:
        ax.grid(True)  # Add a grid to each subplot
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.tick_params(axis='x', rotation=45)
    
    # Displaying figure and adjusting position of the subplots
    fig.suptitle("Behavior Performance (Sandwich, Salad)", fontsize=14)
    plt.subplots_adjust(hspace=0.3, top=0.9, bottom=0.1)
    plt.show()

def plot_poke_count(pokes_data, session_dates, ax, label):
    """Plot for total pokes over a session"""
    if pokes_data is not None:
        # Grouping pokes in the full dataframe by the session date 
        pokes_count = pokes_data.groupby('session_date').size().reset_index(name='pokes_count')
        pokes_count = pokes_count[pokes_count['session_date'].isin(session_dates)]

        if not pokes_count.empty:
            #Plotting a trace of the pokes
            line, = ax.plot(pokes_count['session_date'], pokes_count['pokes_count'],
                marker='o', linestyle='-', label=label)
            ax.set_ylabel('Number of Pokes')
            ax.set_title('Poke Count Across Days')
            ax.grid()
            return [line], [label]
    return [], []

def plot_trial_count(trials_data, session_dates, ax, label):
    """Plot for total trials over a session"""
    if trials_data is not None:
        # Grouping trials in the full dataframe by the session date 
        trials_count = trials_data.groupby('session_date').size().reset_index(name='trials_count')
        trials_count = trials_count[trials_count['session_date'].isin(session_dates)]

        if not trials_count.empty:
            # Plotting a trace of the trials
            line, = ax.plot(trials_count['session_date'], trials_count['trials_count'],
                marker='o', linestyle='-', label=label)
            ax.set_ylabel('Number of Trials')
            ax.set_title('Trial Count Across Days')
            ax.grid()
            return [line], [label]
    return [], []

def plot_n_ports_poked(data_directory, mouse_name, start_date, ax, label, overall_daily_avg=None):
    """Function to calculate the mean number of pokes per trial for every session.
    The flow of the function is as follows:
    - Reads both the pokes.csv and trials.csv files.
    - Takes the trial_numbers and goal_ports from trials.csv and merges it with 
    pokes.csv to make merged_data which has the same number of rows as pokes.csv
    - Makes a new column for previous goal ports
    - Counts the unique ports poked for the first trial
    - For every subsequent trial it checks the goal_port of previous trial number and 
    fills this value in the new column 
    - Counts unique ports poked for each trial then excludes pokes on at the previous goal port
    - Groups these pokes by trial number and takes the mean over all trials for a session
    - Appends this value to a list of n_ports_poked for different dates
    """    
    average_data = []
    encountered_dates = set()  # Track all dates with any data found for this mouse
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")

    for root, dirs, files in os.walk(data_directory):
        if mouse_name in root:
            folder_name = os.path.basename(root)
            try:
                date_part = folder_name.split('_')[0]
                session_date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                
                if session_date_obj >= start_date_obj:
                    pokes_file_path = os.path.join(root, "pokes.csv")
                    trials_file_path = os.path.join(root, "trials.csv")

                    if os.path.exists(pokes_file_path) and os.path.exists(trials_file_path):
                        # Load data and skip files if they have fewer than two rows
                        pokes_data = pd.read_csv(pokes_file_path)
                        trials_data = pd.read_csv(trials_file_path)
                        if len(pokes_data) < 2 or len(trials_data) < 2:
                            continue  # Skip this session if not enough data

                        # Track that we encountered this session date
                        encountered_dates.add(session_date_obj)

                        # Merge data to analyze unique ports poked
                        merged_data = pd.merge(pokes_data, trials_data[['trial_number', 'goal_port']],
                                               left_on='trial_number', right_on='trial_number', how='left')

                        merged_data['previous_goal_port'] = None
                        for i in range(len(merged_data)):
                            if i == 0:
                                n_ports_poked = merged_data['poked_port'].nunique()
                            else:
                                previous_goal_port = merged_data.iloc[i - 1]['goal_port']
                                merged_data.at[i, 'previous_goal_port'] = previous_goal_port
                                current_trial_poked_ports = merged_data[merged_data['trial_number'] == merged_data.iloc[i]['trial_number']]
                                n_ports_poked = current_trial_poked_ports[current_trial_poked_ports['poked_port'] != previous_goal_port]['poked_port'].nunique()

                            trials_data.loc[trials_data['trial_number'] == merged_data.iloc[i]['trial_number'], 'n_ports_poked'] = n_ports_poked

                        # Calculate the average number of pokes per trial for this session by dropping npp 0 values for last trial
                        valid_pokes = trials_data['n_ports_poked'][trials_data['n_ports_poked'] > 0]
                        if len(valid_pokes) > 0:
                            average_pokes_per_trial = valid_pokes.mean()
                        else:
                            average_pokes_per_trial = np.nan

                        average_data.append((session_date_obj, average_pokes_per_trial))

            except ValueError:
                print(f"Could not parse date from folder name: {folder_name}")

    # Ensure all encountered dates are included, with NaNs for dates with insufficient data
    complete_average_data = pd.DataFrame(list(encountered_dates), columns=['session_date'])
    complete_average_data = complete_average_data.merge(pd.DataFrame(average_data, columns=['session_date', 'average_pokes_per_trial']), 
                                                        on='session_date', how='left').sort_values('session_date').reset_index(drop=True)

    # Plot the continuous trace even if some data is missing for certain dates
    if not complete_average_data.empty:
        line, = ax.plot(complete_average_data['session_date'], complete_average_data['average_pokes_per_trial'], 
                        marker='o', linestyle='-', label=label)

        if overall_daily_avg is not None:
            for date, avg in zip(complete_average_data['session_date'], complete_average_data['average_pokes_per_trial']):
                if not pd.isna(avg):
                    if date in overall_daily_avg:
                        overall_daily_avg[date].append(avg)
                    else:
                        overall_daily_avg[date] = [avg]

        ax.set_ylabel('N Pokes per Trial')
        ax.set_title('Average Pokes per Trial Across Days')
        ax.set_ylim(6, 1)
        ax.axhline(y=4, color='black', linestyle=':', label='Chance Level = 4' if label == mouse_name else None)
        #ax.axvline(x=datetime.strptime("2024-10-25", "%Y-%m-%d"), color='red', linestyle='--', label='Change to Sweep Task' if label == mouse_name else None)
        #ax.axvline(x=datetime.strptime("2024-11-12", "%Y-%m-%d"), color='green', linestyle='--', label='Speaker Issue Fix' if label == mouse_name else None)
        
        ax.grid()
        return [line], [label]
    return [], []

if __name__ == "__main__":
    plot_combined(data_directory, mouse_names, start_date)

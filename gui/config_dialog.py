## LIST / CONFIG RELATED CLASSES
"""
These are classes that are primarily used to display different tasks in a list 
that can be edited on the GUI.
There are a lot of different menus and elements involved that's why there are a 
lot of  individual classes in this section (could have named them better)
Their functions are as follows:
- ConfigurationDetailsDialog: Dialog Box that shows up to display all the 
    parameters for a specific task when right clicking a task (can't be edited)
- PresetTaskDialog: This is a menu that appears when adding a new mouse. It 
    gives you the option to just choose a task from a list and the 
    default parameters will be applied according to the values set in the 
    defaults file (pi/configs/defaults.json)
- ConfigurationDialog: This is an editable window that shows up when right 
    clicking a task and selecting 'Edit Configuration'. The values of the 
    different task parameters can be changed and saved here
- ConfigurationList: The list of saved tasks for the mice. New mice can be 
    added or removed here and can be searched for. It is also responsible for 
    sending task parameters to the pi side using another network socket.
    (Initially wanted Worker class to handle all network related but was 
    not able to implement it properly. Can be changed if needed)
"""

# Displays a Dialog box with all the details of the task when you click View Details after right-clicking
class ConfigurationDetailsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        
        # Setting the title for the window
        self.setWindowTitle("Configuration Details") 

        # Creating labels to display saved configuration parameters in the window
        self.name_label = QLabel(f"Name: {config['name']}")
        self.task_label = QLabel(f"Task: {config['task']}")
        self.amplitude_label = QLabel(f"Amplitude: {config['amplitude_min']} - {config['amplitude_max']}")
        self.rate_label = QLabel(f"Rate: {config['rate_min']} - {config['rate_max']}")
        self.irregularity_label = QLabel(f"Irregularity: {config['irregularity_min']} - {config['irregularity_max']}")
        self.reward_label = QLabel(f"Reward Value: {config['reward_value']}")
        self.freq_label = QLabel(f"Center Frequency: {config['center_freq_min']} - {config['center_freq_max']}")
        self.band_label = QLabel(f"Bandwidth: {config['bandwidth']}")

        # Creating a button used to exit the window 
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        self.button_box.accepted.connect(self.accept)

        # Arranging all the labels in a vertical layout
        layout = QVBoxLayout()
        layout.addWidget(self.name_label)
        layout.addWidget(self.task_label)
        layout.addWidget(self.amplitude_label)
        layout.addWidget(self.freq_label)
        layout.addWidget(self.band_label)
        layout.addWidget(self.rate_label)
        layout.addWidget(self.irregularity_label)
        layout.addWidget(self.reward_label)
        layout.addWidget(self.button_box)
        self.setLayout(layout)


# Displays the prompt to make a new task based on default parameters (with the option to edit if needed)
class PresetTaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Setting the title for the window
        self.setWindowTitle("Enter Name and Select Task")

        # Setting a vertical layout for all the elements in this window
        self.layout = QVBoxLayout(self)

        # Making an editable section to save the name
        self.name_label = QLabel("Name:")
        self.name_edit = QLineEdit(self)

        # Making a drop-down list of existing task presets to choose from 
        self.task_label = QLabel("Select Task:")
        self.task_combo = QComboBox(self)
        self.task_combo.addItems(["Fixed", "Sweep", "Poketrain", "Distracter", "Audio"])  
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)

        # Adding all the elements in this window to a vertical layout 
        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.name_edit)
        self.layout.addWidget(self.task_label)
        self.layout.addWidget(self.task_combo)
        self.layout.addWidget(self.ok_button)

    # Method to get the saved name and the selected task type of the mouse
    def get_name_and_task(self):
        return self.name_edit.text(), self.task_combo.currentText()


# Displays an editable dialog box on clicking 'Edit Configuration' to change the parameters for the tasks if needed (after right clicking task) 
class ConfigurationDialog(QDialog):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        
        # Setting window title 
        self.setWindowTitle("Edit Configuration Details")
        
        # Initializing the format for edited configs to be saved in (if more parameters need to be added later this needs to be changed)
        self.config = config if config else {
            "name": "",
            "task": "",
            "amplitude_min": 0.0,
            "amplitude_max": 0.0,
            "rate_min": 0.0,
            "rate_max": 0.0,
            "irregularity_min": 0.0,
            "irregularity_max": 0.0,
            "center_freq_min": 0.0,
            "center_freq_max": 0.0,
            "bandwidth": 0.0,
            "reward_value": 0.0
        }
        
        self.init_ui()

    def init_ui(self):
        
        # Setting a vertical layout for all elements in this menu
        layout = QVBoxLayout(self)

        # Section to edit name 
        self.name_label = QLabel("Name:")
        self.name_edit = QLineEdit(self.config.get("name", ""))
        
        """
        Currently the main format tasks are saved in are for the sweep task. The hack to making the logic work for fixed is to make both the min and max values the same
        For poketrain, these values are set to a very small number so there is no sound playing at all
        """

        # Task remains fixed (cannot be edited currently)
        self.task_label = QLabel(f"Task: {self.config.get('task', '')}")

        # Section to edit the range of amplitudes 
        self.amplitude_label = QLabel("Amplitude:")
        amplitude_layout = QHBoxLayout()
        self.amplitude_min_label = QLabel("Min:")
        self.amplitude_min_edit = QLineEdit(str(self.config.get("amplitude_min", "")))
        self.amplitude_max_label = QLabel("Max:")
        self.amplitude_max_edit = QLineEdit(str(self.config.get("amplitude_max", "")))
        amplitude_layout.addWidget(self.amplitude_min_label)
        amplitude_layout.addWidget(self.amplitude_min_edit)
        amplitude_layout.addWidget(self.amplitude_max_label)
        amplitude_layout.addWidget(self.amplitude_max_edit)

        # Section to edit the range of playing rate 
        self.rate_label = QLabel("Rate:")
        rate_layout = QHBoxLayout()
        self.rate_min_label = QLabel("Min:")
        self.rate_min_edit = QLineEdit(str(self.config.get("rate_min", "")))
        self.rate_max_label = QLabel("Max:")
        self.rate_max_edit = QLineEdit(str(self.config.get("rate_max", "")))
        rate_layout.addWidget(self.rate_min_label)
        rate_layout.addWidget(self.rate_min_edit)
        rate_layout.addWidget(self.rate_max_label)
        rate_layout.addWidget(self.rate_max_edit)

        # Section to edit irregularity
        self.irregularity_label = QLabel("Irregularity:")
        irregularity_layout = QHBoxLayout()
        self.irregularity_min_label = QLabel("Min:")
        self.irregularity_min_edit = QLineEdit(str(self.config.get("irregularity_min", "")))
        self.irregularity_max_label = QLabel("Max:")
        self.irregularity_max_edit = QLineEdit(str(self.config.get("irregularity_max", "")))
        irregularity_layout.addWidget(self.irregularity_min_label)
        irregularity_layout.addWidget(self.irregularity_min_edit)
        irregularity_layout.addWidget(self.irregularity_max_label)
        irregularity_layout.addWidget(self.irregularity_max_edit)
        
        # Section to edit center frequency of the filtered white noise
        self.freq_label = QLabel("Center Frequency:")
        freq_layout = QHBoxLayout()
        self.freq_min_label = QLabel("Min:")
        self.freq_min_edit = QLineEdit(str(self.config.get("center_freq_min", "")))
        self.freq_max_label = QLabel("Max:")
        self.freq_max_edit = QLineEdit(str(self.config.get("center_freq_max", "")))
        freq_layout.addWidget(self.freq_min_label)
        freq_layout.addWidget(self.freq_min_edit)
        freq_layout.addWidget(self.freq_max_label)
        freq_layout.addWidget(self.freq_max_edit)
        
        # Section to edit bandwidth
        self.band_label = QLabel("Bandwidth:")
        self.band_edit = QLineEdit(str(self.config.get("bandwidth", "")))
        
        # Section to edit reward duration 
        self.reward_label = QLabel("Reward Value:")
        self.reward_edit = QLineEdit(str(self.config.get("reward_value", "")))

        # Create button box with OK and Cancel buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # Arrange widgets in a vertical layout
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.task_label)
        layout.addWidget(self.amplitude_label)
        layout.addLayout(amplitude_layout)
        layout.addWidget(self.rate_label)
        layout.addLayout(rate_layout)
        layout.addWidget(self.irregularity_label)
        layout.addLayout(irregularity_layout)
        layout.addWidget(self.freq_label)
        layout.addLayout(freq_layout)
        layout.addWidget(self.band_label)
        layout.addWidget(self.band_edit)
        layout.addWidget(self.reward_label)
        layout.addWidget(self.reward_edit)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

        # Show/hide widgets based on the task type 
        self.update_widgets_based_on_task()

    def update_widgets_based_on_task(self):
        """
        This method makes it so that the range is hidden for when the task is Fixed. 
        Since Fixed doesnt need a min or max range, we remove extra editable boxes and ranges.
        This method also sets the min and max values to be the same 
        (This can be done for poketrain too)
        """
        task = self.config.get("task", "")

        if task.lower() == "fixed":
            # For "Fixed" task, hide max edit fields and labels
            self.amplitude_min_label.hide()
            self.amplitude_max_label.hide()
            self.amplitude_max_edit.hide()
            self.rate_min_label.hide()
            self.rate_max_label.hide()
            self.rate_max_edit.hide()
            self.irregularity_min_label.hide()
            self.irregularity_max_label.hide()
            self.irregularity_max_edit.hide()
            self.freq_min_label.hide()
            self.freq_max_label.hide()
            self.freq_max_edit.hide()

            # Connect min edit fields to update max fields such that their value is the same
            self.amplitude_min_edit.textChanged.connect(self.update_amplitude_max)
            self.rate_min_edit.textChanged.connect(self.update_rate_max)
            self.irregularity_min_edit.textChanged.connect(self.update_irregularity_max)
            self.freq_min_edit.textChanged.connect(self.update_freq_max)


        else:
            # For other tasks, show all min and max edit fields
            pass

    # Methods used to match the min and max parameter value
    def update_amplitude_max(self):
        value = self.amplitude_min_edit.text()
        self.amplitude_max_edit.setText(value)

    def update_rate_max(self):
        value = self.rate_min_edit.text()
        self.rate_max_edit.setText(value)

    def update_irregularity_max(self):
        value = self.irregularity_min_edit.text()
        self.irregularity_max_edit.setText(value)

    def update_freq_max(self):
        value = self.freq_min_edit.text()
        self.freq_max_edit.setText(value)
    
    def get_configuration(self):
        """
        Method to save all the updated values of the task / mouse. 
        It grabs the text entered in the boxes and formats it according to the format we sent earlier.
        It overwrites the current json file used for the task 
        """
        
        # Updating the name of the mouse and grabbing the task associated with it 
        updated_name = self.name_edit.text()
        task = self.config.get("task", "")

        # Grabbing all the values from the text boxes and overwriting the existing values
        try:
            amplitude_min = float(self.amplitude_min_edit.text())
            amplitude_max = float(self.amplitude_max_edit.text())
            rate_min = float(self.rate_min_edit.text())
            rate_max = float(self.rate_max_edit.text())
            irregularity_min = float(self.irregularity_min_edit.text())
            irregularity_max = float(self.irregularity_max_edit.text())
            center_freq_min = float(self.freq_min_edit.text())
            center_freq_max = float(self.freq_max_edit.text())
            bandwidth = float(self.band_edit.text())
            reward_value = float(self.reward_edit.text())
            
        except ValueError:
            # Handle invalid input
            return None

        # Updating the format to be used while saving these values to the json file
        updated_config = {
            "name": updated_name,
            "task": task,
            "amplitude_min": amplitude_min,
            "amplitude_max": amplitude_max,
            "rate_min": rate_min,
            "rate_max": rate_max,
            "irregularity_min": irregularity_min,
            "irregularity_max": irregularity_max,
            "center_freq_min": center_freq_min,
            "center_freq_max": center_freq_max,
            "bandwidth": bandwidth,
            "reward_value": reward_value
        }

        return updated_config


# List of mice that have been saved under certain tasks. It is used to send task parameters to the Pi
class ConfigurationList(QWidget):
    send_config_signal = pyqtSignal(dict) # Currently unused. I think I put this here while trying to make the Worker send the configs instead but that didnt work
    
    def __init__(self, params):
        super().__init__()
        
        # Initializing variables to store current task
        self.configurations = []
        self.current_config = None
        self.current_task = None
        self.config_tree = None
        
        # Store params
        self.params = params
        
        # Sukrith: this was after self.load_default_parameters and this was
        # causing problems
        self.init_ui()

        # Loading default parameters for tasks and also the list of tasks 
        # from the default directory
        self.default_parameters = self.load_default_parameters()
        
        # Call the method to load configurations from a default directory 
        # during initialization
        self.load_default()  

        # Making a ZMQ socket strictly to send task params to pi
        self.context = zmq.Context()
        self.publisher = self.context.socket(zmq.PUB)
        
        # Binding to the port assigned for publishing params 
        self.publisher.bind("tcp://*" + params['config_port'])  

    def init_ui(self):
        # Making a cascasing list of tasks that mice are categorized under
        self.config_tree = QTreeWidget()
        self.config_tree.setHeaderLabels(["Tasks"])
        
        # Making a search box used to search for mice
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search for a mouse...")
        
        # Buttons to add / remove mice
        self.add_button = QPushButton('Add Mouse')
        self.remove_button = QPushButton('Remove Mouse')
        
        # Label to display the currently selected mouse 
        self.selected_config_label = QLabel()

        # Making horizontal layout for the buttons 
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)

        # Making a vertical layout for the entire widget
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.selected_config_label)
        main_layout.addWidget(self.search_box)
        main_layout.addWidget(self.config_tree)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

        # Assigning methods to be executed when the relevant buttons are clicked 
        self.add_button.clicked.connect(self.add_configuration)
        self.remove_button.clicked.connect(self.remove_configuration)
        
        # Setting title for the window
        self.setWindowTitle('Configuration List')
        
        # Displaying the widget
        self.show()

        # Enable custom context menu (that appears when right clicking)
        self.config_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.config_tree.customContextMenuRequested.connect(self.show_context_menu)
        
        # Executing a method to filter configs when the text in the search box is changed 
        self.search_box.textChanged.connect(self.filter_configurations)
        
    # Executes a method to display only the configs that contain the same string as it and update the whole list dynamically
    def filter_configurations(self, text):
        # Logic to remove mice that do not match the string 
        if not text:
            self.update_config_list()
            return
        
        # Displaying the list of configs that contain the same characters as the text in the search box
        filtered_configs = [] # Empty list to add matching configs to
        for config in self.configurations:
            if text.lower() in config["name"].lower():
                filtered_configs.append(config) # Appending matching configs to a list 

        # Updating the entire list of configs
        self.update_config_list(filtered_configs)

    # Warning to notify user that no config is selected when starting session
    def on_start_button_clicked(self):
        if self.current_config is None:
            QMessageBox.warning(self, "Warning", "Please select a mouse before starting the experiment.")
    
    # Loading default task parameters from json file when needed
    def load_default_parameters(self):
        with open(self.params['pi_defaults'], 'r') as file:
            return json.load(file)

    # Method to add a new mouse
    def add_configuration(self):
        
        # Displaying the preset menu to name the mouse
        preset_task_dialog = PresetTaskDialog(self)
        if preset_task_dialog.exec_() == QDialog.Accepted:
            name, task = preset_task_dialog.get_name_and_task()
            
            # Get the default parameters for the selected task
            if task in self.default_parameters:
                default_params = self.default_parameters[task]
            else:
                default_params = {
                    "amplitude_min": 0.0,
                    "amplitude_max": 0.0,
                    "rate_min": 0.0,
                    "rate_max": 0.0,
                    "irregularity_min": 0.0,
                    "irregularity_max": 0.0,
                    "center_freq_min": 0.0,
                    "center_freq_max": 0.0,
                    "bandwidth": 0.0,
                    "reward_value": 0.0
                }

            # Instantiate ConfigurationDialog properly (for editing it later)
            dialog = ConfigurationDialog(self, {
                "name": name,
                "task": task,
                **default_params
            })
            
            # Once the mouse is saved, update the config list with the new mouse
            if dialog.exec_() == QDialog.Accepted:
                new_config = dialog.get_configuration()
                self.configurations.append(new_config)
                self.update_config_list()

                # Automatically save a json file of the configuration according the mouse's name 
                config_name = new_config["name"]
                file_path = os.path.join(params['task_configs'], f"{config_name}.json")
                with open(file_path, 'w') as file:
                    json.dump(new_config, file, indent=4)

    # Method to remove mice 
    def remove_configuration(self):
        # Selecting which mouse to remove 
        selected_item = self.config_tree.currentItem()

        # Removing the mouse from the list of configs to display
        if selected_item and selected_item.parent():
            selected_config = selected_item.data(0, Qt.UserRole)
            self.configurations.remove(selected_config)
            self.update_config_list()

            # Get the filename of the selected mouse
            config_name = selected_config["name"] # Make sure filename is the same as name in the json
            
            # Constructing the full file path with the name
            file_path = os.path.join(params['task_configs'], f"{config_name}.json")

            # Checking if the file exists and deleting it
            if os.path.exists(file_path):
                os.remove(file_path)

    # This function is an extra functionality to load configs from a folder apart from the default location in directory if needed
    def load_configurations(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Configuration Folder")
        if folder:
            self.configurations = self.import_configs_from_folder(folder)
            self.update_config_list()

    # This is a function that loads all the saved task from the default directory where mice are saved
    def load_default(self):
        default_directory = os.path.abspath(self.params['task_configs'])
        if os.path.isdir(default_directory):
            self.configurations = self.import_configs_from_folder(default_directory)
            self.update_config_list()

    # Method used to load all the configs from a specific folder 
    def import_configs_from_folder(self, folder):
        configurations = [] # list of configs
        for filename in os.listdir(folder): 
            if filename.endswith(".json"): # Looking at all json files in specified folder
                file_path = os.path.join(folder, filename) 
                with open(file_path, 'r') as file:
                    config = json.load(file) # Loading all json files 
                    configurations.append(config) # Appending to list of configuration s
        return configurations

    # Method used to update cascading lists whenever a change is made (adding/removing/update)
    def update_config_list(self, configs=None):
        if self.config_tree is not None:
            self.config_tree.clear() # Clearing old list of mice
        categories = {}

        # Adding all configs
        if configs is None:
            configs = self.configurations

        # Categorizing mice based on their different tasks (name of task is extracted from json)
        for config in configs:
            category = config.get("task", "Uncategorized") # Making a category for config files without task (unused now)
            if category not in categories:
                category_item = QTreeWidgetItem([category])
                self.config_tree.addTopLevelItem(category_item)
                categories[category] = category_item
            else:
                category_item = categories[category]

            # Listing the names of different configs under categories 
            config_item = QTreeWidgetItem([config["name"]])
            config_item.setData(0, Qt.UserRole, config)
            category_item.addChild(config_item)

        # Executing the method for sending a config file to the pi when a mouse on the list is double clicked 
        self.config_tree.itemDoubleClicked.connect(self.config_item_clicked)
        
    # Method for logic on what to do when a mouse is double clicked (mainly used to send data to pi)
    def config_item_clicked(self, item, column):
        global current_task, current_time 
        
        if item.parent():  # Ensure it's a config item, not a category
            selected_config = item.data(0, Qt.UserRole)
            self.current_config = selected_config
            self.selected_config_label.setText(f"Selected Config: {selected_config['name']}") # Changing the label text to indicate the currently selected config. Otherwise None
            
            # Prompt to confirm selected configuration (to prevent accidentally using parameters for wrong mouse)
            confirm_dialog = QMessageBox()
            confirm_dialog.setIcon(QMessageBox.Question)
            confirm_dialog.setText(f"Do you want to use '{selected_config['name']}'?")
            confirm_dialog.setWindowTitle("Confirm Configuration")
            confirm_dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            confirm_dialog.setDefaultButton(QMessageBox.Yes)
            
            # Logic for what to do when the selection is confirmed 
            if confirm_dialog.exec_() == QMessageBox.Yes:
                # Serialize JSON data and send it over ZMQ to all the IPs connected to the specified port
                json_data = json.dumps(selected_config)
                self.publisher.send_json(json_data)

                # Updating the global variables for the selected task and updating the time to indicate when it was sent 
                self.current_task = selected_config['name'] + "_" + selected_config['task']
                self.current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                current_time = self.current_time
                current_task = self.current_task

                # Creating a toast message to indicate that the message has been sent to all IPs connected to the config port
                toast = Toast(self)
                toast.setDuration(5000)  # Hide after 5 seconds
                toast.setTitle('Task Parameters Sent') # Setting title
                toast.setText(f'Parameters for task {current_task} have been sent to {args.json_filename}') # Setting test
                toast.applyPreset(ToastPreset.SUCCESS)  # Apply style preset
                toast.show()
            else:
                self.selected_config_label.setText(f"Selected Config: None")

    # Displaying a context menu with options to view and edit when a config is right clicked
    def show_context_menu(self, pos):
        item = self.config_tree.itemAt(pos)
        if item and item.parent():  # Ensure it's a config item, not a category
            menu = QMenu(self)
            
            # Listing possible actions
            view_action = QAction("View Details", self)
            edit_action = QAction("Edit Configuration", self)
            
            # Connecting these actions to methods
            view_action.triggered.connect(lambda: self.view_configuration_details(item))
            edit_action.triggered.connect(lambda: self.edit_configuration(item))
            
            # Listing these actions on the context menu 
            menu.addAction(view_action)
            menu.addAction(edit_action)
            menu.exec_(self.config_tree.mapToGlobal(pos))

    # Method for what to do when 'Edit Configuration' is clicked
    def edit_configuration(self, item):
        selected_config = item.data(0, Qt.UserRole)
        dialog = ConfigurationDialog(self, selected_config) # Displays the menu to edit configurations
        if dialog.exec_() == QDialog.Accepted: 
            updated_config = dialog.get_configuration() # Updating details based on saved information 
            if updated_config:
                self.configurations = [config if config['name'] != selected_config['name'] else updated_config for config in self.configurations] # overwriting 
                self.update_config_list() # Updating list of configs based on edits made 

                # Saving the updated configuration as a json file/ Updating existing json
                config_name = updated_config["name"]
                file_path = os.path.join(params['task_configs'], f"{config_name}.json")
                with open(file_path, 'w') as file:
                    json.dump(updated_config, file, indent=4)

    # Method for what to do when 'View Details' is clicked 
    def view_configuration_details(self, item):
        selected_config = item.data(0, Qt.UserRole)
        dialog = ConfigurationDetailsDialog(selected_config, self) # Display the menu
        dialog.exec_()

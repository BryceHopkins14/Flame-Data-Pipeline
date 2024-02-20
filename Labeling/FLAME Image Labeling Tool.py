#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
# FLAME Image Labeling Tool
# Version 1.0
# Created on 02/19/2024
# Created by Bryce Hopkins
# Instructions: Run program, follow onscreen instructions.
# For questions, email bryceh@clemson.edu
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#

import os
import PySimpleGUI as sg
import shutil
import io
import cv2
from PIL import Image
import queue
import numpy as np
import threading

# Initialize lists and queue
BUFF_RADIUS = 7                 # Radius of buffer to preload images. 7 seems to work well for typical use.
q = queue.Queue()               # Queue full of img filepaths to load   P
b_rgb = []                      # Vector to store output img data. Should be moved to rotary buffer later.
b_ir = []
b_tiff = []

# Note: Current code loads images from low end of buffer to high end. Would be more efficient to load center of buffer first and gradually expand outwards.

# Set theme for GUI
sg.theme('DarkTeal6')

'''
Function that handles image loading from a queue for rgb, ir, and tiffs
It will also append a tuple (index, img) to the proper list 
For tiffs, it will retrieve the min, max, and average temperature stats
'''
def img_loader():
    while True:
        index, path, rgb_ir = q.get()
        if path is None:
            break
        if rgb_ir == "rgb":
            img = load_image(path)
            b_rgb.append((index, img))
        elif rgb_ir == "ir":
            img = load_image(path)
            b_ir.append((index, img))
        elif rgb_ir == "tiff":
            (tiff_min, tiff_avg, tiff_max) = get_temp_stats_from_tiff(path)
            b_tiff.append((index, (tiff_min, tiff_avg, tiff_max)))

        q.task_done()

'''
Function that gets the min, average, and max values of a tiff image and returns
a tuple with that information (min, avg, max)
'''
def get_temp_stats_from_tiff(path):
    arr = np.array(Image.open(path))
    return (np.min(arr), np.average(arr), np.max(arr))

'''
Function  to start/initialize the img loaders for multithreading
Helps to improve performance and loading times of images
'''
def start_img_loaders(worker_pool=2):
    threads = []
    for i in range(worker_pool):
        t = threading.Thread(target=img_loader)
        t.start()
        threads.append(t)
    return threads

'''
Function that stops workers based on a list of threads sent into the function
'''
def stop_workers(threads):
    # stop workers
    for i in threads:
        q.put((None, None, None))
    for t in threads:
        t.join()

'''
Function that creates the queue and places all items in task_items into the queue
'''
def create_queue(task_items):
    for item in task_items:
        q.put(item)

'''
Function that loads an image from image_path and resizes it to default size (640, 512) 
Encodes the image in .png format
Returns the byte representation of the encoded image data
'''
def load_image(image_path, size=(640,512)):
    img = cv2.imread(image_path)
    bio = io.BytesIO()
    img = cv2.resize(img, size)
    is_success, buffer = cv2.imencode(".png", img)
    bio = io.BytesIO(buffer)
    del img
    #print(f'loaded img {image_path} w/ ret {is_success}')
    return bio.getvalue()

'''
Function that creates an image files list from the folder_path
Returns the list of image files that match the extensions listed
'''
def get_image_files(folder_path):
    image_extensions = (".jpg", ".jpeg" ,".JPG", ".TIFF", ".tiff")
    image_files = [file for file in os.listdir(folder_path) if file.lower().endswith(image_extensions)]
    return image_files

# main function, handle events within the application and image processing
def main():
    # Load in the image assets
    coming_soon = load_image('./Assets/ComingSoon.png')
    fire_img = load_image('./Assets/Fire.png', (100,100))
    no_fire_img = load_image('./Assets/No_Fire.png', (100,100)) # NOTE: No_Fire.png needs to be downscaled... its 5000x5000 for some reason
    no_label_img = load_image('./Assets/No_Label.png', (100,100))

    # section to let the user choose the path to their image files
    folder_selected = False
    while not folder_selected:
        folder_path = sg.popup_get_folder("Select parent folder containing images. File directory should be:\n\tfolder/RGB/Raw/image.JPG\n\tfolder/RGB/Corrected FOV/image.JPG\n\tfolder/Thermal/JPG/image.JPG\n\tfolder/Thermal/Celsius TIFF/image.TIFF)\n\nPlease use 'Raw File Sorting.ipynb' on raw data before using this tool.\nIf 'Raw File Sorting.ipynb' was used, select the 'Images' subfolder as the input.", title="Select Parent Folder")
        if not folder_path:
            return

        # Check to see if the input image folder contains the proper file structure
        try:
            rgb_image_files = get_image_files(f'{folder_path}/RGB/Corrected FOV/')
            ir_image_files = get_image_files(f'{folder_path}/Thermal/JPG/') #   NOTE: assumed that paired RGB/IR images have same filename (different file extension for TIFF)
            tiff_image_files = get_image_files(f'{folder_path}/Thermal/Celsius TIFF/')
        # Error if the input image folder structure is invalid
        except:
            sg.popup(f"ERROR: Unable to open subdirectories:\n\t{folder_path}/RGB/Corrected FOV/\n\t{folder_path}/Thermal/JPG/\n\t{folder_path}/Thermal/Celsius TIFF/\n\nPlease make sure the correct parent folder is selected.", line_width=350, title="Error")
        else:
            folder_selected = True

    # Checks to see if there are RGB, IR, and TIFF image files included in the directory, if not, display error message
    if not rgb_image_files:
        sg.popup_error("No rgb image files found in the selected folder.")
        return
    if not ir_image_files:
        sg.popup_error("No ir jpg image files found in the selected folder.")
        return
    if not tiff_image_files:
        sg.popup_error("No ir tiff image files found in the selected folder.")
        return

    # GUI Layouts
    layout = [
        [sg.Text("Move between images with arrow keys"), sg.Push(), sg.Combo(['Fire', 'No Fire', 'Unlabeled'], 'Unlabeled', key='-LABEL_DROPDOWN-', readonly=True), sg.Button('Apply to All'), sg.Push(), sg.Button('Save State', k='-SAVE_STATE-'), sg.Button('Load State', k='-LOAD_STATE-'), sg.Push(), sg.Button("Export Images w/ Labels", key='-EXPORT-')],
        [sg.Button("Help", key="-HELP-")],
        [sg.Button('Temperature Based Labeling', key = '-TEMP_LABEL-'), sg.Push(), sg.Text("Applied Label: "), sg.Image(key='-LABEL_IMG-', size = (100, 100))],
        [sg.Button('Go To', key='-GOTO-'), sg.Text(key="-FILE_NAME-", text="Filename: "), sg.Push(), sg.Text('Min Temp: \tAvg Temp: \tMax Temp: ', key='-TEMP_STATS-')],
        [sg.Image(key="-RGB_IMAGE-", size=(640,512)), sg.Image(key='-IR_IMAGE-', size=(640,512))],
        [sg.Text('Assign labels to displayed images w/ 1, 2, 3 keys. 1 = Fire, 2 = No Fire, 3 = No Label (discarded)'), sg.Push(), sg.Text('Created by Bryce Hopkins')]
    ]

    # Preload buffers w/ initial images
    index = 0
    loaded_rgb_images = [None]*len(rgb_image_files)
    loaded_ir_images = [None]*len(rgb_image_files)
    loaded_tiff_vals = [None]*len(rgb_image_files)
    labels = [None]*len(rgb_image_files)
    starting_images = []
    for i in range(-BUFF_RADIUS, BUFF_RADIUS + 1):
        starting_images.append(((index+i)% len(rgb_image_files), f'{folder_path}/RGB/Corrected FOV/{rgb_image_files[(index+i)% len(rgb_image_files)]}', "rgb"))
        starting_images.append(((index+i)% len(rgb_image_files), f'{folder_path}/Thermal/JPG/{rgb_image_files[(index+i)% len(rgb_image_files)]}', "ir"))
        #starting_images.append(((index+i)% len(rgb_image_files), f'{folder_path}/Thermal/Celsius TIFF/{rgb_image_files[(index+i)% len(rgb_image_files)].split(".")[0]}.TIFF', "tiff"))

    # Initialize workers, add tasks to queue, then wait for workers to finish preloading initial batch of images.
    workers = start_img_loaders(worker_pool=10)
    create_queue(starting_images)
    q.join()
    
    # Go through worker outputs, moving loaded images from the output stacks to the correct loaded image vectors.
    for id, img in b_rgb:
        if min(((index - id) % len(rgb_image_files)), ((id - index) % len(rgb_image_files))) <= BUFF_RADIUS:
            loaded_rgb_images[id] = img
            #print(f'image {id} placed in loaded images')
        else:
            loaded_rgb_images[id] = None
        b_rgb.remove((id, img))
    for id, img in b_ir:
        if min(((index - id) % len(rgb_image_files)), ((id - index) % len(rgb_image_files))) <= BUFF_RADIUS:
            loaded_ir_images[id] = img
            #print(f'image {id} placed in loaded images')
        else:
            loaded_ir_images[id] = None
        b_ir.remove((id, img))
    for id, (temp_min, temp_avg, temp_max) in b_tiff:
        if min(((index - id) % len(rgb_image_files)), ((id - index) % len(rgb_image_files))) <= BUFF_RADIUS:
            loaded_tiff_vals[id] = (temp_min, temp_avg, temp_max)
            #print(f'tiff {id} placed in loaded tiff vals')
        else:
            loaded_tiff_vals[id] = None
        b_tiff.remove((id, (temp_min, temp_avg, temp_max)))
    
    # main application window setup
    window = sg.Window("FLAME Image Labeling Tool", layout, resizable=True, return_keyboard_events=True)

    # Main event loop
    while True:
        # setup window events and timeout duration
        event, values = window.read(timeout=500)
        #print(event, values)
        # break main event loop if the window is closed
        if event == sg.WIN_CLOSED:
            break
        # section to handle left or right arrow key pressed
        elif event in ("Left:37", "Right:39"):
            #   For left or right arrow press:
            #   Move current image index up/down
            #   Add the appropriate image to the image loading queue
            if event == "Left:37":
                index = (index - 1) % len(rgb_image_files)
                q.put(((index - BUFF_RADIUS) % len(rgb_image_files), f'{folder_path}/RGB/Corrected FOV/{rgb_image_files[(index - BUFF_RADIUS) % len(rgb_image_files)]}', "rgb"))
                q.put(((index - BUFF_RADIUS) % len(rgb_image_files), f'{folder_path}/Thermal/JPG/{rgb_image_files[(index - BUFF_RADIUS) % len(rgb_image_files)]}', "ir"))
                #q.put(((index - BUFF_RADIUS) % len(rgb_image_files), f'{folder_path}/Thermal/Celsius TIFF/{rgb_image_files[(index - BUFF_RADIUS) % len(rgb_image_files)].split(".")[0]}.TIFF', "tiff"))
            elif event == "Right:39":
                index = (index + 1) % len(rgb_image_files)
                q.put(((index + BUFF_RADIUS) % len(rgb_image_files), f'{folder_path}/RGB/Corrected FOV/{rgb_image_files[(index + BUFF_RADIUS) % len(rgb_image_files)]}', "rgb"))
                q.put(((index + BUFF_RADIUS) % len(rgb_image_files), f'{folder_path}/Thermal/JPG/{rgb_image_files[(index + BUFF_RADIUS) % len(rgb_image_files)]}', "ir"))
                #q.put(((index + BUFF_RADIUS) % len(rgb_image_files), f'{folder_path}/Thermal/Celsius TIFF/{rgb_image_files[(index + BUFF_RADIUS) % len(rgb_image_files)].split(".")[0]}.TIFF', "tiff"))

        # handle labeling commands
        elif event in ("1", "2", "3"):
            # for 1, 2, 3 press, apply the corresponding label to the displayed images
            match event:
                case "1":
                    labels[index] = "Fire"
                case "2":
                    labels[index] = "No Fire"
                case "3":
                    labels[index] = None

        # apply the specified label from the dropdown and apply to all images
        elif event == "Apply to All":
            # for apply all, apply the currently selected label in the dropdown list to all displayed images
            match values['-LABEL_DROPDOWN-']:
                case "Fire":
                    labels = ["Fire" for x in labels]
                case "No Fire":
                    labels = ["No Fire" for x in labels]
                case "Unlabeled":
                    labels = [None for x in labels]
        
        elif event == '-EXPORT-':
            # for export, copy all input files to output directories based on the applied labels

            # ask the user if they want to rename the files to five digit number scheme
            OUTPUT_FILENAME_DIGITS = 5
            renumber = sg.popup_yes_no(f'Do you want to rename output files to 00001.jpg - {"0"*(OUTPUT_FILENAME_DIGITS-len(str(len(rgb_image_files)))) + str(len(rgb_image_files))}.jpg?\n\nYes = Rename (recommended), No = Preserve input file names', title="Rename Output Files?")

            if renumber == None:
                continue

            # if it doesn't exist, creat the output file directory
            if not os.path.exists('./Output/Fire/RGB/Corrected FOV/'):
                os.makedirs('./Output/Fire/RGB/Corrected FOV/')
            if not os.path.exists('./Output/Fire/RGB/Raw/'):
                os.makedirs('./Output/Fire/RGB/Raw/')
            if not os.path.exists('./Output/Fire/Thermal/JPG/'):
                os.makedirs('./Output/Fire/Thermal/JPG/')
            if not os.path.exists('./Output/Fire/Thermal/Celsius TIFF/'):
                os.makedirs('./Output/Fire/Thermal/Celsius TIFF/')
            
            if not os.path.exists('./Output/No Fire/RGB/Corrected FOV/'):
                os.makedirs('./Output/No Fire/RGB/Corrected FOV/')
            if not os.path.exists('./Output/No Fire/RGB/Raw/'):
                os.makedirs('./Output/No Fire/RGB/Raw/')
            if not os.path.exists('./Output/No Fire/Thermal/JPG/'):
                os.makedirs('./Output/No Fire/Thermal/JPG/')
            if not os.path.exists('./Output/No Fire/Thermal/Celsius TIFF/'):
                os.makedirs('./Output/No Fire/Thermal/Celsius TIFF/')

            # validate that there are no files in the output directories
            if (not len(os.listdir('./Output/No Fire/RGB/Corrected FOV/')) == 0 or
                not len(os.listdir('./Output/Fire/RGB/Corrected FOV/')) == 0 or
                not len(os.listdir('./Output/No Fire/RGB/Raw/')) == 0 or
                not len(os.listdir('./Output/Fire/RGB/Raw/')) == 0 or
                not len(os.listdir('./Output/No Fire/Thermal/JPG/')) == 0 or
                not len(os.listdir('./Output/Fire/Thermal/JPG/')) == 0 or
                not len(os.listdir('./Output/No Fire/Thermal/Celsius TIFF/')) == 0 or
                not len(os.listdir('./Output/Fire/Thermal/Celsius TIFF/')) == 0):
                sg.popup('Error: The output directories are not empty! Please clear the output directory and try again.')
                continue
            
            # Copy input files to output according to their applied labels
            fcount = 0
            nfcount = 0
            ulcount = 0
            #iterate over the rgb, ir, tiff, and label lists/files
            for ix, (rgb, ir, tiff, label) in enumerate(zip(rgb_image_files, ir_image_files, tiff_image_files, labels)):
                rgb_n = rgb
                ir_n = ir
                tiff_n = tiff

                # label images according to their label and renumber naming scheme if specified
                # copy images to the proper folder with the proper renaming
                if label == 'Fire':
                    if renumber == "Yes":
                        rgb_n = f'{"0"*(OUTPUT_FILENAME_DIGITS-len(str(fcount+1))) + str(fcount+1)}.{rgb.split(".")[1]}'
                        ir_n = f'{"0"*(OUTPUT_FILENAME_DIGITS-len(str(fcount+1))) + str(fcount+1)}.{ir.split(".")[1]}'
                        tiff_n = f'{"0"*(OUTPUT_FILENAME_DIGITS-len(str(fcount+1))) + str(fcount+1)}.{tiff.split(".")[1]}'

                    shutil.copy(f'{folder_path}/RGB/Corrected FOV/{rgb}', f'./Output/Fire/RGB/Corrected FOV/{rgb_n}')
                    shutil.copy(f'{folder_path}/RGB/Raw/{rgb}', f'./Output/Fire/RGB/Raw/{rgb_n}')
                    shutil.copy(f'{folder_path}/Thermal/JPG/{ir}', f'./Output/Fire/Thermal/JPG/{ir_n}')
                    shutil.copy(f'{folder_path}/Thermal/Celsius TIFF/{tiff}', f'./Output/Fire/Thermal/Celsius TIFF/{tiff_n}')
                    fcount += 1
                elif label == 'No Fire':
                    if renumber == "Yes":
                        rgb_n = f'{"0"*(OUTPUT_FILENAME_DIGITS-len(str(nfcount+1))) + str(nfcount+1)}.{rgb.split(".")[1]}'
                        ir_n = f'{"0"*(OUTPUT_FILENAME_DIGITS-len(str(nfcount+1))) + str(nfcount+1)}.{ir.split(".")[1]}'
                        tiff_n = f'{"0"*(OUTPUT_FILENAME_DIGITS-len(str(nfcount+1))) + str(nfcount+1)}.{tiff.split(".")[1]}'
                    shutil.copy(f'{folder_path}/RGB/Corrected FOV/{rgb}', f'./Output/No Fire/RGB/Corrected FOV/{rgb_n}')
                    shutil.copy(f'{folder_path}/RGB/Raw/{rgb}', f'./Output/No Fire/RGB/Raw/{rgb_n}')
                    shutil.copy(f'{folder_path}/Thermal/JPG/{ir}', f'./Output/No Fire/Thermal/JPG/{ir_n}')
                    shutil.copy(f'{folder_path}/Thermal/Celsius TIFF/{tiff}', f'./Output/No Fire/Thermal/Celsius TIFF/{tiff_n}')
                    nfcount += 1
                else:
                    ulcount += 1
                    #print(f'File pair {rgb} is unlabeld and was discarded')
            # display the number of image pairs that were copied successfully, as well as how many were discarded/unlabeled
            sg.popup(f'Files exported successfully. Totals:\n\tFire Pairs: {fcount}\n\tNo Fire Pairs: {nfcount}\n\tUnlabeled Pairs (discarded): {ulcount}')

        # handle temperature threshold labeling
        elif event == '-TEMP_LABEL-':
            temp_thres = sg.popup_get_text('Please input temperature (Celsius) to threshold images with.\nSuggested val: 150\n\n\n\nCurrently uses basic threshold on max value in TIFF\nMay take 1-2 minutes for large batches of images')
            if temp_thres is None:
                continue
            # ensure the threshold value is an integer
            try:
                temp_thres = int(temp_thres)
            except:
                sg.popup("Input temperature threshold must be an integer value!")
                continue

            # loop through the tiff image files and label according to the threshold
            for ix, tiff in enumerate(tiff_image_files):
                arr = np.array(Image.open(f'{folder_path}/Thermal/Celsius TIFF/{tiff}'))
                if arr.max() >= temp_thres:
                    labels[ix] = "Fire"
                else:
                    labels[ix] = "No Fire"
            # display successfully labeled image counts, as well as unlabeled image counts
            sg.Popup(f'Successfully labeled images based on T = {temp_thres} C\nTotals:\n\tFire: {labels.count("Fire")}\n\tNo Fire: {labels.count("No Fire")}\n\tUnlabeled: {labels.count(None)}')
        # handles the help tab popup event with instructions on how to use the application
        elif event == "-HELP-":
            sg.Popup('''How to use this tool:\n
                        The Temperature Based Labeling button allows the user to specify a temperature thresold.\n
                            \tImages with a maximum temperature above the thresold will be automatticaly labeled \n
                            \t"Fire" while images with max temperatures below the thresold will be labeled "No Fire".\n\n
                        The Apply to All button (top middle) will apply the selected label in the drop down list to all\n
                            \timages. Usefull if you know the majority images are a specific label.\n\n
                        The Arrow Keys (< and >) can be used to move between image pairs in the input folder. Note that\n
                            \tthe Corrected FOV image will be displayed alongside the Thermal JPG image for each pair.\n\n
                        The Number Keys (1, 2, 3) can be used to apply labels to the displayed image pair. 1 = Fire,\n
                            \t2 = No Fire, 3 = Unlabeled\n\n
                        The Export Images w/ Labels button will copy the images to an output folder, separating the images\n
                            \twith the "Fire" label into a subfolder and the images with the "No Fire" label into a\n
                            \tdifferent subfolder. Images not labeled will not be copied to the output.\n\n
                        The Recommended workflow is as follows:\n
                            \t1) Use the Temperature Based Labeling button to apply preliminary labels to all image pairs.\n
                            \t2) Go through each image pair one by one and correct labels as necessary by visual inspection.\n
                            \t3) Export labeled images with the Export Images w/ Labels button.\n\n
                        For any further questions, email bryceh@clemson.edu''',
                    title = "Help", line_width=300)
        # handle the save state functionality, saves checkpoint of where the user is at, which can be loaded back in using the save_state.txt file
        elif event == '-SAVE_STATE-':
            confirm = sg.popup_yes_no("This will overwrite any existing ./save_state.txt file. Continue?")
            if confirm:
                with open("./save_state.txt", "w") as state:
                    state.write(f'{len(rgb_image_files)}\n')
                    state.write(f'{index}\n')
                    state.write(f'{labels}\n')  
                sg.popup('Successfully wrote state info to "./save_state.txt".', title="State Saved")
        # load state event from the save_state.txt file
        elif event == '-LOAD_STATE-':
            f = sg.popup_get_file('Please select save state file', file_types=(("TEXT FILES",'.txt'),))
            if f is None:
                sg.popup('Please select a valid save state text file.')
                continue

            # Read in the specified state file
            with open(f, 'r') as state:
                num_files = int(state.readline())
                if num_files != len(rgb_image_files):
                    sg.popup("ERROR: Selected state files indicates a different number of input files than the currently selected input folder.")
                    continue

                index = int(state.readline())
                labels_raw = state.readline()
                labels_raw = labels_raw.replace(" ", "") # Note, this also removes the space from the No Fire label
                labels_raw = labels_raw.replace("'", "")
                # [1:-2] to remove brackets and newline character from string
                labels_raw = labels_raw[1:-2].split(',')

                parsed_labels = []
                for num, entry in enumerate(labels_raw):
                    match entry:
                        case 'No Fire':
                            parsed_labels.append('No Fire')
                        case 'NoFire':
                            parsed_labels.append('No Fire')
                        case 'Fire':
                            parsed_labels.append('Fire')
                        case 'None':
                            parsed_labels.append(None)
                        case _:
                            sg.popup("ERROR: Unknown entry in the input save state labels file.")
                            continue
                # error message if the save state labels are not matching the number of input images
                if (len(parsed_labels) != len(labels)):
                    sg.popup('ERROR: Length of save state labels does not match length of input images. Failing to load state.')
                    continue

            # Copy the state file labels to current label vector:
            labels = parsed_labels
            del parsed_labels
            
            # clear loaded images that are outside buffer radius
            for ix, item in enumerate(loaded_rgb_images):
                if item is None:
                    continue
                if min(((index - ix) % len(rgb_image_files)), ((ix - index) % len(rgb_image_files))) > BUFF_RADIUS:
                    loaded_rgb_images[ix] = None
            for ix, item in enumerate(loaded_ir_images):
                if item is None:
                    continue
                if min(((index - ix) % len(rgb_image_files)), ((ix - index) % len(rgb_image_files))) > BUFF_RADIUS:
                    loaded_ir_images[ix] = None
            
            # add images in buff radius around index to queue.
            for i in range(-BUFF_RADIUS, BUFF_RADIUS + 1):
                q.put(((index+i)% len(rgb_image_files), f'{folder_path}/RGB/Corrected FOV/{rgb_image_files[(index+i)% len(rgb_image_files)]}', "rgb"))
                q.put(((index+i)% len(rgb_image_files), f'{folder_path}/Thermal/JPG/{rgb_image_files[(index+i)% len(rgb_image_files)]}', "ir"))
                q.put(((index+i)% len(rgb_image_files), f'{folder_path}/Thermal/Celsius TIFF/{rgb_image_files[(index+i)% len(rgb_image_files)].split(".")[0]}.TIFF', "tiff"))

            sg.popup('Sucessfully loaded state')
        # handle the go to event, allows user to navigate quickly to a specific image pair
        elif event == '-GOTO-':
            # get input index number to goto
            new_index = sg.popup_get_text(f"Please input pair number to goto (1-{len(rgb_image_files)})")
            if not (int(new_index) > 0 and int(new_index) < len(rgb_image_files) + 1):
                sg.popup(f'Error: The input value is outside the allowed range (1-{len(rgb_image_files)})')
                continue
            else:
                # set new index, load in appropriate images, and unload old images.
                index = int(new_index) - 1

                #clear loaded images that are outside buffer radius
                for ix, item in enumerate(loaded_rgb_images):
                    if item is None:
                        continue
                    if min(((index - ix) % len(rgb_image_files)), ((ix - index) % len(rgb_image_files))) > BUFF_RADIUS:
                        loaded_rgb_images[ix] = None
                for ix, item in enumerate(loaded_ir_images):
                    if item is None:
                        continue
                    if min(((index - ix) % len(rgb_image_files)), ((ix - index) % len(rgb_image_files))) > BUFF_RADIUS:
                        loaded_ir_images[ix] = None
                
                # add images in buff radius around index to queue.
                for i in range(-BUFF_RADIUS, BUFF_RADIUS + 1):
                    q.put(((index+i)% len(rgb_image_files), f'{folder_path}/RGB/Corrected FOV/{rgb_image_files[(index+i)% len(rgb_image_files)]}', "rgb"))
                    q.put(((index+i)% len(rgb_image_files), f'{folder_path}/Thermal/JPG/{rgb_image_files[(index+i)% len(rgb_image_files)]}', "ir"))
                    q.put(((index+i)% len(rgb_image_files), f'{folder_path}/Thermal/Celsius TIFF/{rgb_image_files[(index+i)% len(rgb_image_files)].split(".")[0]}.TIFF', "tiff"))

                sg.popup(f'Successfully set index to {index + 1}')

        # Actions completed regardless of event (or on window timeout)
        # go through loaded images buffers, removing old data and adding newly loaded images to img buffer
        for id, img in b_rgb:
            if min(((index - id) % len(rgb_image_files)), ((id - index) % len(rgb_image_files))) <= BUFF_RADIUS:
                loaded_rgb_images[id] = img
                #print(f'image {id} placed in loaded images')
            else:
                loaded_rgb_images[id] = None
            b_rgb.remove((id, img))
        for id, img in b_ir:
            if min(((index - id) % len(rgb_image_files)), ((id - index) % len(rgb_image_files))) <= BUFF_RADIUS:
                loaded_ir_images[id] = img
                #print(f'image {id} placed in loaded images')
            else:
                loaded_ir_images[id] = None
            b_ir.remove((id, img))
        for id, (temp_min, temp_avg, temp_max) in b_tiff:
            if min(((index - id) % len(rgb_image_files)), ((id - index) % len(rgb_image_files))) <= BUFF_RADIUS:
                loaded_tiff_vals[id] = (temp_min, temp_avg, temp_max)
                #print(f'tiff {id} placed in loaded tiff vals')
            else:
                loaded_tiff_vals[id] = None
            b_tiff.remove((id, (temp_min, temp_avg, temp_max)))

        #clear loaded images that are outside buffer radius
        for ix, item in enumerate(loaded_rgb_images):
            if item is None:
                continue
            if min(((index - ix) % len(rgb_image_files)), ((ix - index) % len(rgb_image_files))) > BUFF_RADIUS:
                loaded_rgb_images[ix] = None
        for ix, item in enumerate(loaded_ir_images):
            if item is None:
                continue
            if min(((index - ix) % len(rgb_image_files)), ((ix - index) % len(rgb_image_files))) > BUFF_RADIUS:
                loaded_ir_images[ix] = None

        # Update displayed images, text, and label icon
        match labels[index]:
            case 'Fire':
                window["-LABEL_IMG-"].update(source=fire_img)
            case 'No Fire':
                window["-LABEL_IMG-"].update(source=no_fire_img)
            case None:
                window["-LABEL_IMG-"].update(source=no_label_img)
        if loaded_rgb_images[index] is None:
            window["-RGB_IMAGE-"].update(source=coming_soon)
        else:
            window['-RGB_IMAGE-'].update(source=loaded_rgb_images[index])
        if loaded_ir_images[index] is None:
            window["-IR_IMAGE-"].update(source=coming_soon)
        else:
            window['-IR_IMAGE-'].update(source=loaded_ir_images[index])
        if loaded_tiff_vals[index] is None:
            window['-TEMP_STATS-'].update(f'Min Temp: ...\tAvg Temp: ...\tMax Temp: ...')
        else:
            window['-TEMP_STATS-'].update(f'Min Temp: {loaded_tiff_vals[index][0]:.2f}\tAvg Temp: {loaded_tiff_vals[index][1]:.2f}\tMax Temp: {loaded_tiff_vals[index][2]:.2f}')


        window['-FILE_NAME-'].update(f'File Name: {rgb_image_files[index]}\t Image Pair # [{index+1}/{len(rgb_image_files)}]\t Counts: ({labels.count("Fire")} F, {labels.count("No Fire")} NF, {labels.count(None)} U)')
    window.close()
    stop_workers(workers)

#main function
if __name__ == "__main__":
    main()

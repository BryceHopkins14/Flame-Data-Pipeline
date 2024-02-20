#### File name:     Raw File Sorting.py
#### Version:       1.0
#### Date:          02/19/2024
#### Creator:       Bryce Hopkins
#### Contact email: bryceh@clemson.edu
#### Purpose:       When input with some folders of raw M30T or M2EA image pairs and videos, this program will pair the videos,
####                pair the thermal images to the wide angle images if available, and regenerate the thermal images with a color
####                map (also creating tiffs). This is done for each sub folder in the input folder.
#### Instructions:  Specify input folder and output folder. The program operates assuming that there will be one layer of subfolders
####                in the input folder. Ex: Input Folder/Subfolders/Images&Videos. (or Burn/Plot/Media) The sorted images/videos will
####                be exported to appropriate output subfolders. Depending on number of images, program may take several minutes to
####                execute. Updates will be provided at cell output. NOTE: This program relies on wide angle images having "W" in the
####                filename and thermal images w/ "T" for the M30T and relies on image resolution for the M2EA. FOR THE M2EA, DO NOT
####                INPUT MORE RGB IMAGES THAN THERMALS.
####
#### WARNING:       This program has a known memory leak. As a result, it is not recommended to process >3000 image pairs at a time.
####                Largest working batch: 3000 image pairs - 40,000 MiB peak RAM usage (as reported by task manager) - 2 hour runtime

# specify the input and output folder filenames
INPUT_FOLDER = "./Input Folder/"
OUTPUT_FOLDER = "./Output Folder/"
# Current valid options: "M2EA", "M30T"
CAMERA_USED = 'M30T'
# Boolean that controls whether files will be renamed or not when placed in output folder
RENAME_FILES = True
OUTPUT_FILENAME_DIGITS = 5

# Can be set to last completed image pair number to resume image pair processing if interrupted.
RESUME_ID = 0

# import required dependencies
import os
import sys
from PIL import Image
import exif as EXIF
import datetime
import shutil
import matplotlib.pyplot as plt
import seaborn as sns
import time
import gc
import psutil

# packages from included 'dji_thermal_sdk' folder
from dji_thermal_sdk.dji_sdk import *
from dji_thermal_sdk.utility import rjpeg_to_heatmap
import dji_thermal_sdk.dji_sdk as DJI

# external library function import
from videoprops import get_video_properties

def raw_file_sorting():

    # get the timestamp at the start of the program
    print('Program start. All listed times are in reference to program start. -- time = 0.000 seconds')
    t_start = time.time_ns()
    # Initialize DJI environment
    print(
        f'Initializing DJI environment -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')
    dji_init()
    if DJI._libdirp == "":
        print('DJI environment failed to initialize.') 
        sys.exit(1)

    # Ensure that the output directory exists and is empty, if not, create the output directory
    print(f'Validating output filestructure -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    # check to see that the output directory is empty
    if len(os.listdir(OUTPUT_FOLDER)) > 0 and RESUME_ID == 0:
        print(
            'Error: Output folder is not empty. Make sure old data is removed before use.')
        sys.exit(1)
    #If the output folder contains files and the resume ID is set to 0 or higher
    elif len(os.listdir(OUTPUT_FOLDER)) > 0 and RESUME_ID >= 0:
        print(f'WARNING: Output dir not empty and Resume ID set to {RESUME_ID}. Proceed with caution.')

    # Loop through input folder, then loop through subfolders
    print(f'{len(os.listdir(INPUT_FOLDER))} subfolders detected! Starting processing now. -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')
    for id_subfolder, subfolder in enumerate(os.listdir(INPUT_FOLDER)):
        print(f'For subfolder {subfolder} [{id_subfolder+1}/{len(os.listdir(INPUT_FOLDER))}], {len(os.listdir(f"{INPUT_FOLDER}{subfolder}/"))} files detected. Starting processing. -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')

        # create filename and datetime lists
        rgb_image_filenames = []
        rgb_image_datetimes = []
        ir_image_filenames = []
        ir_image_datetimes = []
        rgb_video_filenames = []
        rgb_video_datetimes = []
        ir_video_filenames = []
        ir_video_datetimes = []

        # iterate over all files in the input subfolders
        for id_file, file in enumerate(os.listdir(f'{INPUT_FOLDER}{subfolder}/')):
            # M30T Camera section
            if CAMERA_USED == "M30T":
                # check for .mp4 video file(s)
                if file.endswith('.MP4'):
                    # Distinguish between RGB (W) and Thermal (T) labeled videos
                    if 'T' in file:
                        # Add the Thermal (T) video filename and timestamp to the respective lists
                        ir_video_filenames.append(file)
                        ir_video_datetimes.append(datetime.datetime.fromtimestamp(
                            os.path.getmtime(f'{INPUT_FOLDER}{subfolder}/{file}')))
                    elif 'W' in file:
                        # Add the RGB (W) labeled video filename and timestamp to the respective lists
                        rgb_video_filenames.append(file)
                        rgb_video_datetimes.append(datetime.datetime.fromtimestamp(
                            os.path.getmtime(f'{INPUT_FOLDER}{subfolder}/{file}')))
                    # else: video is either screen or zoom, which are discarded for now
                # check for .jpg image files
                elif file.endswith('.JPG'):
                    # open image file in binary read mode and extract metadata using EXIF
                    with open(f'{INPUT_FOLDER}{subfolder}/{file}', 'rb') as src:
                        img = EXIF.Image(src)
                        # If image does not have EXIF metadata it is excluded
                        if not img.has_exif:
                            print(
                                f'Image {file} does not have exif data and will be excluded. NOTE: THIS CAN CAUSE DUPLICATE PAIRINGS')
                            continue
                    # Distinguish between RGB (W) and Thermal (T) labeled images
                    if 'T' in file:
                        # Add the Thermal (T) image filename and timestamp to the respective lists
                        ir_image_filenames.append(file)
                        ir_image_datetimes.append(datetime.datetime.strptime(
                            img.datetime, "%Y:%m:%d %H:%M:%S"))
                    elif 'W' in file:
                        # Add the RGB (W) image filename and timestamp to the respective lists
                        rgb_image_filenames.append(file)
                        rgb_image_datetimes.append(datetime.datetime.strptime(
                            img.datetime, "%Y:%m:%d %H:%M:%S"))
                    # delete the img object after getting filename and timestamp to save memory
                    # does not delete the original image file, just the img object in code
                    del img
                    # else: image is either screen or zoom, which are discarded for now.
                # else: file is not a video or image and will be excluded
            # M2EA Camera section
            elif CAMERA_USED == "M2EA":
                # check for .mp4 video file(s)
                if file.endswith('.MP4'):
                    # extract various video properties using get_video_properties()
                    vid_props = get_video_properties(
                        f'{INPUT_FOLDER}{subfolder}/{file}')

                    # separate thermal/rgb videos based on resolution
                    if vid_props['height'] == 512:
                        # Add the Thermal video filename and timestamp to the respective lists
                        ir_video_filenames.append(file)
                        ir_video_datetimes.append(datetime.datetime.fromtimestamp(
                            os.path.getmtime(f'{INPUT_FOLDER}{subfolder}/{file}')))
                    else: # Assumes that only rgb/ir videos exist in input folder
                        # Add the RGB video filename and timestamp to the respective lists
                        rgb_video_filenames.append(file)
                        rgb_video_datetimes.append(datetime.datetime.fromtimestamp(
                            os.path.getmtime(f'{INPUT_FOLDER}{subfolder}/{file}')))
                # check for .jpg image files
                elif file.endswith('.JPG'):
                    # try to open the image and extract metadata with EXIF, if it cannot be opened it is excluded
                    try:
                        with open(f'{INPUT_FOLDER}{subfolder}/{file}', 'rb') as src:
                            img = EXIF.Image(src)
                    except:
                        print(
                            f'Image {file} cannot be opened and will be excluded! This can cause duplicate/missing pairings!')
                        continue
                    # If image does not have EXIF metadata it is excluded
                    if not img.has_exif:
                        print(
                            f'Image {file} does not have exif data and will be excluded. NOTE: THIS CAN CAUSE DUPLICATE PAIRINGS')
                        continue


                   #check for image height equal to 512 pixels or not
                    if img.image_height != 512:
                        print('Thermal image height must be 512 pixels, exiting program.')
                        sys.exit(1)

                    # separate thermal/rgb images based on resolution
                    if img.image_height == 512:
                        # Add the Thermal image filename and timestamp to the respective lists
                        ir_image_filenames.append(file)
                        ir_image_datetimes.append(datetime.datetime.strptime(
                            img.datetime, "%Y:%m:%d %H:%M:%S"))
                    else:  # Assumes that only rgb/ir images exist in input folder
                        # Add the RGB image filename and timestamp to the respective lists
                        rgb_image_filenames.append(file)
                        rgb_image_datetimes.append(datetime.datetime.strptime(
                            img.datetime, "%Y:%m:%d %H:%M:%S"))
                    # delete the img object after getting filename and timestamp to save memory
                    # does not delete the original image file, just the img object in code
                    del img
                # else: file is not a video or image and will be excluded

        # print number images/videos that have been categorized as RGB / IR and the time it took to process
        print(f'\tAll {len(os.listdir(f"{INPUT_FOLDER}{subfolder}"))} files in subfolder [{id_subfolder+1}/{len(os.listdir(INPUT_FOLDER))}] have been categorized as rgb/ir. -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')

        # Go through datetime/filename lists and pair rgb media to the corresponding ir media (timestamps)
        image_pairs = []
        video_pairs = []
        for id, rgb_datetime in enumerate(rgb_image_datetimes):
            image_pairs.append((rgb_image_filenames[id], ir_image_filenames[min(range(len(
                ir_image_datetimes)), key=lambda j: abs(ir_image_datetimes[j]-rgb_datetime))]))

        for id, rgb_datetime in enumerate(rgb_video_datetimes):
            video_pairs.append((rgb_video_filenames[id], ir_video_filenames[min(range(len(
                ir_video_datetimes)), key=lambda j: abs(ir_video_datetimes[j]-rgb_datetime))]))

        # print the number of paired images / videos and the time it took to process
        print(f'\tFiles have been paired. {len(image_pairs)} image pairs and {len(video_pairs)} video pairs created. -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')

        # create output folder for videos and images
        os.makedirs(f'{OUTPUT_FOLDER}{subfolder}/Videos/Thermal', exist_ok=True)
        os.makedirs(f'{OUTPUT_FOLDER}{subfolder}/Videos/RGB', exist_ok=True)
        os.makedirs(f'{OUTPUT_FOLDER}{subfolder}/Images/Thermal/JPG', exist_ok=True)
        os.makedirs(f'{OUTPUT_FOLDER}{subfolder}/Images/Thermal/Celsius TIFF', exist_ok=True)
        os.makedirs(f'{OUTPUT_FOLDER}{subfolder}/Images/RGB/Corrected FOV', exist_ok=True)
        os.makedirs(f'{OUTPUT_FOLDER}{subfolder}/Images/RGB/Raw', exist_ok=True)

        # print the current state of the code, start copying videos to output folder
        print(f'\tOutput directories created. Now copying videos to output -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')

        # Rename all ir media to rgb media filenames for pairing
        # copy videos to output folders
        for ix, (rgb_filename, ir_filename) in enumerate(video_pairs):
            rgb_filename_n = rgb_filename
            if RENAME_FILES:
                # create new filename and pad with 0's
                rgb_filename_n = f'{"0"*(OUTPUT_FILENAME_DIGITS-len(str(ix+1))) + str(ix+1)}.{rgb_filename.split(".")[1]}'
            # copy the RGB / IR video to the output folder with the new filename
            shutil.copy(f'{INPUT_FOLDER}{subfolder}/{rgb_filename}',
                        f'{OUTPUT_FOLDER}{subfolder}/Videos/RGB/{rgb_filename_n}')
            shutil.copy(f'{INPUT_FOLDER}{subfolder}/{ir_filename}',
                        f'{OUTPUT_FOLDER}{subfolder}/Videos/Thermal/{rgb_filename_n}')

        # print the number of video pairs that have been copied and the time it took to process
        print(f'\tAll {len(video_pairs)} video pairs have been coppied to output dir. -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')
        print(f'\tNow beginning image pair processing')
        # continue processing images
        for pair_id, (rgb_filename, ir_filename) in enumerate(image_pairs):
            try:
                # checkpoint for first image processed (start)
                if pair_id == 0:
                    checkpoint_time = time.time_ns()
                    print(f'\t[0/{len(image_pairs)}] processed.')
                # print information about processing every 50 images
                if pair_id % 50 == 0 and not pair_id == 0:
                    print(f'\t[{pair_id}/{len(image_pairs)}] processed. Avg time per pair was {(time.time_ns()-checkpoint_time)/1e9/50:4.3f} s, Current Mem Usage: {psutil.Process(os.getpid()).memory_info().rss / 1024 ** 2 :.2f} MiB -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')
                    checkpoint_time = time.time_ns()

                # resume processing from specified ID
                if pair_id + 1 <= RESUME_ID:
                    continue
                
                # reset new filename variable
                rgb_filename_n = rgb_filename
                if RENAME_FILES:
                    # set variable for new image filename
                    rgb_filename_n = f'{"0"*(OUTPUT_FILENAME_DIGITS-len(str(pair_id+1))) + str(pair_id+1)}.{rgb_filename.split(".")[1]}'

                # create log entry
                with open('log.txt', 'a+') as f:
                    f.write(f'pair {pair_id}: ({rgb_filename, ir_filename}) -> ({rgb_filename_n})\n')

                # extract thermal vals from ir images:
                temp_arr = rjpeg_to_heatmap(
                    f'{INPUT_FOLDER}{subfolder}/{ir_filename}', dtype='float32')
                # recreate thermal jpg from heatmap. This gets rid of any DJI superresolution or digital zoom. Also removes watermark and changes color mapping.
                fig = plt.figure(dpi=72, figsize=(
                    640/72, 512/72), frameon=False)
                fig.add_axes([0, 0, 1, 1])
                ax = sns.heatmap(temp_arr, cmap='inferno', cbar=False)  # NOTE: this appears to have a minor memory leak! ax.cla + gc.collect appears to help, though isnt perfect
                ax.set_xticks([])
                ax.set_yticks([])
                plt.savefig(
                    f'{OUTPUT_FOLDER}{subfolder}/Images/Thermal/JPG/{rgb_filename_n}', dpi=72)
                ax.cla()
                del ax
                plt.cla()
                plt.clf()
                plt.close('all')
                del fig

                # grab exif from original thermal image.
                original_ir_img = Image.open(
                    f'{INPUT_FOLDER}{subfolder}/{ir_filename}')

                # copy exif to newly created thermal jpg
                ir_img = Image.open(
                    f'{OUTPUT_FOLDER}{subfolder}/Images/Thermal/JPG/{rgb_filename_n}')
                ir_img.save(f'{OUTPUT_FOLDER}{subfolder}/Images/Thermal/JPG/{rgb_filename_n}',
                            exif=original_ir_img.info['exif'])
                ir_img.close()
                original_ir_img.close()
                # Save heatmap as TIFF
                tiff = Image.fromarray(temp_arr)
                tiff.save(
                    f'{OUTPUT_FOLDER}{subfolder}/Images/Thermal/Celsius TIFF/{rgb_filename_n.split(".")[0]}.TIFF')
                tiff.close()
                del temp_arr

                # FOV CORRECTIONS HERE
                rgb_img = Image.open(
                    f'{INPUT_FOLDER}{subfolder}/{rgb_filename}')
                # M30T camera images
                if CAMERA_USED == "M30T":
                    # NOTE: The following crop transform seems to work fairly well, though cannot deal w/ lens distortions.
                    #       Crop params were found through iterative improvement (hence the many + & - terms). Aspect ratio must be preserved or a resize operation must occur to preserve 1:1 correlation.
                    # Left, Upper, Right, Lower
                    # crop image
                    rgb_img = rgb_img.crop(
                        (640+40-(60), 412+30+12, 4000-640-40-40-40-16-16+(40), 3000-412-30-30-30-12))
                    # resize image
                    rgb_img = rgb_img.resize((640, 512))
                # M2EA camera images
                elif CAMERA_USED == "M2EA":
                    # rgb_img = rgb_img.crop((640+40-(60), 412+30+12, 4000-640-40-40-40-16-16+(40), 3000-412-30-30-30-12))
                    #crop image
                    rgb_img = rgb_img.crop(
                        (1280+80, 824, 8000-1280+80, 6000-824))
                    #resize image
                    rgb_img = rgb_img.resize((640, 512))

                # Copy cropped rgb image to output w/ orginal exif data
                rgb_img.save(
                    f'{OUTPUT_FOLDER}{subfolder}/Images/RGB/Corrected FOV/{rgb_filename_n}', exif=rgb_img.info['exif'])
                rgb_img.close()

                # Now copy original rgb image to output
                shutil.copy(f'{INPUT_FOLDER}{subfolder}/{rgb_filename}',
                            f'{OUTPUT_FOLDER}{subfolder}/Images/RGB/Raw/{rgb_filename_n}')

                gc.collect()
            # exception if a file pair failed
            except:
                print(
                    f'FAILED at file pair sf= {subfolder}, pid= {pair_id}, rgbf= {rgb_filename}, irf= {ir_filename}')
                exit(1)
        # print status when the processing is complete for a certain folder
        print(f'\tImage processing complete for folder [{id_subfolder +1}/{len(os.listdir(INPUT_FOLDER))}]. -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')
    # print status when all processing is complete
    print(f'All processing complete. Program finished successfully. -- time = {(time.time_ns()-t_start)/1e9:4.3f} seconds')

#main function, run the raw_file_sorting() function
if __name__ == '__main__':
    raw_file_sorting()
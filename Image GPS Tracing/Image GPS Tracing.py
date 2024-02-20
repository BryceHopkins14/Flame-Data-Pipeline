#### File name:     Image GPS Tracing.py
#### Last Updated:          02/19/2024
#### Creator:       Bryce Hopkins
#### Purpose:       Sorts a directory of images by date-time and returns a csv of filenames, GPS coords, and datetime for each image found in the directory
#### Instructions:  Specify source image folder as well as output csv filename.

'''
Create source and output directory variables

Source Directory may be any directory where images are stored.
Image GPS Tracing tool will iterate through all images in the
specified directory.
'''

SOURCE_DIR = './Images/Fire/RGB/'
OUTPUT_CSV_PATH = './GPS_Traces.csv'

#import required libraries
import os
from exif import Image
import csv
from datetime import datetime

'''
Function that will convert latitude or longitude in hours-minutes-seconds (HMS) format 
to decimal degrees format 

Variable coords is expected to be a list with three values
    1.) Hours
    2.) Minutes
    3.) Seconds

Variable ref is expected to be a 'W' or 'S' character representing 
West or South direction
'''


def decimal_coords_from_HMS(coords, ref):
    decimal_degrees = coords[0] + coords[1] / 60 + coords[2] / 3600
    if ref == 'W' or ref == 'S':
        decimal_degrees = -decimal_degrees
    return decimal_degrees


'''
Function that will take in a path to an image file, read EXIF metadata, 
and return the filename, datetime, decimal degrees latitude and longitude, 
and the GPS altitude
'''


def image_coordinates(image_path):
    # open image file in binary read mode
    with open(image_path, 'rb') as src:
        # create Image object from the file
        img = Image(src)
    # check to see if the image contains EXIF metadata
    if img.has_exif:
        try:
            img.gps_longitude
            # Conver the latitude and longitude from HMS to decimal degrees
            coords = (decimal_coords_from_HMS(img.gps_latitude,
                                              img.gps_latitude_ref),
                      decimal_coords_from_HMS(img.gps_longitude,
                                              img.gps_longitude_ref))
            # return tuple: name, datetime, coords, and altitude
            return (src.name, img.datetime_original, coords, img.gps_altitude)

        # error if GPS coordinates not found in EXIF metadata
        except AttributeError:
            print('Image lacks GPS coordinates in exif')
    # error if there is no EXIF metadata in Image file
    else:
        print('The Image has no EXIF information')


if __name__ == "__main__":
    #create list variables
    paths = []
    filenames = []
    datetimes = []
    lats = []
    lons = []
    alts = []

    print('Starting Image GPS Tracing Tool.')
    print(f'Extracting EXIF metadata from images in {SOURCE_DIR}')
    # Pull data from exifs of images in source dir
    for file in os.listdir(SOURCE_DIR):
        img_stats = image_coordinates(SOURCE_DIR + file)
        paths.append(img_stats[0])
        filenames.append(file)
        datetimes.append(img_stats[1])
        lats.append(img_stats[2][0])
        lons.append(img_stats[2][1])
        alts.append(img_stats[3])

    # convert exif times to datetimes for sorting
    datetimes = [datetime.strptime(x, "%Y:%m:%d %H:%M:%S") for x in datetimes]

    # sort data by datetime
    print('Sorting images by datetime.')
    sorted_data = sorted(zip(paths, filenames, datetimes, lats, lons, alts), key=lambda x:x[2])

    paths = [p for p, f, d, la, lo, a in sorted_data]
    filenames = [f for p, f, d, la, lo, a in sorted_data]
    datetimes = [d for p, f, d, la, lo, a in sorted_data]
    lats = [la for p, f, d, la, lo, a in sorted_data]
    lons = [lo for p, f, d, la, lo, a in sorted_data]
    alts = [a for p, f, d, la, lo, a in sorted_data]

    # convert datetimes back to strings
    datetimes = [datetime.strftime(x, "%Y:%m:%d %H:%M:%S") for x in datetimes]

    # log data into csv
    print(f'Logging data to {OUTPUT_CSV_PATH}')
    with open(OUTPUT_CSV_PATH, 'w', newline='') as log:
        log_writer = csv.writer(log)

        # write header
        header = ['Datetime','Latitude','Longitude','Altitude [m ASL]','Image Filename','Image Path']
        log_writer.writerow(header)

        # write data
        for i in range(0, len(paths)):
            log_writer.writerow([datetimes[i],
                                 lats[i],
                                 lons[i],
                                 alts[i],
                                 filenames[i],
                                 paths[i]])
    print('Image GPS Tracing Tool completed.')
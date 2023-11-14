# Automatic toolhead offset calibration using computer vision for Klipper

CVToolheadCalibration is an extension for IDEX printers running klipper that adds functionality to calibrate toolhead offset using a USB microscope/webcam. With this extension you can easily calibrate the toolhead offsets. 

Adds the following commands to klipper:
  - `CV_TEST`, debug command to check if the script works and OpenCV versions
  - `CV_CENTER_TOOLHEAD`, moves the current toolhead to the configured camera_position
  - `CV_SIMPLE_NOZZLE_POSITION`, checks if a nozzle is detected in the current nozzle cam image
  - `CV_CALIB_NOZZLE_PX_MM`, moves the current active toolhead to various positions around the center to calibrate movement data
  - `CV_CALIB_OFFSET`, The main function, runs the calibration function on the T0 toolhead, then switches to T1, calibrates the offset and moves T1 there to compare

Both of the calibration commands have optional command line parameters
  - CALIB_VALUE=0.5, override the default or configured CALIB_VALUE value
  - CALIB_ITERATIONS=5, override the default or configured CALIB_ITERATIONS value
  - PRINT_POSITIONS=1, only for CV_CALIB_NOZZLE_PX_MM, returns the raw MM and PX values of detections used for calibration

!!! !!! !!! !!! !!! 
This is alpha software and only meant for advanced users!
Please only use while supervising your printer, 
may produce unexpected results, 
be ready to hit 'emergency stop' at any time!
!!! !!! !!! !!! !!! 

## How to install

Connect to your klipper machine using SSH, run these commands

```
cd ~/
git clone https://github.com/cawmit/klipper_cv_toolhead_calibration.git
bash ~/klipper_cv_toolhead_calibration/install.sh
```

This will clone the repository and execute the install script.

To enable automatic updates using moonraker, add the following to your moonraker config:

```
[update_manager cv_toolhead_calibration]
type: git_repo
path: ~/klipper_cv_toolhead_calibration
origin: https://github.com/cawmit/klipper_cv_toolhead_calibration.git
install_script: install.sh
requirements: requirements.txt
managed_services: klipper
```

## Configuration

```
[cv_toolhead_calibration]
nozzle_cam_url: http://localhost:8081?action=stream
camera_position: 75,75 # X,Y mm values of the T0 toolhead visible in the center of the nozzle camera
```

## First time running after install

1. Run the `CV_CENTER_TOOLHEAD` command to center the toolhead
2. Connect and open the web page to view the nozzle cam
3. Position the camera so that the nozzle is roughly in the center of the image
4. Run the `CV_SIMPLE_NOZZLE_POSITION` command, this should return your nozzle position in the image
5. If everything works, you can run `CV_CALIB_OFFSET` 

## Special thanks
 - This extension is heavily inspired by TAMV. TAMV is an extension for Duet based printers which also uses computer vision to align toolheads. For more information see: https://github.com/HaythamB/TAMV
 - The user Dorkscript from the DOOMCUBE discord, who tested early versions of the extension and gave very valuable feedback

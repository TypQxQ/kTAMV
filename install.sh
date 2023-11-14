#!/bin/bash

KLIPPER_PATH="${HOME}/klipper"
EXTENSION_PATH="${HOME}/klipper_cv_toolhead_calibration_for_ktcc"

PKGLIST="python-opencv"

link_extension()
{
    echo "Linking extension to Klipper..."
    ln -sf "${EXTENSION_PATH}/cv_toolhead_calibration.py" "${KLIPPER_PATH}/klippy/extras/cv_toolhead_calibration.py"
}

restart_klipper()
{
    echo "Restarting Klipper..."
    sudo systemctl restart klipper
}

verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "This script must not run as root"
        exit -1
    fi
}

# Force script to exit if an error occurs
set -e

# Parse command line arguments
while getopts "k:" arg; do
    case $arg in
        k) KLIPPER_PATH=$OPTARG;;
    esac
done

verify_ready
link_extension
restart_klipper

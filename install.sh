#!/bin/bash

#
# The responsibility of this script is to bootstrap the setup by installing the required system libs,
# virtual environment, and py requirements. The core of the setup logic is done by the PY install script.
#

# Set this to terminate on error.
set -e

# Get the root path of the repo, aka, where this script is executing
KTAMV_REPO_DIR=$(realpath $(dirname "$0"))

# This is the root of where our py virtual env will be.
KTAMV_ENV="${HOME}/ktamv-env"

# This is where Klipper is installed
KLIPPER_HOME="${HOME}/klipper"

# This is where the extension are downloaded to, a subdirectory of the repo.
EXTENSION_PATH="${KTAMV_REPO_DIR}/extension"

# This is where the server is downloaded to, a subdirectory of the repo.
SERVER_PATH="${KTAMV_REPO_DIR}/server"

# This is where Moonraker is installed
MOONRAKER_HOME="${HOME}/moonraker"

# This is where Klipper config files are stored
KLIPPER_CONFIG_HOME="${HOME}/printer_data/config"

# This is where Klipper config files are stored
KLIPPER_ENV="${HOME}/klippy-env"

# This is where Klipper logs are stored
KLIPPER_LOGS_HOME="${HOME}/printer_data/logs"

# This is where Klipper config files were stored before the 0.10.0 release
OLD_KLIPPER_CONFIG_HOME="${HOME}/klipper_config"

# Port to run the server on
PORT="${PORT:-8085}"

# Path to the systemd directory
SYSTEMDDIR="/etc/systemd/system"

# Path to the moonraker asvc file where services are defined
MOONRAKER_ASVC=~/printer_data/moonraker.asvc

# Agree to send images to the developer
SEND_IMAGES="false"


# Note that this is parsed by the update process to find and update required system packages on update!
# This var name MUST BE `PKGLIST`!!
#
# The python requirements are for the installer and plugin
# The virtualenv is for our virtual package env we create
# The curl requirement is for some things in this script.
# OpenCV is used for the image processing
# NumpPy is used for mathemtical operations
# PIL is used for image processing
# Flask is used for the webserver
# Waitress is used to serve the Flask webserver with less resources
# Jinja2 is used by the Flask webserver
# libatlas is used by NumPy
# matplotlib is to find usable fonts
PKGLIST="python3 python3-pip virtualenv curl python3-matplotlib python3-numpy python3-opencv python3-pil python3-flask libatlas-base-dev python3-waitress python3-jinja2"


#
# Console Write Helpers
#
c_default=$(echo -en "\e[39m")
c_green=$(echo -en "\e[92m")
c_yellow=$(echo -en "\e[93m")
c_magenta=$(echo -en "\e[35m")
c_red=$(echo -en "\e[91m")
c_cyan=$(echo -en "\e[96m")

log_header()
{
    echo -e "${c_magenta}$1${c_default}"
}

log_important()
{
    echo -e "${c_yellow}$1${c_default}"
}

log_error()
{
    log_blank
    echo -e "${c_red}$1${c_default}"
    log_blank
}

log_info()
{
    echo -e "${c_green}$1${c_default}"
}

log_blank()
{
    echo ""
}

#
# Logic to create / update our virtual py env
#
install_or_update_python_env()
{
    log_header "Checking Python Virtual Environment For kTAMV..."
    # If the service is already running, we can't recreate the virtual env
    # so if it exists, don't try to create it.
    if [ -d $KTAMV_ENV ]; then
        log_error "Virtual environment found at ${KTAMV_ENV}, skipping creation."
        # This virtual env refresh fails on some devices when the service is already running, so skip it for now.
        # This only refreshes the virtual environment package anyways, so it's not super needed.
        #log_info "Virtual environment found, updating to the latest version of python."
        #python3 -m venv --upgrade "${KTAMV_ENV}"
    else
        log_info "No virtual environment found, creating one now at ${KTAMV_ENV}."
        mkdir -p "${KTAMV_ENV}"
        virtualenv -p /usr/bin/python3 --system-site-packages "${KTAMV_ENV}"
    fi
}

#
# Logic to make sure all of our required system packages are installed.
#
install_or_update_system_dependencies()
{
    log_header "Checking required system packages are installed..."
    log_important "You might be asked for your system password - this is required to install the required system packages."

    # It seems a lot of printer control systems don't have the date and time set correctly, and then the fail
    # getting packages and other downstream things. We will use OctoEverywhere HTTP API to set the current UTC time.
    # Note that since cloudflare will auto force http -> https, we use https, but ignore cert errors, that could be
    # caused by an incorrect date.
    # Note some companion systems don't have curl installed, so this will fail.
    sudo date -s `curl --insecure 'https://octoeverywhere.com/api/util/date' 2>/dev/null` || true

    # These we require to be installed in the OS.
    # Note we need to do this before we create our virtual environment
    sudo apt update
    sudo apt install --yes ${PKGLIST}
    log_info "System package install complete."

    # The PY lib Pillow depends on some system packages that change names depending on the OS.
    # The easiest way to do this was just to try to install them and ignore errors.
    # Most systems already have the packages installed, so this only fixes edge cases.
    # Notes on Pillow deps: https://pillow.readthedocs.io/en/latest/installation.html
    log_info "Ensuring zlib is install for Pillow, it's ok if this package install fails."
    sudo apt install --yes zlib1g-dev 2> /dev/null || true
    sudo apt install --yes zlib-devel 2> /dev/null || true
}

#
# Logic to install or update the virtual env and all of our required packages.
#

#
# Logic to ensure the user isn't trying to use this script to setup in OctoPrint.
#
check_for_ktamv()
{
    # Do a basic check to see if anything is running on the specified port.
    if curl -s "http://127.0.0.1:${PORT}" >/dev/null ; then
        log_important "Just a second... kTAMV or something else was detected running on port ${PORT}."
        log_blank
        log_important "This install script is used to install kTAMV for Mainsail, Fluidd, Moonraker, etc."
        log_blank
        log_blank
        log_info "Stopping install process."
        exit 0
    fi
}

# 
# Logic to check if Klipper is installed
# 
check_klipper() {
    # Check if Klipper is installed
    log_header "Checking if Klipper is installed..."
    if [ "$(sudo systemctl list-units --full -all -t service --no-legend | grep -F "klipper.service")" ]; then
        log_important "${INFO}Klipper service found"
    else
        log_error "${ERROR}Klipper service not found! Please install Klipper first"
        exit -1
    fi
}

# 
# Logic to link the extension to Klipper
# 
link_extension()
{
    log_header "Linking extension to Klipper..."
    log_blank
    ln -sf "${EXTENSION_PATH}/ktamv.py" "${KLIPPER_HOME}/klippy/extras/ktamv.py"
    ln -sf "${EXTENSION_PATH}/ktamv_utl.py" "${KLIPPER_HOME}/klippy/extras/ktamv_utl.py"
}

# 
# Logic to verify the home directories
# 
verify_home_dirs() {
    log_header "Verifying home directories..."
    log_blank
    if [ ! -d "${KLIPPER_HOME}" ]; then
        log_error "Klipper home directory (${KLIPPER_HOME}) not found. Use '-k <dir>' option to override"
        exit -1
    fi
    if [ ! -d "${KLIPPER_CONFIG_HOME}" ]; then
        if [ ! -d "${OLD_KLIPPER_CONFIG_HOME}" ]; then
            log_error "Klipper config directory (${KLIPPER_CONFIG_HOME} or ${OLD_KLIPPER_CONFIG_HOME}) not found. Use '-c <dir>' option to override"
            exit -1
        fi
        KLIPPER_CONFIG_HOME="${OLD_KLIPPER_CONFIG_HOME}"
    fi
    log_info "Klipper config directory (${KLIPPER_CONFIG_HOME}) found"

    if [ ! -d "${MOONRAKER_HOME}" ]; then
        log_error "Moonraker home directory (${MOONRAKER_HOME}) not found. Use '-m <dir>' option to override"
        exit -1
    fi

    if [ ! -d "${KLIPPER_ENV}" ]; then
        log_error "Klipper virtual evniroment directory (${KLIPPER_ENV}) not found. Use '-j <dir>' option to override"
        exit -1
    fi

    if [ ! -d "${SYSTEMDDIR}" ]; then
        log_error "System directory (${SYSTEMDDIR}) not found. Use '-s <dir>' option to override"
        exit -1
    fi

    
}

restart_klipper()
{
    log_header "Restarting Klipper..."
    sudo systemctl restart klipper
}

restart_moonraker()
{
    log_header "Restarting Moonraker..."
    sudo systemctl restart moonraker
}

verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        log_error "This script must not run as root"
        exit -1
    fi
}

# 
# Logic to install the update manager to Moonraker
# 
install_update_manager() {
    log_header "Adding update manager to moonraker.conf"
    dest=${KLIPPER_CONFIG_HOME}/moonraker.conf
    if test -f $dest; then
        # Backup the original printer.cfg file
        next_dest="$(nextfilename "$dest")"
        log_info "Copying original moonraker.conf file to ${next_dest}"
        cp ${dest} ${next_dest}
        already_included=$(grep -c '\[update_manager ktamv\]' ${dest} || true)
        if [ "${already_included}" -eq 0 ]; then
            echo "" >> "${dest}"    # Add a blank line
            echo "" >> "${dest}"    # Add a blank line
            echo -e "[update_manager ktamv]]" >> "${dest}"    # Add the section header
            echo -e "type: git_repo" >> "${dest}"
            echo -e "path: ~/kTAMV" >> "${dest}"
            echo -e "origin: https://github.com/TypQxQ/kTAMV.git" >> "${dest}"
            echo -e "primary_branch: main" >> "${dest}"
            echo -e "install_script: install.sh" >> "${dest}"
            echo -e "managed_services: klipper" >> "${dest}"
        else
            log_error "[update_manager ktamv] already exists in moonraker.conf - skipping installing it there"
        fi

    else
        log_error "moonraker.conf not found!"
    fi
}

# 
# Logic to install the configuration to Klipper
# 
install_klipper_config() {
    log_header "Adding configuration to printer.cfg"

    # Add configuration to printer.cfg if it doesn't exist
    dest=${KLIPPER_CONFIG_HOME}/printer.cfg
    if test -f $dest; then
        # Backup the original printer.cfg file
        next_dest="$(nextfilename "$dest")"
        log_info "Copying original printer.cfg file to ${next_dest}"
        cp ${dest} ${next_dest}

        # Add the configuration to printer.cfg
        # This example assumes that that both the server and the webcam stream are running on the same machine as Klipper
        already_included=$(grep -c '\[ktamv\]' ${dest} || true)
        if [ "${already_included}" -eq 0 ]; then
            echo "" >> "${dest}"    # Add a blank line
            echo "" >> "${dest}"    # Add a blank line
            echo -e "[ktamv]" >> "${dest}"    # Add the section header
            echo -e "nozzle_cam_url: http://localhost/webcam/snapshot?max_delay=0" >> "${dest}"   # Add the address of the webcam stream that will be accessed by the server
            echo -e "server_url: http://localhost:${PORT}" >> "${dest}"    # Add the address of the kTAMV server that will be accessed Klipper
            echo -e "move_speed: 1800" >> "${dest}"   # Add the speed at which the toolhead moves when aligning
            echo -e "send_frame_to_cloud: ${SEND_IMAGES}" >> "${dest}"   # Add the speed at which the toolhead moves when aligning
            

            log_info "Added kTAMV configuration to printer.cfg"
            log_important "Please check the configuration in printer.cfg and adjust it as needed"
            # Restart Klipper
            restart_klipper
        else
            log_error "[ktamv] already exists in printer.cfg - skipping adding it there"
        fi
    else
        log_error "File printer.cfg file not found! Cannot add kTAMV configuration. Do it manually."
    fi

    # Add the inclusion of macros.cfg to printer.cfg if it doesn't exist
    already_included=$(grep -c '\[include ktamv_macros.cfg\]' ${dest} || true)
    if [ "${already_included}" -eq 0 ]; then
        echo "" >> "${dest}"    # Add a blank line
        echo "" >> "${dest}"    # Add a blank line
        echo -e '\[include ktamv-macros.cfg\]' >> "${dest}"    # Add the section header
    else
        log_error "[include ktamv-macros.cfg] already exists in printer.cfg - skipping adding it there"
    fi
    
    if [ ! -f "${KLIPPER_CONFIG_HOME}/ktamv-macros.cfg" ]; then
        log_info "Copying ktamv-macros.cfg to ${KLIPPER_CONFIG_HOME}"
        cp ${KTAMV_REPO_DIR}/ktamv-macros.cfg ${KLIPPER_CONFIG_HOME}
    else
        log_error "[include ktamv-macros.cfg] already exists in printer.cfg - skipping adding it there"
    fi
}

# 
# Logic to install kTAMV as a systemd service
# 
install_sysd(){
    log_header "Installing system start script so the server can start from Moonrker..."

    # Comand to launch the server to be used in the service file
    LAUNCH_CMD="${KTAMV_ENV}/bin/python ${KTAMV_REPO_DIR}/server/ktamv_server.py --port ${PORT}"

    # Create systemd service file
    SERVICE_FILE="${SYSTEMDDIR}/kTAMV_server.service"

    # If the service file already exists, don't overwrite
    [ -f $SERVICE_FILE ] && return
    sudo /bin/sh -c "cat > ${SERVICE_FILE}" << EOF
#Systemd service file for kTAMV_server
[Unit]
Description=Server component for kTAMV. A tool alignment tool for Klipper using machine vision.
After=network-online.target moonraker.service

[Install]
WantedBy=multi-user.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$KTAMV_REPO_DIR/server
ExecStart=$LAUNCH_CMD
Restart=always
RestartSec=10
EOF
    # Use systemctl to enable the klipper systemd service script
        sudo systemctl enable kTAMV_server.service
        sudo systemctl daemon-reload

        # Start the server
        start_server

        # Add kTAMV to the service list of Moonraker
        add_to_asvc

        # Restart Moonraker
        restart_moonraker
}

add_to_asvc()
{
    log_header "Trying to add kTAMV_server to service list"
    if [ -f $MOONRAKER_ASVC ]; then
        log_info "moonraker.asvc was found"
        if ! grep -q kTAMV_server $MOONRAKER_ASVC; then
            log_info "moonraker.asvc does not contain 'kTAMV_server'! Adding it..."
            echo "" >> $MOONRAKER_ASVC    # Add a blank line
            echo -e "kTAMV_server" >> $MOONRAKER_ASVC
        fi
    else
        log_error "moonraker.asvc not found! Add 'kTAMV_server' to the service list manually"
    fi
}

start_server()
{
    log_header "Launching kTAMV Server..."
    sudo systemctl restart kTAMV_server
}


# 
# Logic to ask a question and get a yes or no answer while displaying a prompt under installation
# 
prompt_yn() {
    while true; do
        read -n1 -p "
$@ (y/n)? " yn
        case "${yn}" in
            Y|y)
                echo "y" 
                break;;
            N|n)
                echo "n" 
                break;;
            *)
                ;;
        esac
    done
}

log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_header "                     kTAMV"
log_header "   Klipper Tool Alignment (using) Machine Vision"
log_blank
log_blank
log_important "kTAMV is used to align your printer's toolheads using machine vision."
log_blank
log_info "Usage: $0 [-p <server_port>] [-k <klipper_home_dir>] [-c <klipper_config_dir>] [-j <klipper_enviroment_dir>]"
log_info "[-m <moonraker_home_dir>] [-s <system_dir>]"
log_blank
log_blank
log_important "This script will install kTAMV client to Klipper and kTAMV server on port ${PORT}."
log_important "It will update Rasberry Pi OS and install all required packages."
log_important "It will install configuration in printer.cfg and update manager in Moonraker."
log_blank

log_important "${KTAMV_REPO_DIR}/moonraker_update.txt"

yn=$(prompt_yn "Do you want to continue?")
echo
case $yn in
    y)
        ;;
    n)
        log_info -e "You can run this script again later to install kTAMV."
        log_blank
    exit 0
        ;;
esac
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_blank
log_header "                     kTAMV"
log_header "   Klipper Tool Alignment (using) Machine Vision"
log_blank
log_blank
log_important "Do you want to contribute to the development of kTAMV?"
log_info "I would love if you would like to share the images of the nozzle and obtained results taken when finding the nozzle."
log_info "I plan to use it to improve the algorithm and maybe train an AI as the next step."
log_info "You can change this setting later in printer.cfg."
log_blank

yn=$(prompt_yn "Do you want to continue?")
echo
case $yn in
    y)
        log_info -e "Thank you, this will help a lot!"
        log_blank
        SEND_IMAGES="true"
        ;;
    n)
        log_info -e "Will not send any info."
        log_blank
        SEND_IMAGES="false"
        ;;
esac



while getopts "k:c:m:ids" arg; do
    case $arg in
        k) KLIPPER_HOME=${OPTARG};;
        m) MOONRAKER_HOME=${OPTARG};;
        c) KLIPPER_CONFIG_HOME=${OPTARG};;
        j) KLIPPER_ENV=${OPTARG};;
        s) SYSTEMDDIR=${OPTARG};;
        p) PORT=${OPTARG};;
    esac
done

function nextfilename {
    local name="$1"
    if [ -d "${name}" ]; then
        printf "%s-%s" ${name%%.*} $(date '+%Y%m%d_%H%M%S')
    else
        printf "%s-%s.%s-old" ${name%%.*} $(date '+%Y%m%d_%H%M%S') ${name#*.}
    fi
}


# Make sure we aren't running as root
verify_ready

# Before we do anything, make sure our required system packages are installed.
# These are required for other actions in this script, so it must be done first.
install_or_update_system_dependencies

# Check that kTAMV isn't found.
check_for_ktamv

# Check that Klipper is installed
check_klipper

# Check that the home directories are valid
verify_home_dirs

# Now make sure the virtual env exists, is updated, and all of our currently required PY packages are updated.
install_or_update_python_env

# Link the extension to Klipper
link_extension

# Install the update manager to Moonraker
install_update_manager

# Install kTAMV as a systemd service and then add it to the service list moonraker.asvc
install_sysd

# Install the configuration to Klipper
install_klipper_config

log_blank
log_blank
log_important "kTAMV is now installed. Settings can be found in the printer.cfg file."

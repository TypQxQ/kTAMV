#!/bin/bash
# This script installs the Webcam Server for kTAMV on a Raspi

SRCDIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
PYTHONDIR="${SRCDIR}/.venv"
# LOG_PATH="${MOBILERAKER_LOG_PATH}"
REBUILD_ENV="${REBUILD_ENV:-n}"
FORCE_DEFAULTS="${FORCE_DEFAULTS:-n}"
PORT="${PORT:-8085}"
LAUNCH_CMD="${PYTHONDIR}/bin/python ${SRCDIR}/webcam_server/webcam_server.py --port ${PORT}"

SYSTEMDDIR="/etc/systemd/system"
MOONRAKER_ASVC=~/printer_data/moonraker.asvc



# Function to detect Linux distribution
detect_distribution() {
    if [[ -f /etc/os-release ]]; then
        # Read the distribution information
        source /etc/os-release
        # Set the distribution variable based on ID or ID_LIKE
        if [[ -n $ID ]]; then
            DISTRIBUTION=$ID
        elif [[ -n $ID_LIKE ]]; then
            DISTRIBUTION=$ID_LIKE
        else
            DISTRIBUTION=""
        fi
    else
        # Unable to detect distribution
        DISTRIBUTION=""
    fi
}

# Function to install dependencies based on distribution
install_dependencies() {
    if [ $INSTALL_LIBJPEG != "y" ]; then
        return
    fi

    case $DISTRIBUTION in
        "raspbian" | "debian")
            if [ "$(id -u)" -ne 0 ]; then
                SUDO_CMD="sudo"
            fi
            $SUDO_CMD apt-get update
            $SUDO_CMD apt-get install -y libjpeg62-turbo-dev zlib1g-dev
            ;;
        "ubuntu" | "linuxmint")
            if [ "$(id -u)" -ne 0 ]; then
                SUDO_CMD="sudo"
            fi
            $SUDO_CMD apt-get update
            $SUDO_CMD apt-get install -y libjpeg8-dev zlib1g-dev
            ;;
        "fedora" | "centos" | "rhel")
            if [ "$(id -u)" -ne 0 ]; then
                SUDO_CMD="sudo"
            fi
            $SUDO_CMD dnf install -y libjpeg-devel zlib-devel
            ;;
        "arch" | "manjaro" | "endeavouros")
            if [ "$(id -u)" -ne 0 ]; then
                SUDO_CMD="sudo"
            fi
            $SUDO_CMD pacman -Sy --noconfirm  libjpeg-turbo zlib
            ;;
        *)
            echo "Unsupported distribution. Please install pillow dependencies manually. (https://pillow.readthedocs.io/en/stable/installation.html#external-libraries)"
            exit 1
            ;;
    esac
}


create_virtualenv()
{
    report_status "Installing python virtual environment..."

    # If venv exists and user prompts a rebuild, then do so
    if [ -d ${PYTHONDIR} ] && [ $REBUILD_ENV = "y" ]; then
        report_status "Removing old virtualenv"
        rm -rf ${PYTHONDIR}
    fi

    if [ ! -d ${PYTHONDIR} ]; then
        virtualenv -p /usr/bin/python3 ${PYTHONDIR}
    fi

    # Install/update dependencies
    ${PYTHONDIR}/bin/pip install -r ${SRCDIR}/webcam_server/requirements.txt
}

install_script()
{
# if [ -z "$LOG_PATH" ]
# then
#     CMD="${LAUNCH_CMD}"
# else
#     CMD="${LAUNCH_CMD} -l ${LOG_PATH}"

# fi
CMD="${LAUNCH_CMD}"

# Create systemd service file
    SERVICE_FILE="${SYSTEMDDIR}/kTAMV_webcam_server.service"
    [ -f $SERVICE_FILE ] && [ $FORCE_DEFAULTS = "n" ] && return
    report_status "Installing system start script..."
    sudo /bin/sh -c "cat > ${SERVICE_FILE}" << EOF
#Systemd service file for kTAMV_webcam_server
[Unit]
Description=WebCam Server to stream MJPEG from kTAMV so it can be viewed in Mainsail
After=network-online.target moonraker.service

[Install]
WantedBy=multi-user.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SRCDIR
ExecStart=$CMD
Restart=always
RestartSec=10
EOF
# Use systemctl to enable the klipper systemd service script
    sudo systemctl enable kTAMV_webcam_server.service
    sudo systemctl daemon-reload
}


start_software()
{
    report_status "Launching kTAMV Webcam Server..."
    sudo systemctl restart kTAMV_webcam_server
}

# Helper functions
report_status()
{
    echo -e "\n\n###### $1"
}

verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "This script must not run as root"
        exit -1
    fi
}

add_to_asvc()
{
    report_status "Trying to add kTAMV_webcam_server to service list"
    if [ -f $MOONRAKER_ASVC ]; then
        echo "moonraker.asvc was found"
        if ! grep -q kTAMV_webcam_server $MOONRAKER_ASVC; then
            echo "moonraker.asvc does not contain 'kTAMV_webcam_server'! Adding it..."
            echo -e "\nkTAMV_webcam_server" >> $MOONRAKER_ASVC
        fi
    fi
}

# Force script to exit if an error occurs
set -e

# Find SRCDIR from the pathname of this script
# SRCDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )"/.. && pwd )"

# Parse command line arguments
while getopts "rfl:j" arg; do
    case $arg in
        r) REBUILD_ENV="y";;
        f) FORCE_DEFAULTS="y";;
        # l) LOG_PATH=$OPTARG;;
        p) PORT="8085";; 

    esac
done

# Run installation steps defined above
# verify_ready
# detect_distribution
create_virtualenv
install_script
add_to_asvc
# install_dependencies
start_software

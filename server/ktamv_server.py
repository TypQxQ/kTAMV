# import the Flask module, the MJPEGResponse class, and the os module
import datetime, io, time, random, os, numpy as np, threading
from flask import Flask, jsonify, request, send_file #, send_from_directory
from PIL import Image, ImageDraw, ImageFont  #, ImageFile
from argparse import ArgumentParser
import matplotlib.font_manager as fm
from waitress import serve
import logging, json, traceback
from dataclasses import dataclass, field
from ktamv_server_dm import Ktamv_Server_Detection_Manager as dm

__logdebug = ""
# URL to the cloud server
__CLOUD_URL = "http://ktamv.ignat.se/index.php"
# If no nozzle found in this time, timeout the function
__CV_TIMEOUT = 20  
# Minimum amount of matches to confirm toolhead position after a move
__CV_MIN_MATCHES = 3 
# Size of frame to use
_FRAME_WIDTH = 640
_FRAME_HEIGHT = 480

# FPS to use when running the preview
__PREVIEW_FPS = 2

# If the nozzle position is within this many pixels when comparing frames, it's considered a match. Only whole numbers are supported.
__detection_tolerance = 0
# Wheather to update the image at next request
__update_static_image = True
# Error message to show on the image
__error_message_to_image = ""

# Indicates if preview is running
__preview_running = False

# Create logs folder if it doesn't exist and configure logging
if not os.path.exists("./logs"):
    os.makedirs("logs")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%a, %d %b %Y %H:%M:%S",
    filename="logs/ktamv_server.log",
    filemode="w",
    encoding="utf-8",
)

# create a Flask app
app = Flask(__name__)


# Define a global variable to store the processed frame in form of an image
__processed_frame_as_image = None
# Define a global variable to store the processed frame in form of bytes
__processed_frame_as_bytes = None
# The loaded standby image
__standby_image = None
# Define a global variable to store the camera path.
_camera_url = None
# Whether to send the frame to the cloud
__send_frame_to_cloud = False
# Define a global variable to store a key-value pair of the request id and the result
request_results = dict()
# The transform matrix calculated from the calibration points
_transformMatrix = None


@dataclass
class Ktamv_Request_Result:
    request_id: int
    data: str # As JSON encoded string
    runtime: float = None
    statuscode: int = None
    statusmessage: str = None
    

# Returns the transposed matrix calculated from the calibration points
@app.route("/calculate_camera_to_space_matrix", methods=["POST"])
def calculate_camera_to_space_matrix():
    show_error_message_to_image("")
    try:
        log("*** calling calculate_camera_to_space_matrix ***")
        # Get the camera path from the JSON object
        calibration_points = None
        try:
            data = json.loads(request.data)
            calibration_points = data.get("calibration_points")
        except json.JSONDecodeError:
            return "JSON Decode Error", 400

        if calibration_points is None:
            return "Calibration Points not found in JSON", 400
        else:
            if calibration_points is not None:
                n = len(calibration_points)
                real_coords, pixel_coords = np.empty((n, 2)), np.empty((n, 2))
                for i, (r, p) in enumerate(calibration_points):
                    real_coords[i] = r
                    pixel_coords[i] = p
                x, y = pixel_coords[:, 0], pixel_coords[:, 1]
                A = np.vstack([x**2, y**2, x * y, x, y, np.ones(n)]).T
                transform = np.linalg.lstsq(A, real_coords, rcond=None)
                global _transformMatrix
                _transformMatrix = transform[0].T
                return "OK", 200
    except Exception as e:
        show_error_message_to_image("Error: Could not calculate image to space matrix.")
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))
        return ""

@app.route("/calculate_offset_from_matrix", methods=["POST"])
def calculate_offset_from_matrix():
    show_error_message_to_image("")
    try:
        log("*** calling calculate_offset ***")
        try:
            data = json.loads(request.data)
            _v = data.get("_v")
            log("_v: " + str(_v))
            log("_transformMatrix: " + str(_transformMatrix))
            # _transformMatrix = data.get("transformMatrix")
        except json.JSONDecodeError:
            log("JSON Decode Error")
            return "JSON Decode Error", 400
        
        offsets = -1 * (0.55 * _transformMatrix @ _v)
        return jsonify(offsets.tolist())
    except Exception as e:
        show_error_message_to_image("Error: Could not calculate offset from matrix.")
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))

@app.route("/set_server_cfg", methods=["POST"])
def set_server_cfg():
    show_error_message_to_image("")
    try:
        log("*** calling set_server_cfg ***")
        camera_url = None
        response = ""

        # Stoping preview if running
        global __preview_running, __detection_tolerance, __send_frame_to_cloud
        __preview_running = False
        
        # Get the camera path from the JSON object
        try:
            data = json.loads(request.data)
            camera_url = data.get("camera_url")
        except json.JSONDecodeError:
            show_error_message_to_image("Error: Could not set camera URL.")
            return "JSON Decode Error", 400
        
        try:
            data = json.loads(request.data)
            send_frame_to_cloud = data.get("send_frame_to_cloud")
        except:
            pass

        if send_frame_to_cloud is not None:
            if send_frame_to_cloud == True:
                __send_frame_to_cloud = True
                response += "send_frame_to_cloud set to True\n"
            else:
                __send_frame_to_cloud = False
                response += "send_frame_to_cloud set to False\n"

        try:
            data = json.loads(request.data)
            __detection_tolerance = data.get("detection_tolerance")
        except:
            pass

        if camera_url is None:
            show_error_message_to_image("Error: Could not set camera URL.")
            return "Camera path not found in JSON", 400
        else:
            if camera_url.casefold().startswith(
                "http://"
            ) or camera_url.casefold().startswith("https://"):
                global _camera_url
                _camera_url = camera_url
                # Return code 200 to web browser
                log(f"*** end of set_server_cfg (set to {_camera_url}) ***<br>")
                show_error_message_to_image("Camera url set.")
                return response + "Camera path set to " + _camera_url, 200
            else:
                show_error_message_to_image("Error: Invalid nozzle_cam_url.")
                log("*** end of set_server_cfg (not set) ***<br>")
                return "Camera path must start with http:// or https://", 400
    except Exception as e:
        show_error_message_to_image("Error: Could not set camera URL.")
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


# Called from DetectionManager to put the frame in the global variable so it can be sent to the web browser
def put_frame(frame):
    try:
        global __processed_frame_as_image, __update_static_image
        # Convert the frame to a PIL Image
        __processed_frame_as_image = Image.fromarray(frame)
        __update_static_image = True
        
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


@app.route("/getAllReqests")
def getAllReqests():
    try:
        return jsonify(request_results)
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


@app.route("/")
def index():
    file_path = "logs/ktamv_server.log"
    content = "<H1>kTAMV Server is running</H1><br><b>Log file:</b><br>"
    content += (
        "Frame width: "
        + str(_FRAME_WIDTH)
        + ", Frame height: "
        + str(_FRAME_HEIGHT)
        + "<br>"
    )
    content += "Debuging log:<br>" + __logdebug + "<br>"
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content += file.read()

            # Replace line breaks with HTML line breaks
            content = content.replace("\n", "<br>")
            # Wrap the content with HTML tags
            html_content = f'<html><head><meta charset="utf-8"></head><body>{content}</body></html>'

            return html_content
    except FileNotFoundError:
        return content + "Log file not found"


@app.route("/getReqest", methods=["GET", "POST"])
def getReqest():
    try:
        # Get the request id from the URL
        request_id = request.args.get("request_id", type=int, default=None)

        # Return the request result if it exists, otherwise return a 404
        try:
            return jsonify(request_results[request_id])
        except KeyError:
            return jsonify(
                Ktamv_Request_Result(
                    request_id, None, None, 404, "Request not found"
                )
            )
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


@app.route("/getNozzlePosition")
def getNozzlePosition():
    show_error_message_to_image("")
    # Stoping preview if running
    global __preview_running
    __preview_running = False

    try:
        log("*** calling getNozzlePosition ***")
        start_time = time.time()  # Get the current time

        # Get a random request id
        request_id = random.randint(0, 1000000)

        if _camera_url is None:
            request_results[request_id] = Ktamv_Request_Result(
                request_id, None, time.time() - start_time, 502, "Camera URL not set"
            )
            log("*** end of getNozzlePosition - Camera URL not set ***<br>")
            return jsonify(request_results[request_id])


        request_results[request_id] = Ktamv_Request_Result(
            request_id, None, None, 202, "Accepted"
        )
        log("request_results: " + str(request_results))

        def do_work():
            log("*** calling do_work ***")
            detection_manager = dm(
                log, _camera_url, __CLOUD_URL, __send_frame_to_cloud
            )

            position = detection_manager.recursively_find_nozzle_position(
                put_frame, __CV_MIN_MATCHES, __CV_TIMEOUT, __detection_tolerance
            )

            log("position: " + str(position))

            if position is None:
                request_result_object = Ktamv_Request_Result(
                    request_id, None, time.time() - start_time, 404, "No nozzle found"
                )
                show_error_message_to_image("Error: No nozzle found.")
            else:
                request_result_object = Ktamv_Request_Result(
                    request_id,
                    json.dumps(position),
                    time.time() - start_time,
                    200,
                    "OK"
                )

            global request_results
            request_results[request_id] = request_result_object

            log("*** end of do_work ***")

        thread = threading.Thread(target=do_work)
        thread.start()

        log("*** end of getNozzlePosition ***<br>")
        return jsonify(request_results[request_id])
    except Exception as e:
        show_error_message_to_image("Error: Could not get nozzle position.")
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))

@app.route("/preview", methods=["POST"])
def preview():
    show_error_message_to_image("")
    try:
        log("*** calling preview ***")
        start_time = time.time()  # Get the current time
        global __preview_running

        try:
            data = json.loads(request.data)
            action = data.get("action")
        except json.JSONDecodeError:
            show_error_message_to_image("Error: Could not get action.")
            return "JSON Decode Error", 400

        def do_preview():
            log("*** calling do_preview ***")
            # Do not send images from preview to the cloud
            detection_manager = dm(
                log, _camera_url, cloud_url = "", send_to_cloud = False
            )
            
            while __preview_running:
                dm.get_preview_frame(detection_manager, put_frame)
                

            log("*** end of do_preview ***")

            # Wait for 1s/FPS for a maximum FPS.
            # This is to avoid overloading the server
            time.sleep(1 / __PREVIEW_FPS)

        # Handle the action
        if action == "stop":
            __preview_running = False
            return "Stopped preview.", 200
        elif action == "start":
            if _camera_url is None:
                log("*** end of preview - Camera URL not set ***<br>")
                return "Camera URL not set", 502
            else:
                __preview_running = True
                thread = threading.Thread(target=do_preview)
                thread.start()
                return "Started preview.", 200
        else:
            return "Invalid action.", 400
    except Exception as e:
        show_error_message_to_image("Error: Could not do preview.")
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))

###
# Returns the image to the web browser to act as a webcam
###
@app.route("/image")
def image():
    try:
        global __processed_frame_as_bytes, __update_static_image, __standby_image, __processed_frame_as_image

        # If no image has been recieved since start, load a standby image
        if __processed_frame_as_image is None:
            __processed_frame_as_image = Image.open("standby.jpg", mode="r")

            # read the file content as bytes
            __processed_frame_as_image.load()
            
            # Update text on the image
            __update_static_image = True

        if __update_static_image:
            __update_static_image = False

            # Draw the text on the image
            __processed_frame_as_image = drawOnFrame(__processed_frame_as_image)

            # Save the image to a byte array of JPEG format
            img_io = io.BytesIO()
            __processed_frame_as_image.save(img_io, "JPEG")
            img_io.seek(0)
            __processed_frame_as_bytes = img_io.read()
            

        # Get a byte stream of the image
        processed_frame_file = io.BytesIO(__processed_frame_as_bytes)
        processed_frame_file.seek(0)

        # Send the image to the web browser
        return send_file(processed_frame_file, mimetype="image/jpeg")
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


def drawOnFrame(usedFrame):
    # Get a string with the current date and time
    current_datetime = datetime.datetime.now()
    current_datetime_str = current_datetime.strftime("%Y-%m-%d %H:%M:%S.%f")

    # Draw the date on the image
    usedFrame: Image.Image = drawTextOnFrame(
        usedFrame, "Updated: " + current_datetime_str, row=1
    )
    
    if _camera_url is None:
        usedFrame = drawTextOnFrame(usedFrame, "kTAMV Server Configuration not recieved.", row=2)
    elif __processed_frame_as_image is None:
        usedFrame = drawTextOnFrame(usedFrame, "No image recieved since start.", row=2)
    elif _transformMatrix is None:
        usedFrame = drawTextOnFrame(usedFrame, "Camera not calibrated.", row=2)

    if __error_message_to_image != "":
        usedFrame = drawTextOnFrame(usedFrame, __error_message_to_image, row=3)
        
    if __preview_running:
        usedFrame = drawTextOnFrame(usedFrame, "Preview running.", row=-1, row_width=270)
                
    return usedFrame

def drawTextOnFrame(usedFrame, text, row=1, row_width=640):
    try:
        FONT_SIZE = 28
        FONT_COLOR = (255, 255, 255)
        FIRST_ROW_START = (10, 10)

        # Create a draw object
        draw = ImageDraw.Draw(usedFrame)

        # Choose a font
        font_path = fm.findfont(fm.FontProperties(family="arial"))
        font = ImageFont.truetype(font_path, FONT_SIZE)

        if row > 0:
            # Row from top
            start_point = (FIRST_ROW_START[0], FIRST_ROW_START[1] + (row - 1) * (FONT_SIZE + 10) )
        else:
            # Row from bottom
            start_point = (FIRST_ROW_START[0], usedFrame.height - (abs(row) * (FONT_SIZE + 10) + FIRST_ROW_START[1]) )
        
        # Draw the date on the image
        draw.rectangle((start_point[0]-5, start_point[1]-5, row_width - start_point[0], start_point[1] + FONT_SIZE + 10), fill=(0,0,0))
        draw.text(start_point, text, font=font, fill=FONT_COLOR )

        return usedFrame
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


def log_clear():
    global __logdebug
    __logdebug = ""


def log(message: str):
    global __logdebug
    __logdebug += message + "<br>"


def log_get():
    global __logdebug
    return __logdebug

def show_error_message_to_image(message : str):
    global __error_message_to_image, __update_static_image
    __error_message_to_image = message
    __update_static_image = True

# Run the app on the specified port
if __name__ == "__main__":
    logger = logging.getLogger(__name__)

    # Create an argument parser
    parser = ArgumentParser()
    parser.add_argument("--port", type=int, default=8085, help="Port number")

    # Parse the command-line arguments
    args = parser.parse_args()

    # Run the app with the specified port
    # app.run(host="0.0.0.0", port=args.port, debug=True)
    # app.run(host='0.0.0.0', port=args.port, debug=False)
    serve(app, host='0.0.0.0', port=args.port)

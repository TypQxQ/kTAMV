# import the Flask module, the MJPEGResponse class, and the os module
from array import array
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
__CLOUD_URL = "http://ktamv.ignat.se/index.php"

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

# Define a global variable to store the processed frame
processed_frame = None
# Define a global variable to store the camera path (e.g. /dev/video0)
_camera_url = None
# Whether to send the frame to the cloud
_send_frame_to_cloud = False
# Define a global variable to store a key-value pair of the request id and the result
request_results = dict()
# Size of last frame
_frame_width = 0
_frame_height = 0
_transformMatrix = None

@dataclass
class Ktamv_Request_Result:
    request_id: int
    data: str # As JSON encoded string
    runtime: float = None
    statuscode: int = None
    statusmessage: str = None
    frame_width: int = _frame_width
    frame_height: int = _frame_height
    

# Returns the transposed matrix calculated from the calibration points
@app.route("/calculate_camera_to_space_matrix", methods=["POST"])
def calculate_camera_to_space_matrix():
    try:
        log("*** calling calculate_camera_to_space_matrix ***")
        # Get the camera path from the JSON object
        _calibration_points = None
        try:
            data = json.loads(request.data)
            _calibration_points = data.get("calibration_points")
        except json.JSONDecodeError:
            return "JSON Decode Error", 400

        if _calibration_points is None:
            return "Calibration Points not found in JSON", 400
        else:
            if _calibration_points is not None:
                n = len(_calibration_points)
                real_coords, pixel_coords = np.empty((n, 2)), np.empty((n, 2))
                for i, (r, p) in enumerate(_calibration_points):
                    real_coords[i] = r
                    pixel_coords[i] = p
                x, y = pixel_coords[:, 0], pixel_coords[:, 1]
                A = np.vstack([x**2, y**2, x * y, x, y, np.ones(n)]).T
                transform = np.linalg.lstsq(A, real_coords, rcond=None)
                global _transformMatrix
                _transformMatrix = transform[0].T
                
                # transformMatrix = transform[0]
                # TODO: Unsure if this is correct
                # a = transformMatrix.T[0].tolist()
                # b = transformMatrix.T[1].tolist()
                # c= [a, b]
                
                
                # c= array([a, b])
                # c= array([a, b], dtype=array)
                # c = array([a, b], dtype=float)
                # return jsonify(a, b)
                # return jsonify(transformMatrix.T)
                return "OK", 200
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))
        return ""

@app.route("/calculate_offset_from_matrix", methods=["POST"])
def calculate_offset_from_matrix():
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
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))

@app.route("/set_server_cfg", methods=["POST"])
def set_server_cfg():
    try:
        log("*** calling set_server_cfg ***")
        # Get the camera path from the JSON object
        camera_url = None
        
        response = ""
        # log("request.data: " + str(request.data))
        try:
            data = json.loads(request.data)
            camera_url = data.get("camera_url")
        except json.JSONDecodeError:
            return "JSON Decode Error", 400
        
        try:
            data = json.loads(request.data)
            send_frame_to_cloud = data.get("send_frame_to_cloud")
        except:
            pass

        if send_frame_to_cloud is not None:
            global _send_frame_to_cloud
            if send_frame_to_cloud == True:
                _send_frame_to_cloud = True
                response += "send_frame_to_cloud set to True\n"
            else:
                _send_frame_to_cloud = False
                response += "send_frame_to_cloud set to False\n"

        if camera_url is None:
            return "Camera path not found in JSON", 400
        else:
            if camera_url.casefold().startswith(
                "http://"
            ) or camera_url.casefold().startswith("https://"):
                global _camera_url
                _camera_url = camera_url
                # Return code 200 to web browser
                log(f"*** end of set_server_cfg (set to {_camera_url}) ***<br>")
                return response + "Camera path set to " + _camera_url, 200
            else:
                log("*** end of set_server_cfg (not set) ***<br>")
                return "Camera path must start with http:// or https://", 400
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


# Called from DetectionManager to put the frame in the global variable so it can be sent to the web browser
def put_frame(frame):
    try:
        # Get a string with the current date and time
        current_datetime = datetime.datetime.now()
        current_datetime_str = current_datetime.strftime("%Y-%m-%d %H:%M:%S.%f")

        # Convert the frame to a PIL Image
        temp_frame = Image.fromarray(frame)
        # Draw the date on the image
        temp_frame: Image.Image = drawOnFrame(
            temp_frame, "Updated: " + current_datetime_str
        )
        # Convert the image to a byteio object (file-like object) encoded as JPEG
        byteio = io.BytesIO()
        temp_frame.save(byteio, format="JPEG")
        byteio.seek(0)
        # Write the frame to the global variable, so init it as global and then write to it
        global processed_frame, _frame_width, _frame_height
        processed_frame = byteio.read()
        _frame_width, _frame_height = temp_frame.size
        temp_frame.close()

        # Alternative that is not used but one row for every step if not need to add text.
        # processed_frame = cv2.imencode('.jpg', processed_frame)[1].tobytes()
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
        + str(_frame_width)
        + ", Frame height: "
        + str(_frame_height)
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
            CV_TIMEOUT = 20  # 5 # If no nozzle found in this time, timeout the function
            CV_MIN_MATCHES = (
                3  # Minimum amount of matches to confirm toolhead position after a move
            )
            CV_XY_TOLERANCE = 1  # If the nozzle position is within this tolerance, it's considered a match. 1.0 would be 1 pixel. Only whole numbers are supported.

            log("*** calling do_work ***")
            detection_manager = dm(
                log, _camera_url, __CLOUD_URL, _send_frame_to_cloud
            )

            log("detection_manager: " + str(detection_manager))

            position = detection_manager.recursively_find_nozzle_position(
                put_frame, CV_MIN_MATCHES, CV_TIMEOUT, CV_XY_TOLERANCE
            )

            log("position: " + str(position))

            if position is None:
                request_result_object = Ktamv_Request_Result(
                    request_id, None, time.time() - start_time, 404, "No nozzle found"
                )
            else:
                request_result_object = Ktamv_Request_Result(
                    request_id,
                    json.dumps(position),
                    time.time() - start_time,
                    200,
                    "OK",
                    _frame_width,
                    _frame_height,
                )

            global request_results
            request_results[request_id] = request_result_object

            log("*** end of do_work ***")

        # thread = threading.Thread(target=do_work, kwargs={'value': request.args.get('value', 20)})
        thread = threading.Thread(target=do_work)
        thread.start()

        log("*** end of getNozzlePosition ***<br>")
        return jsonify(request_results[request_id])
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


def drawOnFrame(usedFrame, text):
    try:
        # usedFrame = copy.deepcopy(image)

        # Create a draw object
        draw = ImageDraw.Draw(usedFrame)

        # Choose a font
        font_path = fm.findfont(fm.FontProperties(family="arial"))
        font = ImageFont.truetype(font_path, 32)

        # Draw the date on the image
        draw.text((10, 10), text, font=font, fill=(255, 255, 255))

        return usedFrame
    except Exception as e:
        log("Error: " + str(e) + "<br>" + str(traceback.format_exc()))


@app.route("/image")
def image():
    try:
        global processed_frame

        # If no image has been recieved since start, load a standby image
        if processed_frame is None:
            standbyImage = Image.open("standby.jpg", mode="r")

            # read the file content as bytes
            standbyImage.load()

            # Draw the text on the image
            standbyImage = drawOnFrame(standbyImage, "No image recieved since start.")

            # Save the image to a byte array of JPEG format
            img_io = io.BytesIO()
            standbyImage.save(img_io, "JPEG")
            img_io.seek(0)
            processed_frame = img_io.read()

        # Get a byte stream of the image
        processed_frame_file = io.BytesIO(processed_frame)
        processed_frame_file.seek(0)

        # Send the image to the web browser
        return send_file(processed_frame_file, mimetype="image/jpeg")
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
    app.run(host='0.0.0.0', port=args.port, debug=False)
    # serve(app, host='0.0.0.0', port=args.port)

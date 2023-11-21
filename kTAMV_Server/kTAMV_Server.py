# import the Flask module, the MJPEGResponse class, and the os module
import datetime, io, copy, time, random, os, cv2, numpy as np, threading
from flask import jsonify
from flask import Flask, request, send_file
from mjpeg.server import MJPEGResponse
from flask import send_from_directory, send_file
from PIL import Image, ImageDraw, ImageFont, ImageFile
import argparse

import logging, json
import kTAMV_Server_io as kTAMV_io
import kTAMV_Server_DetectionManager as kTAMV_DetectionManager

# Create logs folder if it doesn't exist and configure logging
if not os.path.exists("logs"):
    os.makedirs("logs")
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%a, %d %b %Y %H:%M:%S', filename='logs/kTAMV_Server.log', filemode='w', encoding='utf-8')

# create a Flask app
app = Flask(__name__)

class kTAMV_RequestResult(dict):
    def __init__(self, request_id, position = None, runtime = None, statuscode = None, statusmessage = None):
        dict.__init__(self, {
            "request_id": request_id,
            "position": position,
            "runtime": runtime,
            "statuscode": statuscode,
            "statusmessage": statusmessage
        })

# Define a global variable to store the processed frame
processed_frame = None
# Define a global variable to store the camera path (e.g. /dev/video0)
camera_url = None
camera_url = 'http://192.168.1.204/webcam2/stream'
#Define a global variable to store a key-value pair of the request id and the result
request_result = dict()

@app.route('/set_camera_url', methods=['POST'])
def set_camera_url(self):
    # Get the camera path from the JSON object
    camera_url = None
    try:
        data = json.loads(request.data)
        camera_url = data.get('camera_url')
    except json.JSONDecodeError:
        pass

    if camera_url is None:
        return "Camera path not found in JSON"
    else:
        # Return code 200 to web browser
        return "Camera path set to " + camera_url, 200
        
# Called from DetectionManager to put the frame in the global variable so it can be sent to the web browser
def put_frame(frame):

    # Get a string with the current date and time
    current_datetime = datetime.datetime.now()
    current_datetime_str = current_datetime.strftime("%Y-%m-%d %H:%M:%S.%f")

    # Convert the frame to a PIL Image
    temp_frame = Image.fromarray(frame)
    # Draw the date on the image
    temp_frame : Image.Image = drawOnFrame(temp_frame, "Updated: " + current_datetime_str)
    # Convert the image to a byteio object (file-like object) encoded as JPEG
    byteio = io.BytesIO()
    temp_frame.save(byteio, format='JPEG')
    byteio.seek(0)
    # Write the frame to the global variable, so init it as global and then write to it
    global processed_frame
    processed_frame = byteio.read()
    
    # Alternative that is not used but one row for every step if not need to add text.
    # processed_frame = cv2.imencode('.jpg', processed_frame)[1].tobytes()

@app.route('/getAllReqests')
def getAllReqests():
    return jsonify(request_result)

@app.route('/')
def default():
    file_path = 'logs/kTAMV_Server.log'
    content = "<H1>kTAMV Server is running</H1><br><b>Log file:</b><br>"
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content += file.read()
            
            
            # Replace line breaks with HTML line breaks
            content = content.replace('\n', '<br>')
            # Wrap the content with HTML tags
            html_content = f'<html><head><meta charset="utf-8"></head><body>{content}</body></html>'
            
            return html_content
    except FileNotFoundError:
        return content + "Log file not found"


@app.route('/getReqest', methods=['GET', 'POST'])
def getReqest():
    # Get the request id from the URL
    request_id = request.args.get("request_id", type=int, default=None)
    
    # Return the request result if it exists, otherwise return a 404
    try:
        return jsonify(request_result[request_id])
    except KeyError:
        return jsonify(kTAMV_RequestResult(request_id, None, None, 404, "Request not found"))


@app.route('/burstNozzleDetection')
def burstNozzleDetection():
    start_time = time.time()  # Get the current time
    
    # Get a random request id
    request_id = random.randint(0, 1000000)
    request_result[request_id] = kTAMV_RequestResult(request_id, None, None, 202, "Accepted")

    def do_work():
        CV_TIME_OUT = 20 #5 # If no nozzle found in this time, timeout the function
        CV_MIN_MATCHES = 3 # Minimum amount of matches to confirm toolhead position after a move
        CV_XY_TOLERANCE = 1 # If the nozzle position is within this tolerance, it's considered a match. 1.0 would be 1 pixel. Only whole numbers are supported.

        detection_manager = kTAMV_DetectionManager.kTAMV_DetectionManager(camera_url = camera_url)

        position = detection_manager.recursively_find_nozzle_position(put_frame, request_id, 1)

        if position is None:
            request_result_object = kTAMV_RequestResult(request_id, None, time.time() - start_time, 404, "No nozzle found")
        else:
            request_result_object = kTAMV_RequestResult(request_id, position.tolist(), time.time() - start_time, 200, "OK")

        global request_result
        request_result[request_id] = request_result_object

    # thread = threading.Thread(target=do_work, kwargs={'value': request.args.get('value', 20)})
    thread = threading.Thread(target=do_work)
    thread.start()

    return jsonify(request_result[request_id])

def drawOnFrame(usedFrame, text):
    # usedFrame = copy.deepcopy(image)
    
    # Create a draw object
    draw = ImageDraw.Draw(usedFrame)

    # Choose a font
    font = ImageFont.truetype("arial.ttf", 32)
    
    # Draw the date on the image
    draw.text((10, 10), text, font=font, fill=(255, 255, 255))

    return usedFrame

@app.route('/image')
def image():
    global processed_frame

    # If no image has been recieved since start, load a standby image
    if processed_frame is None:
        standbyImage = Image.open("standby.jpg", mode='r')
        
        # read the file content as bytes
        standbyImage.load()

        # Draw the text on the image
        standbyImage = drawOnFrame(standbyImage, "No image recieved since start." )

        # Save the image to a byte array of JPEG format
        img_io = io.BytesIO()
        standbyImage.save(img_io, 'JPEG')
        img_io.seek(0)
        processed_frame = img_io.read()

    # Get a byte stream of the image
    processed_frame_file= io.BytesIO(processed_frame)
    processed_frame_file.seek(0)

    # Send the image to the web browser
    return send_file(processed_frame_file, mimetype='image/jpeg')

# Run the app on the specified port
if __name__ == "__main__":

    # logger = logging.getLogger(__name__)

    # Create an argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8085, help='Port number')

    # Parse the command-line arguments
    args = parser.parse_args()

    # Run the app with the specified port
    app.run(host='0.0.0.0', port=args.port)
    last_frame = None
    

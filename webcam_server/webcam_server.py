# import the Flask module, the MJPEGResponse class, and the os module
import datetime, io, copy
from flask import Flask, request, send_file
from mjpeg.server import MJPEGResponse
from flask import send_from_directory, send_file
from PIL import Image, ImageDraw, ImageFont, ImageFile


# create a Flask app
app = Flask(__name__)

# Define a global variable to store the uploaded image
uploaded_image = None


def drawOnFrame(image, text):
    usedFrame = copy.deepcopy(image)
    
    # Create a draw object
    draw = ImageDraw.Draw(usedFrame)

    # Choose a font
    font = ImageFont.truetype("arial.ttf", 32)
    
    # Draw the date on the image
    draw.text((10, 10), text, font=font, fill=(255, 255, 255))

    return usedFrame

@app.route('/upload', methods=['POST'])
def upload():
    try:
        global uploaded_image
        if 'image.jpeg' not in request.files:
            return 'there is no image.jpeg in form!'

        file = request.files['image.jpeg']
        
        img = Image.open(file.stream)

        # img = drawOnFrame(img, "Min egna text" )
        
        # Save the image to a byte array
        jpeg_bytedata = io.BytesIO()
        img.save(jpeg_bytedata, format='JPEG')

        uploaded_image = img
        return 'File uploaded successfully'
    except Exception as e:
        print("Error uploading image: " + str(e))
        return str(e)

@app.route('/image')
def image():
    global uploaded_image
    # print("Req to send image")
    if uploaded_image is None:
        standbyImage = Image.open("standby.jpg", mode='r')
        # read the file content as bytes
        standbyImage.load()

        # Draw the text on the image
        standbyImage = drawOnFrame(standbyImage, "No image recieved since start." )

        uploaded_image = standbyImage

    img_io = io.BytesIO()
    uploaded_image.save(img_io, 'JPEG')
    # print("Sending image 2")
    img_io.seek(0)
    return send_file(img_io, mimetype='image/jpeg')

# run the app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8082)
    last_frame = None
import io
import picamera
import logging
import socketserver
import time

from threading import Condition
from http import server
from requests.auth import HTTPBasicAuth
from gpiozero import LED

PAGE="""\
<html>
<head>
<title>Finn Doggy Cam</title>
</head>
<body>
<center><h1>Raspberry Pi - Surveillance Camera</h1></center>
<center><img src="stream.mjpg" width="720" height="480"></center>
</body>
</html>
"""

count = 0
clients = [0,1,2,3,4]
streaming_pin = 4
running_pin = 17
streaming_led = LED(streaming_pin)
running_led = LED(running_pin)

running_led.on()

class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()
        print("Initializing Stream Output")

    def write(self, buf):
        global count
        
        if count==0:
            streaming_led.off()
        else:
            streaming_led.on()
    
        
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)



class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        MAX = 5
        global count
        global clients
        
        client = self.client_address[0]
        print("current list of clients: ")
        print(clients)
        
        if count < MAX and client not in clients:
            print("new client!")
            clients[count] = client
            count = count + 1
        elif count > MAX - 1:
            print("we're maxed out")
        
        print("count: %s", count)
        print("this is the client address connected: %s", self.client_address)
        
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
                count = count - 1
                print("count: %s", count)
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

with picamera.PiCamera(resolution='1920x1080', framerate=60) as camera:
    output = StreamingOutput()
    #Uncomment the next line to change your Pi's Camera rotation (in degrees)
    camera.rotation = 180
    camera.start_recording(output, format='mjpeg')
    try:
        address = ('', 8123)
        server = StreamingServer(address, StreamingHandler)
        server.serve_forever()
    finally:
        camera.stop_recording()

from argparse import ArgumentParser
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PyQt6.QtWidgets import * 
from PIL import ImageQt
import sys
from time import sleep

import zmq
import ipc_pb2
#import ipc_pb2.IPC.Action as act
import os
import threading

act= ipc_pb2.IPC.Action

print(sys.argv)
def get_args( our_args):
    print(our_args)
    parser = ArgumentParser()
    parser.add_argument('-t','--default-text',default="A cow eating grass")

    opts=parser.parse_args( our_args)
    return opts

def message( action, string=None, blob=None ):
    out = ipc_pb2.IPC()
    out.action = action
    if string is not None:
        out.str_data = string
    if blob is not None:
        out.blob_data = blob
    return out.SerializeToString()

def rmessage( blob ):
    out = ipc_pb2.IPC()
    out.ParseFromString(blob)
    return out


def model_runner( ):
    ctx = zmq.Context()
    socket = ctx.socket(zmq.REP)
    socket.bind("tcp://localhost:5788")

    lsocket = ctx.socket(zmq.PUB)
    lsocket.bind("tcp://localhost:5789")
    msg = socket.recv()
    ipcm = rmessage(msg)

    def do_log(string):
        lsocket.send_multipart([b'info',string.encode('utf-8')])
    if ipcm.action != act.STARTED:
        do_log("BARF")
        raise Exception("BARF")

    socket.send(message(act.STARTED))
    do_log("TEST LOG")

    working = True
    while working:
        msg = socket.recv()
        ipcm = rmessage(msg)
        if ipcm.action == act.PING: 
            socket.send(message(act.PONG))
            do_log("PONG")
        elif ipcm.action == act.STOP: 
            working = False
            do_log("BYEEEEEEEEE")


class ModelWorker(QObject):
    image_error = pyqtSignal(str)
    image_ready = pyqtSignal(object)

    def __init__(self ):
        super().__init__()

        self.run_mutex = QMutex()
        self.finished = QWaitCondition()
        self.update_mutex =QMutex()

        # protect with update
        self.ready=False

    @pyqtSlot()
    def run(self):
        self.update_mutex.lock()
        self.ready =False
        self.update_mutex.unlock()
        print("Running Model")
        from diffusers import StableDiffusionPipeline
        import torch

        model_id = "CompVis/stable-diffusion-v1-4"
        self.pipeline = StableDiffusionPipeline.from_pretrained(model_id,
                torch_dtype=torch.float16)

        self.pipeline.to("cuda")

        #sleep(3)
        print("Done Model, Waiting.")
        #self.run_mutex.lock()
        #self.finished.wait(self.run_mutex)
        print("Done Wait")
        
        # init, then wait for term conidiont.

    @pyqtSlot(str)
    def create(self,input_str):
        print(f"Request for Create: {input_str}")
        #sleep(5)
        #self.image_ready.emit(None)
        prompt = input_str

        try:
            results = self.pipeline(prompt) 
            print(results)
            image = results.images[0]
            self.image_ready.emit(image)
        except Exception as e:
            print(e)

    @pyqtSlot()
    def on_exit(self):
        print("on exit")
        self.finished.wakeAll()

class Window(QWidget):
    image_request = pyqtSignal(str)
    shutdown = pyqtSignal()
    start_background = pyqtSignal()
    def __init__(self):
        QWidget.__init__(self)

        self.bkgr = QThread()
        self.worker = ModelWorker()
        self.worker.moveToThread(self.bkgr)

        self.working = False
        self.setWindowTitle("Portrait Selector")

        self.main_layout = QGridLayout()
        self.setLayout(self.main_layout)

        prompt = "A color portrait photograph of a young woman, age 27 named Anne Shirley"
        self.image_area = QLabel("Press a button to continue")
        self.control_layout = QGridLayout()
        self.text = QLineEdit(prompt) 
        self.go = QPushButton("Generate")
        self.main_layout.addWidget(self.image_area,0,0)
        self.main_layout.addLayout(self.control_layout,1,0)
        self.control_layout.addWidget(self.text,0,0)
        self.control_layout.addWidget(self.go,0,1)


        self.setGeometry(500,500,500,500)

        self.go.clicked.connect(self.on_generate)

        # image requst from here to worker
        self.image_request.connect(self.worker.create)
        # image output from worker to here
        self.worker.image_ready.connect( self.on_image_ready )
        self.shutdown.connect(self.worker.on_exit)
        self.start_background.connect(self.worker.run)
        self.bkgr.start()
        self.start_background.emit()


    def on_generate(self):
        print("Gen Req"+ self.text.text())
        self.working = True
        self.image_request.emit(self.text.text())

    def closeEvent(self,event):
        print("Exiting")
        self.shutdown.emit()

    def on_image_ready(self, image):
        if image is None:
            return
        print(f"Ready! {type(image)} format is {image.format}")
        pil2qt = ImageQt.ImageQt(image)
        px = QPixmap.fromImage(pil2qt)
        #img = QImage( image.tobytes("raw", "RGB"), image.size[0], image.size[1],
        #        QImage.Format_RGB32)
        self.image_area.setPixmap(px)

#pipe_fds = os.pipe()
pid = os.fork()

log_run = True
def log_recv( ctz ):
    zsocket = ctx.socket(zmq.SUB)
    zsocket.connect("tcp://localhost:5789")
    #lsocket.setsockopt(zmq.SUBSCRIBE, 4)
    zsocket.subscribe("")
    poller = zmq.Poller()
    poller.register(zsocket,zmq.POLLIN)
    print("log reciever on.")
    while log_run:
        socks = dict(poller.poll(1000))
        if socks:
            if socks.get(zsocket):
                bmsg = zsocket.recv(zmq.NOBLOCK)
                print(f"M {bmsg.decode('utf-8')}")
            else:
                print("Socks, but not zsocket?")
        #else:
        #   print("No data")
    print("Done")


if pid == 0:
    model_runner()
else:
    ctx = zmq.Context()
    socket = ctx.socket(zmq.REQ)
    socket.connect("tcp://localhost:5788")
    socket.send(message(act.STARTED))

    lthread = threading.Thread(target=log_recv,args=(ctx,))
    lthread.start()

    msg = socket.recv()
    ipcm = rmessage(msg)
    if ipcm.action == act.STARTED: 
        socket.send(message(act.PING))
    else:
        raise Exception("IPC Init Fail")
    msg = socket.recv()
    ipcm = rmessage(msg)
    if ipcm.action == act.PONG: 
        print("ok, alive.")
        #socket.send(message(act.PING))
    else:
        raise Exception("IPC Init PING Fail")
    socket.send(message(act.STOP))
    #os.write(write_fd,X)
    sleep(4)
    log_run=False
    lthread.join()
    sys.exit(0)

    app = QApplication(sys.argv)

    unused_args = app.arguments()
    opts = get_args([ str(s) for s in unused_args ][1:])

    print(opts.default_text)
    screen = Window()
    screen.show()

    sys.exit(app.exec())

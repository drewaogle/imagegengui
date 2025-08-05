from argparse import ArgumentParser
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PyQt6.QtWidgets import * 
from PIL import ImageQt
import sys
from time import sleep

print(sys.argv)
def get_args( our_args):
    print(our_args)
    parser = ArgumentParser()
    parser.add_argument('-t','--default-text',default="A cow eating grass")

    opts=parser.parse_args( our_args)
    return opts



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


app = QApplication(sys.argv)

unused_args = app.arguments()
opts = get_args([ str(s) for s in unused_args ][1:])

print(opts.default_text)
screen = Window()
screen.show()

sys.exit(app.exec())

# Import packages
import os
import sys

from api import *

from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QFileDialog


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi("gui/main_form.ui", self)

        self.pushButton_currentid.released.connect(self.update_scanid)
        self.pushButton_browse.released.connect(self.get_dir)
        self.pushButton_start.released.connect(self.start_loop)
        self.pushButton_stop.released.connect(self.stop_loop)

    def update_scanid(self):
        self.lineEdit_startid.setProperty("text", str(get_current_scanid()))
        return

    def get_dir(self):
        dialog = QFileDialog()
        dialog.setFileMode(QFileDialog.DirectoryOnly)

        folder = dialog.getExistingDirectory(self, 'Save Location')
        if folder != "":
            if folder[-1] != "/" and folder[-1] != "\\":
                folder += os.sep
            self.lineEdit_savelocation.setProperty("text", folder)
        return

    def start_loop(self):
        # Check for a thread running the main loop
        try:
            if self.th.isRunning is True:
                return
        except AttributeError:
            self.th = Tloop(self)

        # Check the scan parameters
        self.start_id = int(self.lineEdit_startid.text())
        self.wd = self.lineEdit_savelocation.text()
        self.N = int(self.lineEdit_numscan.text())
        self.dt = int(self.lineEdit_delay.text())
        (self.start_id, self.wd, self.N, self.dt) = check_inputs(self.start_id, self.wd, self.N, self.dt)
        print(self.start_id, self.wd, self.N, self.dt)
        self.lineEdit_savelocation.setProperty("text", self.wd)
        self.lineEdit_startid.setProperty("text", str(self.start_id))
        self.lineEdit_numscan.setProperty("text", str(self.N))
        self.lineEdit_delay.setProperty("text", str(self.dt))
        
        # Change to the proper working directory
        os.chdir(self.wd)

        # Start the thread
        self.th.start()
        return

    def stop_loop(self):
        self.th.stop()
        return

    def update_progress(self, x):
        self.progressBar.setProperty("value", x)
        return


class Tloop(QThread):
    signal_update_progressBar = pyqtSignal(float)
    DT = 0.01  # sleep time

    def __init__(self, form):
        super(QThread, self).__init__()
        self.form = form
        self.isRunning = False
        self.signal_update_progressBar.connect(self.form.update_progress)

    def __del__(self):
        self.isRunning = False
        self.wait()

    def stop(self):
        self.__del__()

    def run(self):
        self.isRunning = True

        try:
            while self.isRunning:
                xrf_loop(self.form.start_id, self.form.N)
                loop_sleep(self.form.dt, gui=self)
        except KeyboardInterrupt:
            print("\n\nStopping SRX Autosave loop.")
            pass


app = QtWidgets.QApplication(sys.argv)
window = MainWindow()
window.show()
app.exec_()


# %% Main loop for XRF maps -> HDF5
def autosave_xrf(start_id, wd="", N=1000, dt=60):
    """
    SRX Autosave

    Setup the main loop to automatically download and make the HDF5s

    Parameters
    ----------
    start_id : int
        Starting scan ID
    wd : string
        Path to write the HDF5 files
    N : int
        Number of scan IDs to search for, start_id + N
    dt : int
        Time, in seconds, to wait before trying to make more files

    Returns
    -------
    None

    Examples
    --------
    Start downloading and creating HDF5 files and saving them into the user's directory
    >>> autosave_xrf(1234, wd='/home/xf05id1/current_user_data/, N=1000, dt=60)

    """
    # Check the input parameters
    (start_id, wd, N, dt) = check_inputs(start_id, wd, N, dt)
    os.chdir(wd)

    print("--------------------------------------------------")

    try:
        while True:
            xrf_loop(start_id, N)
            loop_sleep(dt)

    except KeyboardInterrupt:
        print("\n\nExiting SRX AutoSave.")
        pass

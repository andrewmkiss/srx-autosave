# Import packages
import os
import sys
import h5py
import numpy as np
from pathlib import Path
from tifffile import imsave

from api import (get_current_scanid, check_inputs, xrf_loop, loop_sleep)

from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QFileDialog

try:
    from pyxrf import pyxrf_batch
except ImportError:
    print("Error importing pyXRF. Continuing without import.")

# For Hi-DPI monitors
QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QtWidgets.QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        path = Path(__file__).parent
        uic.loadUi(path / "gui/main_form.ui", self)

        self.label_logo.setProperty("pixmap", path / "gui/5-ID_TopAlign.png")
        self.setProperty("windowIcon", path / "gui/5-ID_TopAlign.png")

        self.pushButton_stop.setProperty("enabled", False)
        self.setContentsMargins(20, 0, 20, 20)

        self.pushButton_currentid.released.connect(self.update_scanid)
        self.pushButton_plus1.released.connect(self.update_scanid_plus1)
        self.pushButton_browse.released.connect(self.get_dir)
        self.pushButton_start.released.connect(self.start_loop)
        self.pushButton_stop.released.connect(self.stop_loop)
        self.pushButton_batchfit.released.connect(self.get_conf_H5_dirs)

    def update_scanid(self):
        self.lineEdit_startid.setProperty("text", str(get_current_scanid()))
        return

    def update_scanid_plus1(self):
        self.lineEdit_startid.setProperty("text", str(get_current_scanid()+1))
        return

    def get_dir(self):
        dialog = QFileDialog()
        dialog.setFileMode(QFileDialog.DirectoryOnly)

        folder = dialog.getExistingDirectory(self, 'Save Location', str(Path.home()))
        if folder != "":
            if folder[-1] != "/" and folder[-1] != "\\":
                folder += os.sep
            self.lineEdit_savelocation.setProperty("text", folder)
        return

    def get_scan_parameters(self):
        self.start_id = int(self.lineEdit_startid.text())
        self.wd = self.lineEdit_savelocation.text()
        self.N = int(self.lineEdit_numscan.text())
        self.dt = int(self.lineEdit_delay.text())

    def set_scan_parameters(self):
        self.lineEdit_savelocation.setProperty("text", self.wd)
        self.lineEdit_startid.setProperty("text", str(self.start_id))
        self.lineEdit_numscan.setProperty("text", str(self.N))
        self.lineEdit_delay.setProperty("text", str(self.dt))

    def lock_widgets(self, value):
        self.lineEdit_savelocation.setProperty("enabled", value)
        self.lineEdit_startid.setProperty("enabled", value)
        self.lineEdit_numscan.setProperty("enabled", value)
        self.lineEdit_delay.setProperty("enabled", value)
        self.pushButton_browse.setProperty("enabled", value)
        self.pushButton_currentid.setProperty("enabled", value)
        self.pushButton_plus1.setProperty("enabled", value)

    def start_loop(self):
        # Check for a thread running the main loop
        try:
            if self.th.isRunning is True:
                self.th.stop()
        except AttributeError:
            self.th = Tloop(self)

        # Check the scan parameters
        self.get_scan_parameters()
        tmp = check_inputs(self.start_id, self.wd, self.N, self.dt)
        self.start_id = tmp[0]
        self.wd = tmp[1]
        self.N = tmp[2]
        self.dt = tmp[3]
        # print(self.start_id, self.wd, self.N, self.dt)
        self.set_scan_parameters()

        # Change to the proper working directory
        try:
            os.chdir(self.wd)
        except FileNotFoundError as ex:
            self.label_status.setProperty("text", str(ex))
            print(ex)
            return

        # Start the thread
        self.pushButton_stop.setProperty("enabled", True)
        self.pushButton_start.setProperty("text", "Force Restart")
        self.lock_widgets(False)
        self.th.start()
        return

    def stop_loop(self):
        try:
            self.th.stop()
            self.pushButton_stop.setProperty("enabled", False)
            self.pushButton_start.setProperty("text", "Start")
            self.lock_widgets(True)
        except AttributeError:
            pass
        return

    def update_progress(self, x):
        self.progressBar.setProperty("value", x)
        return

    def update_status(self, x):
        self.label_status.setProperty("text", x)
        return
    
    def get_conf_H5_dirs(self):
       # Create Qt context
       # app = Qt.QApplication([])
        # Then do what is needed...
        confFile = QFileDialog.getOpenFileName(None,
                                                  "Choose the config file")
        confFile = confFile[0]
        if not confFile:
            print("Configuration file not selected. Exiting.")
            sys.exit(1)
        
        H5Files = QFileDialog.getOpenFileName(None,
                                                  "Choose the H5 files to be fitted")
    
        print("Configuration file: " + confFile)
        print("H5 files to fit:")
        for d in H5Files:
            print("-" + d)
            
        pyxrf_batch(param_file_name = confFile, data_files = H5Files, save_tiff=True, scaler_name="I0")
        return


class Tloop(QThread):
    signal_update_progressBar = pyqtSignal(float)
    signal_update_status = pyqtSignal(str)
    DT = 0.01  # sleep time

    def __init__(self, form):
        super(QThread, self).__init__()
        self.form = form
        self.isRunning = False
        self.signal_update_progressBar.connect(self.form.update_progress)
        self.signal_update_status.connect(self.form.update_status)

    def __del__(self):
        self.isRunning = False
        self.wait()

    def stop(self):
        self.__del__()

    def run(self):
        self.isRunning = True

        try:
            while self.isRunning:
                xrf_loop(self.form.start_id, self.form.N, gui=self)
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

def autoroi_xrf(scanid):
    """
    SRX auto_roi

    Automatic generate roi based on the specified elements

    Parameters
    ----------
    scanid : int
        Scan ID
   
    Returns
    -------
    None

    Examples
    --------
    Start generating rois from the saved h5 files and saving them into the user's directory
    >>> autoroi_xrf(1234)

    """
    #load h5 file (autosaved)
    element_roi = {'Ca_k':[350,390], "Fe_k": [620,660], "Ni_k": [730,770], "Cu_k": [780, 820], "Zn_k": [780, 820], "Pt_l": [920,960], "Au_l": [1140, 1180]};
    
    print("export rois...")
    with h5py.File(f"scan2D_{scanid}_*.h5") as f:
        for x in element_roi:
            roi = np.sum(f['xrfmap/detsum/counts'][:,:,element_roi[x][0]:element_roi[x][1]], axis=2)
            sclr_I0 = f['xrfmap/scalers/val'][:,:,0]
            roi_norm = roi/sclr_I0
            imsave(f'roi_{scanid}_{x}.tiff', roi_norm, dtype="float32")
    print("finish exporting rois")
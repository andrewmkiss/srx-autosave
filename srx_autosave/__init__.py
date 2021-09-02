# Import packages
import os
import sys
from pathlib import Path

import _version
from api import (get_current_scanid, check_inputs, xrf_loop, autoroi_xrf, loop_sleep)
from new_makehdf import new_makehdf
from PyQt5 import QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QFileDialog

try:
    from pyxrf.api_dev import pyxrf_batch
except ImportError:
    print("Error importing pyXRF. Continuing without import.")


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        path = Path(__file__).parent
        uic.loadUi(path / "gui/main_form.ui", self)

        self.label_logo.setProperty("pixmap", path / "gui/5-ID_TopAlign.png")
        self.setProperty("windowIcon", path / "gui/5-ID_TopAlign.png")

        ver = get_versions()
        ver_str = f"{ver['version'][:3]} {ver['date'].split('T')[0]}"
        self.label_version.setProperty("text", ver_str)

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
        self.pushButton_batchfit.setProperty("enabled", value)

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
        filter = "JSON (*.json)"
        confFile = QFileDialog()
        confFile.setFileMode(QFileDialog.ExistingFiles)
        confFile = confFile.getOpenFileName(self, "Choose the config file", "/home/xf05id1/current_user_data/", filter)
        confFile = confFile[0]
        if not confFile:
            print("Configuration file not selected. Exiting.")
            sys.exit(1)
        
        filter = "H% (*.h5)"
        H5Files = QFileDialog()
        H5Files.setFileMode(QFileDialog.ExistingFiles)
        H5Files, mask = H5Files.getOpenFileNames(self, "Choose the H5 files to be fitted", "/home/xf05id1/current_user_data/", filter)
    
        print("Configuration file: " + confFile)
        print("H5 files to fit:")
        for d in H5Files:
            print("-" + d)
            
        pyxrf_batch(param_file_name = confFile, data_files = H5Files, scaler_name = "i0")
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


def run_autosave():

    # For Hi-DPI monitors
    QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_autosave()

#!/usr/bin/env python
from subprocess import Popen, PIPE

import threading
import socket
import os
import sys
import random
import time
import urllib2

from PyQt4.QtGui import *
from PyQt4.QtCore import *

# -a ip port ext_port proto dur
# -d ext_port proto ip

CLIENTS = []
FILE_PATH = None
BUFFER = 8192
TIMEOUT_IN_HOURS = 12

# generate random port
PORT = random.randint(20000, 65530)

# create server socket
SERVER = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
SERVER.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
SERVER.bind(('', PORT))
SERVER.listen(0)

''' Client Handler '''

class Client(threading.Thread):
	# setup client
	def __init__(self, client, addr):
		super(Client, self).__init__()
		self.client = client
		self.addr = addr
		self._running = True
		self.window = False

	# client I/O
	def run(self):
		global FILE_PATH, BUFFER
		
		f = open( FILE_PATH , 'rb')
		file_size = str(os.path.getsize( FILE_PATH ))
		if 'L' in file_size: file_size = file_size.replace('L','')
		file_name = os.path.basename( FILE_PATH )

		# Send Client file info
		self.client.send( file_name + "***" + file_size)
		time.sleep(0.5) # a small delay to make sure file data doesn't overlap

		# Stream file data to client
		while self._running:
			data = f.read( BUFFER )
			if not data:
				break
			self.client.send( data )

		# close file stream
		f.close()


	# end connection
	def __closeall__(self):
		self._running = False
		self.client.close()

''' Downloader '''

class Downloader(threading.Thread):
	def __init__(self, addr, window):
		threading.Thread.__init__(self)
		self.addr = addr
		self.window = window

	def run(self):
		# create socket to get data
		self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.s.settimeout(2)
		
		try:
			self.window.down_box.setEnabled(False)

			# Connect to client
			self.addr = ( self.addr[0], int(self.addr[1]) )
			self.window.new_status.emit("Connecting to " + str(self.addr[0])+":"+str(self.addr[1]))

			# connect to partner
			try:
				self.s.connect( self.addr )
			except Exception as e:
				self.close_all()
				self.window.new_status.emit("Failed to connect: " + str(e))
				return

			# Successful connetion	
			self.window.new_status.emit("Connected!")
			self.window.update_bar.emit(0)

			# get file info
			file_info = str(self.s.recv(1024))

			# make sure params are there
			if '***' not in file_info:
				self.close_all()
				return

			# open file
			_file_name = file_info.split('***')[0]
			f = open( _file_name, 'wb' )
			fsize = int(file_info.split('***')[1])
			done = 0

			# start file stream downloader
			while True:
				try:
					# get next data stream
					data = self.s.recv( BUFFER )
					if not data:
						break

					# update progress bar percentage
					done += len(data)
					percent = (done * 100.0) / (fsize * 1.0)
					self.window.update_bar.emit(percent)

					# write to file
					f.write( data )
				except Exception as e:
					break

			# finish download
			self.window.update_bar.emit(100)
			self.window.new_log("Downloaded " + _file_name)
			self.close_all()

		except Exception:
			self.close_all()

	def close_all(self):
		self.s.close()
		self.window.down_box.setEnabled(True)


''' Server socket handler '''

class Server(threading.Thread):
	def __init__(self, window):
		threading.Thread.__init__(self)
		self.window = window

		# get port and server
		global SERVER, PORT
		self.port = PORT
		self.sock = SERVER

	def run(self):
		global CLIENTS

		while True:
			try:
				# get client
				client_sock, addr = self.sock.accept()
				# only if file is selected
				if self.window._file != None:
					self.window.new_client.emit( addr )
					client = Client( client_sock, addr )
					client.daemon = True
					client.start()
					CLIENTS.append( client )

				else:
					# no file selected
					self.window.new_log.emit("Client connected but no file selected!")
					client_sock.close()

			except Exception as e:
				print "ERROR: " + str(e)
				sys.exit()

	def exit_all(self):
		global CLIENTS

		# destroy all clients
		for client in CLIENTS:
			try:
				client.__closeall__()
				client.terminate()
				client.join()
				del client
			except:
				pass


class MainWindow(QWidget):
	new_client = pyqtSignal(tuple)
	update_bar = pyqtSignal(int)
	new_status = pyqtSignal(str)
	new_log    = pyqtSignal(str)

	def __init__(self):
		super(MainWindow, self).__init__()

		self._file = None
		self._lanip = None

		self.initUI()
		self.startThread( self.init_service )

	''' Init UI '''
	def initUI(self):
		self.resize( 480, 360 )
		self.setWindowTitle("Python Transfer Client")

		# create layout
		self.layout = QVBoxLayout()
		self.setLayout(self.layout)

		# create widgets & signals
		self.update_bar.connect( self.update_progress )
		self.new_status.connect( self.update_status )
		self.new_log.connect( self.update_log )
		self.create_widgets()

	''' Thread & Signal Functions '''
	def update_progress(self, value):
		self.pbar.setValue( int(value) )

	def update_status(self, message):
		self.status_bar.setText( str(message) )

	def startThread(self, func, *args):
		thread = threading.Thread(target=func,args=args)
		thread.daemon = True
		thread.start()

	def note_new_client(self, addr):
		client_ip = str(addr[0])+":"+str(addr[1])
		self.new_log.emit( "New Connection> " + client_ip + " !")

	def update_log(self, message):
		message = str(message)
		self.log_box.append( str(message) )

	''' On Exit '''
	def closeEvent(self, event):
		global PORT
		self.update_log("Exitting...")
		self.server.exit_all()
		try:
			command = "upnpc.exe -d {0} TCP {1}".format(str(PORT), self._lanip)
			print str(command)
			output = Popen(command.split(),stdout=PIPE,stderr=PIPE).communicate()
			if output[1] != "":
				print "[-] Error: " + str(output[-1])
			else:
				print "[+] Command sucess"
		except:
			pass
		self.destroy()
		QApplication.quit()


	''' Load Service '''
	def init_service(self):
		global TIMEOUT_IN_HOURS

		# Close app for initialization
		self._disable()
		self.create_server()
		time.sleep(0.1)

		# bind signals
		self.new_client.connect(self.note_new_client)

		# Get public IP address
		self.new_status.emit( "Getting ip address..." )
		public_ip = urllib2.urlopen("http://ip.42.pl/raw").read()
		public_port = self.server.port
		self.ip.setText( str(public_ip) + ":" + str(public_port) )

		# Setup Port forward
		self.new_status.emit("setting up UPNP... ")
		self._lanip = socket.gethostbyname(socket.getfqdn())
		_timeout = str(TIMEOUT_IN_HOURS * 60 * 60) # to seconds
		_port = str(self.server.port)
		command = "upnpc.exe -a {0} {1} {2} TCP {3}".format(
			self._lanip, _port, _port, _timeout)
		print str(command)
		output = Popen(command.split(),stdout=PIPE,stderr=PIPE).communicate()
		if output[1] != "":
			print "[-] Error: " + str(output[-1])
		else:
			print "[+] Command sucess"

		# Ready app for use
		time.sleep(0.1)
		self.new_status.emit("Ready!")
		self._enable()

	# Create the TCP Server
	def create_server(self):
		self.server = Server(self)
		self.server.daemon = True
		self.server.start()

	''' Enable / Disable Widgets '''
	def _disable(self):
		self.ip.setEnabled(False)
		self.up_box.setEnabled(False)
		self.down_box.setEnabled(False)
		self.log_box.setEnabled(False)

	def _enable(self):
		self.ip.setEnabled(True)
		self.up_box.setEnabled(True)
		self.down_box.setEnabled(True)
		self.log_box.setEnabled(True)

	''' Other Functions '''
	# start downloading client's file
	def startDownload(self):
		text = str(self.dest_ip.text())
		if not text.isspace():
			try:
				addr = text.split(":")
				downloader = Downloader(addr, self)
				downloader.daemon = True
				downloader.start()
			except:
				self._enable()

	# load your own file for download
	def loadFile( self ):
		global FILE_PATH

		try:
			fname = str(QFileDialog.getOpenFileName(self, 'Open File', '/')[0])
			if fname != '':
				fname = os.path.abspath( fname )
				FILE_PATH = fname
				self.file_name.setText( FILE_PATH )
				self._file = FILE_PATH
		except Exception as e:
			print str(e)
			pass


	''' Create Widgets '''
	def create_widgets(self):
		self.ip = QLineEdit("getting ip..")
		self.ip.setAlignment(Qt.AlignCenter)
		self.ip.setReadOnly(True)
		self.ip.setStyleSheet("font-size: 20px; font-weight: bold;")

		self.up_box = QGroupBox()
		self.up_box.setTitle("Upload")
		up_layout = QVBoxLayout()
		self.up_box.setLayout(up_layout)

		self.down_box = QGroupBox()
		self.down_box.setTitle("Download")
		down_layout = QVBoxLayout()
		self.down_box.setLayout(down_layout)

		# upload box
		self.pick_btn = QPushButton("Pick a file")
		self.pick_btn.clicked.connect( self.loadFile )
		self.file_name = QLabel("file name")

		up_layout.addWidget( self.pick_btn )
		up_layout.addWidget( self.file_name )

		# download box
		self.dest_ip = QLineEdit()
		self.dest_ip.setPlaceholderText("IP Address:Port")
		self.down_button = QPushButton("Connect")
		self.down_button.clicked.connect( self.startDownload )
		self.down_file_name = QLabel("download_file_name.file")
		enter_layout = QHBoxLayout()
		enter_layout.addWidget( QLabel("Enter Target Address: ") )
		enter_layout.addWidget( self.dest_ip )
		enter_layout.addWidget( self.down_button )

		self.pbar = QProgressBar()
		self.pbar.setOrientation(Qt.Horizontal)
		self.pbar.setRange(0,100)
		self.speed = QLabel("0 kbps")
		progress_layout = QHBoxLayout()
		progress_layout.addWidget( self.pbar )
		progress_layout.addWidget( self.speed )

		down_layout.addLayout( enter_layout )
		down_layout.addLayout( progress_layout )

		# log box
		self.log_box = QTextEdit()
		self.log_box.setReadOnly(True)

		# Status bar
		hline = QFrame()
		hline.setFrameShape(QFrame.HLine)
		hline.setFrameShadow(QFrame.Sunken)
		self.status_bar = QLabel("Loading...")

		# add widgets to layout
		self.layout.addWidget( self.ip )
		self.layout.addWidget( self.up_box )
		self.layout.addWidget( self.down_box )
		self.layout.addWidget( QLabel("Log:") )
		self.layout.addWidget( self.log_box )
		self.layout.addStretch(1)
		self.layout.addWidget( hline )
		self.layout.addWidget( self.status_bar )


if __name__ == '__main__':
	app = QApplication(sys.argv)
	app.setStyle("plastique")

	win = MainWindow()
	win.show()

	sys.exit(app.exec_())
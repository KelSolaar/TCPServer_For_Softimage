"""
**TCPServer.py**

**Platform:**
	Windows, Linux.

**Description:**
	| This module defines the :class:`TCPServer`class and other helpers objects needed to run a **Python** socket server
	inside **Autodesk Softimage** in a similar way than **Autodesk Maya** command port.
	| This module has been created as a replacement to
	`sIBL_GUI_XSI_Server <https://github.com/KelSolaar/sIBL_GUI_XSI_Server>`_ addon for 2 major reasons:

		- The fact that **sIBL_GUI_XSI_Server** was a C# addon needed to be recompiled for each **Autodesk Softimage**
version
		- The need for a generic socket server that could be easily extended and modified because
it's written in **Python**.

	| Some examples exists, especially on `XSI-Blog <http://www.softimageblog.com/archives/132>`_
	unfortunately they don't work anymore with current **Autodesk Softimage** releases,
	resulting in application getting blocked while the code is executed.
	| To prevent this the :class:`TCPServer`class code is executed in a separate thread using the 
	:mod:`SocketServer`.
	| One of the major issue encountered while implementing the server was that the client code was getting executed
	into the server thread resulting in random application crashes.
	| The trick to avoid this has been to create a global requests stack using :class:`collections.deque` class shared
	between the main application thread and the server thread, then a timer event process the data on a regular interval.
	| Another issue was the scopes oddities happening with the code and especially the PPG logic. It seems that
	the PPG logic definitions are called in another scope than the module one.
	| Hopefully, thanks to **Python** introspection it's possible to retrieve the correct module object. For that,
	a global :data:`__uid__` attribute is defined, then the list of objects handled by the garbage collector is traversed
	until one with the attribute is found. See :def:`_getModule` definition for more details.
	| An alternate design using the plugin **UserData** attribute has been tested but never managed to wrap correcly
	the :class:`collections.deque` class inside a COM object.

**Usage:**

	| Download and install the addon like any other addon. It should be available in the plug-ins manager as
	**TCPServer_For_Softimage**.
	| The server should start automatically with **Autodesk Softimage** startup. You can also start it using the
	**TCPServer_start** command or the **TCPServer_property**.
	| By default the server is handling string packets of *4096* in size, if the packets are bigger they are split and
	stacked. They are processed by the \*RequestHandlers.processData methods.

**Handlers:**
	| Different handlers are available as examples:
	| The :class:`DefaultStackDataRequestHandler` class handles two types of string formatting:

		- An existing script file path: "C://MyScript//PythonScript.py" in that case the script would be executed as
		a **Python** script by the application.

		- A string with the following formatting: "Language | Code", "JScript | LogMessage(\"Pouet!\")" in that case
		the given code would be executed as **Python** JScript by the application resulting in **Pouet!** being logged.

	Example client code:

		>>> import socket
		>>> connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		>>> connection.connect(("127.0.0.1", 12288))
		>>> connection.send("JScript | LogMessage(\"Pouet\")")
		29
		>>> connection.send("C:/Users/KelSolaar/AppData/Roaming/HDRLabs/sIBL_GUI/4.0/io/loaderScripts/sIBL_XSI_Import.js")
		91
		>>> connection.close()

**Others:**

"""

#**********************************************************************************************************************
#***	External imports.
#**********************************************************************************************************************
import SocketServer
import collections
import os
import re
import sys
import threading
from win32com.client import constants as siConstants

#**********************************************************************************************************************
#***	Module attributes.
#**********************************************************************************************************************
__author__ = "Thomas Mansencal"
__copyright__ = "Copyright (C) 2008 - 2012 - Thomas Mansencal"
__license__ = "GPL V3.0 - http://www.gnu.org/licenses/"
__maintainer__ = "Thomas Mansencal"
__email__ = "thomas.mansencal@gmail.com"
__status__ = "Production"

__uid__ = "ab7c34a670c7737f491edfd2939201c4"

__all__ = []

#**********************************************************************************************************************
#***	Module classes and definitions.
#**********************************************************************************************************************
class ProgrammingError(Exception):
	pass

class AbstractServerError(Exception):
	pass

class ServerOperationError(AbstractServerError):
	pass

class NetworkMessages():
	dataReceived = "@DATA_RECEIVED"
	requestEnd = "@REQUEST_END"

class DefaultRequestHandler(SocketServer.BaseRequestHandler, NetworkMessages):

	def handle(self):
		while True:
			data = self.request.recv(4096)
			if not data:
				break
			
			self.request.send(self.dataReceived)
			sys.stdout.write(data)
		return True

	@staticmethod
	def processData():
		pass

class LoggingRequestHandler(SocketServer.BaseRequestHandler, NetworkMessages):

	def handle(self):
		while True:
			data = self.request.recv(4096)
			if not data:
				break
			
			self.request.send(self.dataReceived)
			Runtime.requestsStack.append(data)
		return True

	@staticmethod
	def processData():
		while Runtime.requestsStack:
			Application.LogMessage(Runtime.requestsStack.popleft())
		return True

class DefaultStackDataRequestHandler(SocketServer.BaseRequestHandler, NetworkMessages):

	def handle(self):
		while True:
			data = self.request.recv(4096)
			if not data:
				break
			
			self.request.send(self.dataReceived)
			Runtime.requestsStack.append(data)
		return True

	@staticmethod
	def processData():
		while Runtime.requestsStack:
			data = Runtime.requestsStack.popleft().strip()
			if os.path.exists(data):
				value = Application.ExecuteScript(data)
				Application.LogMessage("{0} | Request return value: '{1}'.".format(
				Constants.name, value), siConstants.siVerbose)
			else:
				for language in Constants.languages:
					match = re.match(r"\s*(?P<language>{0})\s*\|(?P<code>.*)".format(language), data)
					if match:
						value = Application.ExecuteScriptCode(match.group("code"), match.group("language"))
						Application.LogMessage("{0} | Request return value: '{1}'.".format(
						Constants.name, value), siConstants.siVerbose)
						break
		return True

class PythonStackDataRequestHandler(SocketServer.BaseRequestHandler):

	def handle(self):
		allData = []
		while True:
			data = self.request.recv(4096)
			if not data:
				break
			
			self.request.send(self.dataReceived)
			if self.requestEnd in data:
				allData.append(data[:data.find(self.requestEnd)])
				break

			allData.append(data)
			if len(allData) >=1:
				tail = allData[-2] + allData[-1]
				if self.requestEnd in tail:
					allData[-2] = tail[:tail.find(self.requestEnd)]
					allData.pop()
					break

		Runtime.requestsStack.append("".join(allData))
		return True

	@staticmethod
	def processData():
		while Runtime.requestsStack:
			value = Application.ExecuteScriptCode(Runtime.requestsStack.popleft(), "Python")
			Application.LogMessage("{0} | Request return value: '{1}'.".format(
			Constants.name, value), siConstants.siVerbose)
		return True

class Constants(object):

	name = "TCPServer"
	author = __author__
	email = __email__
	website = "http://www.thomasmansencal.com/"
	majorVersion = 1
	minorVersion = 0
	patchVersion = 0
	settings = "TCPServer_settings_property"
	logo = "pictures/TCPServer_Logo.bmp"
	defaultAddress = "127.0.0.1"
	defaultPort = 12288
	defaultRequestsHandler = DefaultStackDataRequestHandler
	languages = ("VBScript", "JScript", "Python", "PythonScript", "PerlScript")

class Runtime(object):

	server = None
	address = Constants.defaultAddress
	port = Constants.defaultPort
	requestsHandler = Constants.defaultRequestsHandler
	requestsStack = collections.deque()

class TCPServer(object):

	def __init__(self, address, port, handler=DefaultRequestHandler):
		self.__address = None
		self.address = address
		self.__port = None
		self.port = port
		self.__handler = None
		self.handler = handler

		self.__server = None
		self.__worker = None
		self.__online = False

	#******************************************************************************************************************
	#***	Attributes properties.
	#******************************************************************************************************************
	@property
	def address(self):
		return self.__address

	@address.setter
	def address(self, value):
		if value is not None:
			assert type(value) in (str, unicode), "'{0}' attribute: '{1}' type is not 'str' or 'unicode'!".format(
			"address", value)
		self.__address = value

	@address.deleter
	def address(self):
		raise ProgrammingError("{0} | '{1}' attribute is not deletable!".format(self.__class__.__name__, "address"))

	@property
	def port(self):
		return self.__port

	@port.setter
	def port(self, value):
		if value is not None:
			assert type(value) is int, "'{0}' attribute: '{1}' type is not 'int'!".format(
			"port", value)
		self.__port = value

	@port.deleter
	def port(self):
		raise ProgrammingError("{0} | '{1}' attribute is not deletable!".format(self.__class__.__name__, "port"))

	@property
	def handler(self):
		return self.__handler

	@handler.setter
	def handler(self, value):
		if value is not None:
			assert issubclass(value, SocketServer.BaseRequestHandler), \
			"'{0}' attribute: '{1}' is not 'SocketServer.BaseRequestHandler' subclass!".format("handler", value)
		self.__handler = value

	@handler.deleter
	def handler(self):
		raise ProgrammingError("{0} | '{1}' attribute is not deletable!".format(self.__class__.__name__, "handler"))

	@property
	def online(self):
		return self.__online

	@online.setter
	def online(self, value):
		raise ProgrammingError("{0} | '{1}' attribute is read only!".format(self.__class__.__name__, "online"))

	@online.deleter
	def online(self):
		raise ProgrammingError("{0} | '{1}' attribute is not deletable!".format(self.__class__.__name__, "online"))

	#******************************************************************************************************************
	#***	Class methods.
	#******************************************************************************************************************
	def start(self):
		if self.__online:
			raise ServerOperationError("{0} | '{1}' server is already online!".format(self.__class__.__name__, self))

		self.__server = SocketServer.TCPServer((self.__address, self.__port), self.__handler)
		self.__worker = threading.Thread(target=self.__server.serve_forever)
		self.__worker.setDaemon(True)
		self.__worker.start()
		self.__online = True
		return True
	
	def stop(self):
		if not self.__online:
			raise ServerOperationError("{0} | '{1}' server is not online!".format(self.__class__.__name__, self))

		self.__server.socket.close()
		self.__server.shutdown()
		self.__server = None
		self.__worker = None
		self.__online = False
		return True
	
def XSILoadPlugin(pluginRegistrar):
	pluginRegistrar.Author = Constants.author
	pluginRegistrar.Name = Constants.name
	pluginRegistrar.URL = Constants.website
	pluginRegistrar.Email = Constants.email
	pluginRegistrar.Major = Constants.majorVersion
	pluginRegistrar.Minor = Constants.minorVersion

	pluginRegistrar.RegisterCommand("TCPServer_start", "TCPServer_start")
	pluginRegistrar.RegisterCommand("TCPServer_stop", "TCPServer_stop")
	pluginRegistrar.RegisterEvent("TCPServer_startupEvent", siConstants.siOnStartup)	
	pluginRegistrar.RegisterTimerEvent("TCPServer_timerEvent", 250, 0)

	pluginRegistrar.RegisterProperty("TCPServer_property");

	Application.LogMessage("'{0}' has been loaded!".format(pluginRegistrar.Name))
	return True

def XSIUnloadPlugin(pluginRegistrar):
	_stopServer()
	Application.LogMessage("'{0}' has been unloaded!".format(pluginRegistrar.Name))
	return True

def TCPServer_startupEvent_OnEvent(context):
	Application.LogMessage("{0} | 'TCPServer_startupEvent_OnEvent' called!".format(
	Constants.name), siConstants.siVerbose)
	_registerSettingsProperty()
	_restoreSettings()
	_startServer()
	return True

def TCPServer_start_Init(context):
	Application.LogMessage("{0} | 'TCPServer_start_Init' called!".format(
	Constants.name), siConstants.siVerbose)
	return True

def TCPServer_start_Execute():
	Application.LogMessage("{0} | 'TCPServer_start_Execute' called!".format(
	Constants.name), siConstants.siVerbose)
	_startServer()
	return True

def TCPServer_stop_Init(context):
	Application.LogMessage("{0} | 'TCPServer_stop_Init' called!".format(
	Constants.name), siConstants.siVerbose)
	return True

def TCPServer_stop_Execute():
	Application.LogMessage("{0} | 'TCPServer_stop_Execute' called!".format(
	Constants.name), siConstants.siVerbose)
	_stopServer()
	return True

def TCPServer_timerEvent_OnEvent(context):
	# Application.LogMessage("{0} | 'TCPServer_timerEvent' called!".format(
	# Constants.name), siConstants.siVerbose)
	Runtime.requestsHandler.processData()
	return False

def TCPServer_property_Define(context):
	property = context.Source
	property.AddParameter2("Logo_siString", siConstants.siString)
	property.AddParameter2("Address_siString", siConstants.siString, Runtime.address)
	property.AddParameter2("Port_siInt", siConstants.siInt4, Runtime.port, 10000, 65536, 10000, 65536)
	return True

def TCPServer_property_DefineLayout(context):
	layout = context.Source
	layout.Clear()

	Logo_siControlBitmap = layout.AddItem("Logo_siString", "", siConstants.siControlBitmap)
	Logo_siControlBitmap.SetAttribute(siConstants.siUIFilePath, os.path.join(__sipath__, Constants.logo))
	Logo_siControlBitmap.SetAttribute(siConstants.siUINoLabel, True)

	layout.AddGroup("Server", True, 0)

	layout.AddItem("Address_siString", "Address")
	layout.AddRow()
	layout.EndRow()
	layout.AddItem("Port_siInt", "Port")
	layout.EndGroup()

	layout.AddGroup()
	layout.AddRow()
	layout.AddButton("Start_Server_button", "Start TCPServer")
	layout.AddGroup()
	layout.EndGroup()
	layout.AddButton("Stop_Server_button", "Stop TCPServer")
	layout.EndRow()
	layout.EndGroup()
	return True

def TCPServer_property_Address_siString_OnChanged():
	module = _getModule()
	if not module:
		return

	module.Runtime.address = PPG.Address_siString.Value
	module._storeSettings()
	return True

def TCPServer_property_Port_siInt_OnChanged():
	module = _getModule()
	if not module:
		return

	module.Runtime.port = PPG.Port_siInt.Value
	module._storeSettings()
	return True

def TCPServer_property_Start_Server_button_OnClicked():
	module = _getModule()
	if not module:
		return

	module._startServer()
	return True

def TCPServer_property_Stop_Server_button_OnClicked():
	module = _getModule()
	if not module:
		return

	module._stopServer()
	return True

def _registerSettingsProperty():
	if not Application.Preferences.Categories(Constants.settings):
		property = Application.ActiveSceneRoot.AddCustomProperty(Constants.settings);
		property.AddParameter2("Address_siString", siConstants.siString, Constants.defaultAddress)
		property.AddParameter2("Port_siInt", siConstants.siInt4, Constants.defaultPort, 10000, 65536, 10000, 65536)
		Application.InstallCustomPreferences("TCPServer_settings_property", "TCPServer_settings_property")
	return True 

def _storeSettings():
	if Application.Preferences.Categories(Constants.settings):
		Application.preferences.SetPreferenceValue("{0}.Address_siString".format(Constants.settings), Runtime.address)
		Application.preferences.SetPreferenceValue("{0}.Port_siInt".format(Constants.settings), Runtime.port)
	return True 

def _restoreSettings():
	if Application.Preferences.Categories(Constants.settings):
		Runtime.address = str(Application.preferences.GetPreferenceValue("{0}.Address_siString".format(Constants.settings)))
		Runtime.port = int(Application.preferences.GetPreferenceValue("{0}.Port_siInt".format(Constants.settings)))
	return True 

def _getServer(address, port, requestsHandler):
	return TCPServer(address, port, requestsHandler)

def _startServer():
	if Runtime.server:
		if Runtime.server.online:
			XSIUIToolkit.Msgbox("{0} | The server is already online!".format(Constants.name, Runtime.server),
								siConstants.siMsgExclamation, "{0} | Warning".format(Constants.name))
			return

	Runtime.server = _getServer(Runtime.address, Runtime.port, Runtime.requestsHandler)
	Runtime.server.start()
	return True

def _stopServer():
	if Runtime.server:
		if not Runtime.server.online:
			XSIUIToolkit.Msgbox("{0} | The server is not online!".format(Constants.name, Runtime.server),
								siConstants.siMsgExclamation, "{0} | Warning".format(Constants.name))
			return

	Runtime.server and Runtime.server.stop()
	return True

def _getModule():
	# Garbage Collector wizardry to retrieve the actual module object.
	import gc
	for object in gc.get_objects():
		if not hasattr(object,"__uid__"):
			continue

		if getattr(object, "__uid__") == __uid__:
			return object

"""
**TCPServer.py**

**Platform:**
    Windows.

**Description:**
    | **Softimage 2013**: Due to some breaking changes in Softimage 2013, the addon cannot be used anymore the way
    it was designed	to be: No more hot servers restart / handlers swap. You will have to define the settings
    you want to use and restart the application.
    | This module defines the :class:`TCPServer`class and other helpers objects needed to run a **Python** socket server
    inside **Autodesk Softimage** in a similar way than **Autodesk Maya** command port.
    | This module has been created as a replacement to
    `sIBL_GUI_XSI_Server <https://github.com/KelSolaar/sIBL_GUI_XSI_Server>`_ addon for 2 major reasons:

        - The fact that **sIBL_GUI_XSI_Server** was a C# addon needing to be recompiled for each **Autodesk Softimage**
version.
        - The need for a generic socket server that could be easily extended and modified because
it's written in **Python**.

    | Some examples exists, especially on `XSI-Blog <http://www.softimageblog.com/archives/132>`_
    unfortunately they don't work anymore with current **Autodesk Softimage** releases,
    resulting in application getting blocked while the code is executed.
    | To prevent this the :class:`TCPServer`class code is executed in a separate thread using the
    :mod:`SocketServer`.
    | One of the major issue encountered while implementing the server was because the client code was getting executed
    into the server thread resulting in random application crashes.
    | The trick to avoid this has been to create a global requests stack using :class:`collections.deque` class shared
    between the main application thread and the server thread, then a timer event poll the data on a regular interval and
    process it.
    | Another issue was the scopes oddities happening within the code and especially inside the PPG logic. It seems that
    the PPG logic definitions are called in another scope than the module one, making it hard to access module objects and
    annoying if you don't want to expose everything in application commands.
    | Hopefully, thanks to **Python** introspection it's possible to retrieve the correct module object. For that,
    a global :data:`__uid__` attribute is defined, then the list of objects handled by the garbage collector is traversed
    until one with the attribute is found. See :def:`_getModule` definition for more details.
    | An alternate design using the plugin **UserData** attribute has been tested but never managed to wrap correcly
    the :class:`collections.deque` class inside a COM object.

**Usage:**

    | Download and install the addon like any other addon. It should be available in the plug-ins manager as
    **TCPServer_For_Softimage**.
    | The server should start automatically with **Autodesk Softimage** startup. You can also start it using the
    **TCPServer_start** command or the **TCPServer_property** available in the View -> TCPServer -> TCPServer Preferences
    menu.

**Handlers:**
    | Different handlers are available:
    | The :class:`EchoRequestsHandler` class that writes to standard output what the client send and echo it back:

    Example client code:

        >>> import socket
        >>> connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        >>> connection.connect(("127.0.0.1", 12288))
        >>> connection.send("Hello World!")
        12
        >>> connection.recv(1024)
        'Hello World!'
        >>> connection.close()

    The :class:`DefaultStackDataRequestsHandler` class handles two types of string formatting:

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

    The :class:`LoggingStackDataRequestsHandler` class that verbose what the client send:

    Example client code:

        >>> import socket
        >>> connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        >>> connection.connect(("127.0.0.1", 12288))
        >>> connection.send("Hello World!")
        12
        >>> connection.close()

    The :class:`PythonStackDataRequestsHandler` class that will aggregate the data the client send until it encounters the
    :attr:`PythonStackDataRequestsHandler.request_end` attribute and then executes the given data as **Python** code.

    Example client code:

        >>> import socket
        >>> connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        >>> connection.connect(("127.0.0.1", 12288))
        >>> connection.send("import sys\nprint sys.maxint<!RE>")
        33
        >>> connection.close()

**Others:**

"""

from __future__ import unicode_literals

import SocketServer
import collections
import inspect
import os
import re
import socket
import itertools
import threading
from win32com.client import constants as siConstants

__author__ = "Thomas Mansencal"
__copyright__ = "Copyright (C) 2008 - 2013 - Thomas Mansencal"
__license__ = "GPL V3.0 - http://www.gnu.org/licenses/"
__maintainer__ = "Thomas Mansencal"
__email__ = "thomas.mansencal@gmail.com"
__status__ = "Production"

__uid__ = "ab7c34a670c7737f491edfd2939201c4"

__all__ = ["ProgrammingError",
           "AbstractServerError",
           "ServerOperationError",
           "EchoRequestsHandler",
           "LoggingStackDataRequestsHandler",
           "DefaultStackDataRequestsHandler",
           "PythonStackDataRequestsHandler",
           "Constants",
           "Runtime",
           "TCPServer",
           "XSILoadPlugin",
           "XSIUnloadPlugin"]


class ProgrammingError(Exception):
    pass


class AbstractServerError(Exception):
    pass


class ServerOperationError(AbstractServerError):
    pass


class EchoRequestsHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        while True:
            data = self.request.recv(1024)
            if not data:
                break

            self.request.send(data)
        return True

    @staticmethod
    def process_data():
        pass


class LoggingStackDataRequestsHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        while True:
            data = self.request.recv(1024)
            if not data:
                break

            Runtime.requests_stack.append(data)
        return True

    @staticmethod
    def process_data():
        while Runtime.requests_stack:
            Application.LogMessage(Runtime.requests_stack.popleft())
        return True


class DefaultStackDataRequestsHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        while True:
            data = self.request.recv(1024)
            if not data:
                break

            Runtime.requests_stack.append(data)
        return True

    @staticmethod
    def process_data():
        while Runtime.requests_stack:
            data = Runtime.requests_stack.popleft().strip()
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


class PythonStackDataRequestsHandler(SocketServer.BaseRequestHandler):
    request_end = "<!RE>"

    def handle(self):
        all_data = []
        while True:
            data = self.request.recv(1024)
            if not data:
                break

            if self.request_end in data:
                all_data.append(data[:data.find(self.request_end)])
                break

            all_data.append(data)
            if len(all_data) >= 1:
                tail = all_data[-2] + all_data[-1]
                if self.request_end in tail:
                    all_data[-2] = tail[:tail.find(self.request_end)]
                    all_data.pop()
                    break

        Runtime.requests_stack.append("".join(all_data))
        return True

    @staticmethod
    def process_data():
        while Runtime.requests_stack:
            value = Application.ExecuteScriptCode(Runtime.requests_stack.popleft(), "Python")
            Application.LogMessage("{0} | Request return value: '{1}'.".format(
                Constants.name, value), siConstants.siVerbose)
        return True


class Constants(object):
    name = "TCPServer"
    author = __author__
    email = __email__
    website = "http://www.thomasmansencal.com/"
    major_version = 0
    minor_version = 2
    patch_version = 0
    settings = "TCPServer_settings_property"
    logo = "pictures/TCPServer_Logo.bmp"
    default_address = "127.0.0.1"
    default_port = 12288
    default_requests_handler = DefaultStackDataRequestsHandler
    languages = ("VBScript", "JScript", "Python", "PythonScript", "PerlScript")


class Runtime(object):
    server = None
    address = Constants.default_address
    port = Constants.default_port
    requests_handler = Constants.default_requests_handler
    requests_stack = collections.deque()


class TCPServer(object):

    def __init__(self, address, port, handler=EchoRequestsHandler):
        self.__address = None
        self.address = address
        self.__port = None
        self.port = port
        self.__handler = None
        self.handler = handler

        self.__server = None
        self.__worker = None
        self.__online = False

    @property
    def address(self):
        return self.__address

    @address.setter
    def address(self, value):
        if value is not None:
            assert type(value) is unicode, "'{0}' attribute: '{1}' type is not 'unicode'!".format(
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

    def start(self):
        if self.__online:
            raise ServerOperationError("{0} | '{1}' server is already online!".format(self.__class__.__name__, self))

        try:
            self.__server = SocketServer.TCPServer((self.__address, self.__port), self.__handler)
            self.__worker = threading.Thread(target=self.__server.serve_forever)
            self.__worker.setDaemon(True)
            self.__worker.start()
            self.__online = True
            Application.LogMessage(
                "{0} | Server successfully started on '{1}' address and '{2}' port using '{3}' requests handler!".format(
                    self.__class__.__name__, self.__address, self.__port, self.__handler.__name__),
                siConstants.siInfo)
            return True
        except socket.error as error:
            if error.errno == 10048:
                Application.LogMessage(
                    "{0} | Cannot start server, a connection is already opened on port '{2}'!".format(
                        self.__class__.__name__, self, self.__port), siConstants.siWarning)
            else:
                raise error

    def stop(self):
        if not self.__online:
            raise ServerOperationError("{0} | '{1}' server is not online!".format(self.__class__.__name__, self))

        self.__server.shutdown()
        self.__server = None
        self.__worker = None
        self.__online = False
        Application.LogMessage("{0} | Server successfully stopped!".format(
            self.__class__.__name__), siConstants.siInfo)
        return True


def XSILoadPlugin(plugin_registrar):
    plugin_registrar.Author = Constants.author
    plugin_registrar.Name = Constants.name
    plugin_registrar.URL = Constants.website
    plugin_registrar.Email = Constants.email
    plugin_registrar.Major = Constants.major_version
    plugin_registrar.Minor = Constants.minor_version

    plugin_registrar.RegisterEvent("TCPServer_startupEvent", siConstants.siOnStartup)
    plugin_registrar.RegisterCommand("TCPServer_start", "TCPServer_start")
    plugin_registrar.RegisterCommand("TCPServer_stop", "TCPServer_stop")
    plugin_registrar.RegisterTimerEvent("TCPServer_timerEvent", 250, 0)
    plugin_registrar.RegisterMenu(siConstants.siMenuMainApplicationViewsID, "TCPServer")

    plugin_registrar.RegisterProperty("TCPServer_property")

    Application.LogMessage("'{0}' has been loaded!".format(plugin_registrar.Name))
    return True


def XSIUnloadPlugin(plugin_registrar):
    _stop_server()
    Application.LogMessage("'{0}' has been unloaded!".format(plugin_registrar.Name))
    return True


def TCPServer_startupEvent_OnEvent(context):
    Application.LogMessage("{0} | 'TCPServer_startupEvent_OnEvent' called!".format(
        Constants.name), siConstants.siVerbose)
    _register_settings_property()
    _restore_settings()
    _start_server()
    return True


def TCPServer_start_Init(context):
    Application.LogMessage("{0} | 'TCPServer_start_Init' called!".format(
        Constants.name), siConstants.siVerbose)
    return True


def TCPServer_start_Execute():
    Application.LogMessage("{0} | 'TCPServer_start_Execute' called!".format(
        Constants.name), siConstants.siVerbose)
    _start_server()
    return True


def TCPServer_stop_Init(context):
    Application.LogMessage("{0} | 'TCPServer_stop_Init' called!".format(
        Constants.name), siConstants.siVerbose)
    return True


def TCPServer_stop_Execute():
    Application.LogMessage("{0} | 'TCPServer_stop_Execute' called!".format(
        Constants.name), siConstants.siVerbose)
    _stop_server()
    return True


def TCPServer_timerEvent_OnEvent(context):
    # Application.LogMessage("{0} | 'TCPServer_timerEvent' called!".format(
    # Constants.name), siConstants.siVerbose)
    Runtime.requests_handler.process_data()
    return False


def TCPServer_Init(context):
    menu = context.Source
    menu.AddCallbackItem("TCPServer Preferences", "TCPServer_Preferences_Clicked")
    return True


def TCPServer_Preferences_Clicked(context):
    Application.SIAddProp("TCPServer_property", "Scene_Root", siConstants.siDefaultPropagation)
    Application.InspectObj("TCPServer_property", "", "TCPServer_property")
    return True


def TCPServer_property_Define(context):
    property = context.Source
    property.AddParameter2("Logo_siString", siConstants.siString)
    property.AddParameter2("Address_siString", siConstants.siString, Runtime.address)
    property.AddParameter2("Port_siInt", siConstants.siInt4, Runtime.port, 0, 65535, 0, 65535)
    property.AddParameter2("RequestsHandlers_siInt",
                           siConstants.siInt4,
                           _get_requests_handlers().index(Runtime.requests_handler))
    return True


def TCPServer_property_DefineLayout(context):
    layout = context.Source
    layout.Clear()

    Logo_siControlBitmap = layout.AddItem("Logo_siString", "", siConstants.siControlBitmap)
    Logo_siControlBitmap.SetAttribute(siConstants.siUIFilePath, os.path.join(__sipath__, Constants.logo))
    Logo_siControlBitmap.SetAttribute(siConstants.siUINoLabel, True)

    layout.AddGroup("Server", True, 0)
    layout.AddItem("Address_siString", "Address")
    layout.AddItem("Port_siInt", "Port")
    requests_handlers = [requestsHandler.__name__ for requestsHandler in _get_requests_handlers()]
    layout.AddEnumControl("RequestsHandlers_siInt",
                          list(itertools.chain.from_iterable(zip(requests_handlers, range(len(requests_handlers))))),
                          "Requests Handlers", siConstants.siControlCombo)
    layout.EndGroup()

    # layout.AddGroup()
    # layout.AddRow()
    # layout.AddButton("Start_Server_button", "Start TCPServer")
    # layout.AddGroup()
    # layout.EndGroup()
    # layout.AddButton("Stop_Server_button", "Stop TCPServer")
    # layout.EndRow()
    # layout.EndGroup()
    return True


def TCPServer_property_Address_siString_OnChanged():
    Runtime.address = PPG.Address_siString.Value
    _store_settings()

    # module = _get_module()
    # if not module:
    # 	return

    # module.Runtime.address = PPG.Address_siString.Value
    # module._store_settings()
    # module._restart_server()
    return True


def TCPServer_property_Port_siInt_OnChanged():
    Runtime.port = PPG.Port_siInt.Value
    _store_settings()

    # module = _get_module()
    # if not module:
    # 	return

    # module.Runtime.port = PPG.Port_siInt.Value
    # module._store_settings()
    # module._restart_server()
    return True


def TCPServer_property_RequestsHandlers_siInt_OnChanged():
    Runtime.requests_handler = _get_requests_handlers()[PPG.RequestsHandlers_siInt.Value]
    _store_settings()

    # module = _get_module()
    # if not module:
    # 	return

    # module.Runtime.requests_handler = getattr(_get_module(),
    # _get_requests_handlers()[PPG.RequestsHandlers_siInt.Value].__name__)
    # module._store_settings()
    # module._restart_server()
    return True


def TCPServer_property_Start_Server_button_OnClicked():
    # module = _get_module()
    # if not module:
    # 	return

    # module._start_server()
    return True


def TCPServer_property_Stop_Server_button_OnClicked():
    # module = _get_module()
    # if not module:
    # 	return

    # module._stop_server()
    return True


def _register_settings_property():
    if not Application.Preferences.Categories(Constants.settings):
        property = Application.ActiveSceneRoot.AddCustomProperty(Constants.settings)
        property.AddParameter2("Address_siString", siConstants.siString, Constants.default_address)
        property.AddParameter2("Port_siInt", siConstants.siInt4, Constants.default_port, 0, 65535, 0, 65535)
        property.AddParameter2("RequestsHandler_siInt",
                               siConstants.siInt4,
                               _get_requests_handlers().index(Constants.default_requests_handler))
        Application.InstallCustomPreferences("TCPServer_settings_property", "TCPServer_settings_property")
    return True


def _store_settings():
    if Application.Preferences.Categories(Constants.settings):
        Application.preferences.SetPreferenceValue("{0}.Address_siString".format(Constants.settings), Runtime.address)
        Application.preferences.SetPreferenceValue("{0}.Port_siInt".format(Constants.settings), Runtime.port)
        Application.preferences.SetPreferenceValue(
            "{0}.RequestsHandler_siInt".format(Constants.settings),
            _get_requests_handlers().index(Runtime.requests_handler))
    return True


def _restore_settings():
    if Application.Preferences.Categories(Constants.settings):
        Runtime.address = unicode(Application.preferences.GetPreferenceValue(
            "{0}.Address_siString".format(Constants.settings)))
        Runtime.port = int(Application.preferences.GetPreferenceValue("{0}.Port_siInt".format(Constants.settings)))
        Runtime.requests_handler = _get_requests_handlers()[int(Application.preferences.GetPreferenceValue(
            "{0}.RequestsHandler_siInt".format(Constants.settings)))]
    return True


def _get_server(address, port, requests_handler):
    return TCPServer(address, port, requests_handler)


def _start_server():
    if Runtime.server:
        if Runtime.server.online:
            Application.LogMessage("{0} | The server is already online!".format(Constants.name), siConstants.siWarning)
            return

    Runtime.server = _get_server(Runtime.address, Runtime.port, Runtime.requests_handler)
    Runtime.server.start()
    return True


def _stop_server():
    if Runtime.server:
        if not Runtime.server.online:
            Application.LogMessage("{0} | The server is not online!".format(Constants.name), siConstants.siWarning)
            return

    Runtime.server and Runtime.server.stop()
    return True


def _restart_server():
    if Runtime.server:
        Runtime.server.online and _stop_server()

    _start_server()
    return True


def _get_module():
    # Garbage Collector wizardry to retrieve the actual module object.
    import gc

    for object in gc.get_objects():
        if not hasattr(object, "__uid__"):
            continue

        if getattr(object, "__uid__") == __uid__:
            return object


def _get_requests_handlers():
    requests_handlers = []
    for object in sorted(globals().values()):
        if not inspect.isclass(object):
            continue

        if issubclass(object, SocketServer.BaseRequestHandler):
            requests_handlers.append(object)

    return sorted(requests_handlers, key=lambda x: x.__name__)

    # Module introspection to retrieve the requests handlers classes.
    # module = _get_module()
    # requests_handlers = []
    # for attribute in dir(module):
    # 	object = getattr(module, attribute)
    # 	if not inspect.isclass(object):
    # 		continue

    # 	if issubclass(object, SocketServer.BaseRequestHandler):
    # 		requests_handlers.append(object)
    # return sorted(requests_handlers, key=lambda x:x.__name__)

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
**reStructuredText_to_html.py**

**Platform:**
	Windows, Linux, Mac Os X.

**Description:**
	Converts a reStructuredText file to html.

**Others:**

"""

from __future__ import unicode_literals

import argparse
import os
import sys

import foundations.decorators
import foundations.verbose
from foundations.io import File

__author__ = "Thomas Mansencal"
__copyright__ = "Copyright (C) 2008 - 2014 - Thomas Mansencal"
__license__ = "GPL V3.0 - http://www.gnu.org/licenses/"
__maintainer__ = "Thomas Mansencal"
__email__ = "thomas.mansencal@gmail.com"
__status__ = "Production"

__all__ = ["LOGGER",
		   "RESOURCES_DIRECTORY",
		   "CSS_FILE",
		   "TIDY_SETTINGS_FILE",
		   "RST2HTML",
		   "reStructuredText_to_html",
		   "get_command_line_arguments",
		   "main"]

LOGGER = foundations.verbose.install_logger()

RESOURCES_DIRECTORY = os.path.join(os.path.dirname(__file__))

CSS_FILE = os.path.join(RESOURCES_DIRECTORY, "css", "style.css")
TIDY_SETTINGS_FILE = os.path.join(RESOURCES_DIRECTORY, "tidy", "tidy_settings.rc")

RST2HTML = "rst2html.py"

foundations.verbose.get_logging_console_handler()
foundations.verbose.set_verbosity_level(3)

def reStructuredText_to_html(input, output, css_file):
	"""
	Outputs a reStructuredText file to html.

	:param input: Input reStructuredText file to convert.
	:type input: unicode
	:param output: Output html file.
	:type output: unicode
	:param css_file: Css file.
	:type css_file: unicode
	:return: Definition success.
	:rtype: bool
	"""

	LOGGER.info("{0} | Converting '{1}' reStructuredText file to html!".format(reStructuredText_to_html.__name__, input))
	os.system("{0} --stylesheet-path='{1}' '{2}' > '{3}'".format(RST2HTML,
																 os.path.join(os.path.dirname(__file__), css_file),
																 input,
																 output))

	LOGGER.info("{0} | Formatting html file!".format("Tidy"))
	os.system("tidy -config {0} -m '{1}'".format(os.path.join(os.path.dirname(__file__), TIDY_SETTINGS_FILE), output))

	file = File(output)
	file.cache()
	LOGGER.info("{0} | Replacing spaces with tabs!".format(reStructuredText_to_html.__name__))
	file.content = [line.replace(" " * 4, "\t") for line in file.content]
	file.write()

	return True

def get_command_line_arguments():
	"""
	Retrieves command line arguments.

	:return: Namespace.
	:rtype: Namespace
	"""

	parser = argparse.ArgumentParser(add_help=False)

	parser.add_argument("-h",
						"--help",
						action="help",
						help="'Displays this help message and exit.'")

	parser.add_argument("-i",
						"--input",
						type=unicode,
						dest="input",
						help="'Input reStructuredText file to convert.'")

	parser.add_argument("-o",
						"--output",
						type=unicode,
						dest="output",
						help="'Output html file.'")

	parser.add_argument("-c",
						"--css_file",
						type=unicode,
						dest="css_file",
						help="'Css file.'")

	if len(sys.argv) == 1:
		parser.print_help()
		sys.exit(1)

	return parser.parse_args()

@foundations.decorators.system_exit
def main():
	"""
	Starts the Application.

	:return: Definition success.
	:rtype: bool
	"""

	args = get_command_line_arguments()
	args.css_file = args.css_file if foundations.common.path_exists(args.css_file) else CSS_FILE
	return reStructuredText_to_html(args.input,
								  args.output,
								  args.css_file)

if __name__ == "__main__":
	main()

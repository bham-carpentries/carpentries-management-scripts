import configparser

def read_settings(settings_file):
	"""
	Read settings for the program using ConfigParser.

	args:
		settings_file: filename to read

	returns:
		Result from configparser of reading the settings
	"""
	cp = configparser.ConfigParser()
	cp.read(settings_file)
	if not cp.sections():
		logger.error("Unable to read any settings from '%s'.", settings_file)
		raise RuntimeError("Unable to read settings.")

	return cp
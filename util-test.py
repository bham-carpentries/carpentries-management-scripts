import logging
import os
import tempfile
import unittest

import util

class SettingsLoader(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		"""
		Create a dummy settings file.
		"""
		if getattr(cls, '_dummysettings', None) is None:
			(handle, path) = tempfile.mkstemp()
			os.close(handle)
			with open(path, 'w') as f:
				f.write("""
[github]
accesstoken = 12345
""")

			cls._dummysettings = path
			logging.debug("Created temporary settings file: %s", cls._dummysettings)


	@classmethod
	def tearDownClass(cls):
		# Clean up the temporary file.
		try:
			os.remove(cls._dummysettings)
			cls._dummysettings = None
		except AttributeError:
			# If no _dummysettings, carry on as it wasn't created
			pass


	def test_load_settings(self):
		settings = util.read_settings(self._dummysettings)
		self.assertIn('github', settings)
		self.assertIn('accesstoken', settings['github'])
		self.assertEqual(settings.get('github', 'accesstoken'), '12345')
		self.assertEqual(settings['github']['accesstoken'], '12345')

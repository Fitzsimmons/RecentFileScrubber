import gconf
import pyinotify
import glib
import gtk

import os
import shutil
import tempfile

from lxml import etree

class RecentFileScrubber(pyinotify.ProcessEvent):

	def __init__(self):
		self.blacklist = []
		self.action = None
		self.client = gconf.client_get_default()
		self.watching = False
		self.wdd = None
		
		self.xpath_query = "false"
		
		self.gconf_dir = '/apps/recent-file-scrubber'
		self.blacklist_key = '/apps/recent-file-scrubber/blacklist'
		self.action_key = '/apps/recent-file-scrubber/action'
		self.filename = '.recently-used.xbel'
		self.directory = os.path.expanduser('~/')
		if "SCRUBBER_DEBUG" in os.environ.keys() and os.environ["SCRUBBER_DEBUG"] == "1":
			self.debug = True
		else:
			self.debug = False

	def main(self):

		if self.debug:
			print "Debug mode on"

		self.client.add_dir(self.gconf_dir, gconf.CLIENT_PRELOAD_NONE)
		self.client.notify_add(self.blacklist_key, self.update_blacklist)
		self.client.notify_add(self.action_key, self.update_action)
		self.wm = pyinotify.WatchManager()
		self.notifier = pyinotify.Notifier(self.wm, self, timeout=10)
		self.update_action()
		self.update_blacklist()

		gtk.main()
	
	def begin_watch(self):
		if not self.watching:
			self.wdd = self.wm.add_watch(self.directory, pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO)
			if self.debug:
				print "Added watch to %s" % (self.directory,)
			
			glib.timeout_add_seconds(1, self.quick_check)
			self.watching = True
		
	
	def cancel_watch(self):
		if self.watching:
			self.wm.rm_watch(self.wdd[self.file_path])
			self.watching = False
	
	def __update_xpath_query(self):
		if len(self.blacklist) == 0:
			self.xpath_query = "false"
			return
		
		query = '/xbel/bookmark['
		first = True
		for p in self.blacklist:
			if not first:
				query += ' or '
			else:
				first = False

			query += 'contains(@href, "%s")' % (p,)
		query += ' and not(private)]'
		if self.action == "hide":
			query += "/info/metadata"
		
		self.xpath_query = query
		if self.debug:
			print "Xpath query updated: %s" % (query,)
	
	def update_blacklist(self, *throwaway):
		self.blacklist = self.client.get_list(self.blacklist_key, gconf.VALUE_STRING)
		if self.debug:
			print "Blacklist updated:"
			print self.blacklist
		
		self.__update_xpath_query()
		self.update_bookmark_file()
		
		if len(self.blacklist) > 0:
			self.begin_watch()
		else:
			self.cancel_watch()
	
	def update_action(self, *throwaway):
		possible = self.client.get_string(self.action_key)
		assert possible in ["hide", "delete"], 'Action must be either hide or delete'
		self.action = possible
		
		if self.debug:
			print "Action is now set to %s" % (possible,)
			
		self.__update_xpath_query()
		self.update_bookmark_file()
		
	def quick_check(self):
		assert self.notifier._timeout is not None, 'Notifier must be constructed with a short timeout'
		while self.notifier.check_events():  #loop in case more events appear while we are processing
                	self.notifier.read_events()
                	self.notifier.process_events()
		
		return self.watching

	def is_correct_event(self, event):
		return event.name == self.filename
	
	def update_bookmark_file(self):
		if self.debug:
			print "Scanning bookmark file for changes"
		
		if len(self.blacklist) > 0:
			#open the file in readonly mode so as to not trigger this event recursively
			f = open(os.path.join(self.directory, self.filename), 'r')
			tree = etree.parse(f)
			f.close()

			elements = tree.xpath(self.xpath_query)
			if len(elements) > 0:
				for e in elements:
					if self.action == "hide":
						etree.SubElement(e, "private")
						if self.debug:
							print "Added private element to bookmark: %s" % (e.get("href"),)
					elif self.action == "delete":
						tree.getroot().remove(e)
					else:
						raise ValueError('Unhandled action: %s' % (self.action,))
			
				o = tempfile.NamedTemporaryFile(prefix=self.filename, dir=self.directory, delete=False)
				tree.write(o)
				o.close()
				shutil.move(o.name, os.path.join(self.directory, self.filename))
	

	def process_IN_MOVED_TO(self, event):
		if self.is_correct_event(event):
			self.update_bookmark_file()

	def process_IN_CLOSE_WRITE(self, event):
		if self.is_correct_event(event):
			self.update_bookmark_file()
		

if __name__ == "__main__":
	r = RecentFileScrubber()
	r.main()

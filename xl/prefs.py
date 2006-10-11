# Copyright (C) 2006 Adam Olsen
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 1, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

import thread, os, os.path, string
from xl import tracks, xlmisc, media
from gettext import gettext as _
import pygtk, common
pygtk.require('2.0')
import gtk, gtk.glade, pango, subprocess
try:
    import gpod
    IPOD_AVAILABLE = True
except:
    IPOD_AVAILABLE = False

try:
    import gamin
    GAMIN_AVAIL = True
except ImportError:
    GAMIN_AVAIL = False

settings = None
xml = None

class PrefsItem(object):
    """
        Representing a gtk.Entry preferences item
    """
    def __init__(self, name, default, change=None, done=None):
        """
            Initializes the preferences item
            expects the name of the widget in the .glade file, the default for
            this setting, an optional function to be called when the value is
            changed, and an optional function to be called when this setting
            is applied
        """

        self.widget = xml.get_widget('prefs_%s' % name)
        self.name = name
        self.default = default
        self.change = change
        self.done = done

        self.set_pref()
        if change: 
            self.setup_change()

    def setup_change(self):
        """
            Sets up the function to be called when this preference is changed
        """
        self.widget.connect('focus-out-event',
            self.change, self.name, self.widget.get_text())
        self.widget.connect('activate',
            lambda *e: self.change(self.widget, None, self.name,
                self.widget.get_text()))

    def set_pref(self):
        """ 
            Sets the GUI widget up for this preference
        """
        self.widget.set_text(str(settings.get(self.name, self.default)))

    def do_done(self):
        """
            Calls the done function
        """
        return self.done(self.widget)

    def apply(self):
        """
            applies this setting
        """
        if self.done and not self.do_done(): return False
        settings[self.name] = self.widget.get_text()
        return True
       
class CheckPrefsItem(PrefsItem):
    """
        A class to represent check boxes in the preferences window
    """
    def __init__(self, name, default, change=None, done=None):
        PrefsItem.__init__(self, name, default, change, done)

    def setup_change(self):
        self.widget.connect('toggled',
            self.change)

    def set_pref(self):
        self.widget.set_active(settings.get_boolean(self.name,
            self.default))

    def apply(self):
        if self.done and not self.do_done(): return False
        settings.set_boolean(self.name, self.widget.get_active())
        return True

class ColorButtonPrefsItem(PrefsItem):
    """
        A class to represent the color button in the prefs window
    """
    def __init__(self, name, default, change=None, done=None):
        PrefsItem.__init__(self, name, default, change, done)

    def setup_change(self):
        self.widget.connect('color-set',
            self.change, self.name)

    def set_pref(self):
        self.widget.set_color(gtk.gdk.color_parse(
            settings.get(self.name, self.default)))

    def apply(self):
        if self.done and not self.do_done(): return False
        color = self.widget.get_color()
        string = "#%x%x%x" % (color.red / 257, color.green / 257, 
            color.blue / 257)
        settings[self.name] = string
        return True

class FontButtonPrefsItem(ColorButtonPrefsItem):
    """
        Font button
    """
    def __init__(self, name, default, change=None, done=None):
        ColorButtonPrefsItem.__init__(self, name, default, change, done)

    def setup_change(self):
        self.widget.connect('font-set', self.change, self.name)

    def set_pref(self):
        font = settings.get(self.name, self.default)
        self.widget.set_font_name(font)
        
    def apply(self):
        if self.done and not self.do_don(): return False
        font = self.widget.get_font_name()
        settings[self.name] = font
        return True

class DirPrefsItem(PrefsItem):
    """
        Directory chooser button
    """
    def __init__(self, name, default, change=None, done=None):
        PrefsItem.__init__(self, name, default, change, done)

    def setup_change(self):
        pass

    def set_pref(self):
        """
            Sets the current directory
        """
        directory = settings.get(self.name, self.default)
        self.widget.set_filename(directory)

    def apply(self):
        if self.done and not self.do_done(): return False
        directory = self.widget.get_filename()
        settings[self.name] = directory
        return True

class ComboPrefsItem(PrefsItem):
    """
        combo box
    """
    def __init__(self, name, default, change=None, done=None):
        PrefsItem.__init__(self, name, default, change, done)

    def setup_change(self):
        self.widget.connect('changed',
            self.change)

    def set_pref(self):
        item = settings.get(self.name, self.default)

        model = self.widget.get_model()
        iter = model.get_iter_first()
        count = 0
        while True:
            value = model.get_value(iter, 0)
            if value == item:
                self.widget.set_active(count)
                break
            count += 1
            iter = model.iter_next(iter)
            if not iter: break

    def apply(self):
        if self.done and not self.do_done(): return False
        settings[self.name] = self.widget.get_active_text()
        return True

class Preferences(object):
    """
        Preferences Dialog
    """
    order = ('General', 'Advanced')
    items = ({'General':
                ('Miscellaneous',
                'OSD',
                'Last.fm'),
            'Advanced':
                ('iPod',
                'Playback',
                'Streamripper',
                'Locale')
            })
    def __init__(self, parent):
        """
            Initilizes the preferences dialog
        """

        global settings, xml

        self.exaile = parent
        self.fields = []
        self.popup = None
        self.osd_settings = xlmisc.get_popup_settings(self.exaile.settings)
        settings = self.exaile.settings
        self.xml = gtk.glade.XML('exaile.glade', 'PreferencesDialog', 'exaile')
        xml = self.xml
        self.window = self.xml.get_widget('PreferencesDialog')
        self.window.set_transient_for(parent.window)

        self.nb = self.xml.get_widget('prefs_nb')
        self.nb.set_show_tabs(False)

        self.tree = self.xml.get_widget('prefs_tree')
        text = gtk.CellRendererText()
        col = gtk.TreeViewColumn('Preferences', text, text=0)
        self.tree.append_column(col)
        self.tree.connect('button_press_event',
            self.switch_pane)

        self.xml.get_widget('prefs_cancel_button').connect('clicked',
            lambda *e: self.cancel())
        self.xml.get_widget('prefs_apply_button').connect('clicked',
            self.apply)

        self.xml.get_widget('prefs_ok_button').connect('clicked',
            self.ok)
        self.label = self.xml.get_widget('prefs_frame_label')

        self.model = gtk.TreeStore(str, int)

        self.tree.set_model(self.model)
    
        count = 0
        for header in self.order:
            items = self.items[header]
            node = self.model.append(None, [header, 0]) 
            for item in items:
                self.model.append(node, [item, count])
                count += 1
            self.tree.expand_row(self.model.get_path(node), False)

        selection = self.tree.get_selection()
        selection.select_path((0,0))
        xml.get_widget('prefs_lastfm_pass').set_invisible_char('*')
        xml.get_widget('prefs_audio_sink').set_active(0)

        simple_settings = ({
            'use_splash': (CheckPrefsItem, True),
            'use_streamripper': (CheckPrefsItem, False,
                self.__check_streamripper),
            'streamripper_save_location': (DirPrefsItem, os.getenv("HOME")),
            'streamripper_relay_port': (PrefsItem, '8000'),
            'kill_streamripper': (CheckPrefsItem, True),
            'watch_directories': (CheckPrefsItem, False, self.__check_gamin,
                self.__setup_gamin),
            'watch_exclude_dirs': (PrefsItem, 'incomplete'),
            'fetch_covers': (CheckPrefsItem, True),
            'save_queue': (CheckPrefsItem, True),
            'ensure_visible': (CheckPrefsItem, True),
            'art_filenames': (PrefsItem, 
                'cover.jpg folder.jpg .folder.jpg album.jpg art.jpg'),
            'open_last': (CheckPrefsItem, True),
            'use_popup': (CheckPrefsItem, True),
            'osd_w': (PrefsItem, '400', self.osd_adjust_size),
            'osd_h': (PrefsItem, '95', self.osd_adjust_size),
            'lastfm_user': (PrefsItem, ''),
            'lastfm_pass': (PrefsItem, '', None, self.setup_lastfm),
            'ipod_mount': (PrefsItem, '/media/ipod'),
            'as_submit_ipod': (CheckPrefsItem, False), 
            'audio_sink': (ComboPrefsItem, 'Use GConf Settings'),
            'osd_large_text_font': (FontButtonPrefsItem, 'Sans 14',
                self.osd_fontpicker),
            'osd_small_text_font': (FontButtonPrefsItem, 'Sans 9',
                self.osd_fontpicker),
            'osd_textcolor': (ColorButtonPrefsItem, '#ffffff',
                self.osd_colorpicker),
            'osd_bgcolor': (ColorButtonPrefsItem, '#567ea2',
                self.osd_colorpicker),
            'use_tray': (CheckPrefsItem, True, None, self.setup_tray),
            'tab_placement': (ComboPrefsItem, 'Top', None, self.setup_tabs),
            'amazon_locale': (PrefsItem, 'us'),
            'wikipedia_locale': (PrefsItem, 'us'),
        })

        for setting, value in simple_settings.iteritems():
            c = value[0]
            default = value[1]
            if len(value) == 3: change = value[2]
            else: change = None

            if len(value) == 4: done = value[3]
            else: done = None
            item = c(setting, default, change, done)
            self.fields.append(item)

    def __check_gamin(self, widget):
        """
            Make sure gamin is availabe
        """
        if widget.get_active():
            if not GAMIN_AVAIL:
                common.error(self.exaile.window,
                    _("Cannot watch directories for changes. "
                    "Install python2.4-gamin to use this feature."))
                widget.set_active(False)
                return False

    def __check_streamripper(self, widget):
        """
            Make sure that streamripper can be found on the system
        """
        if widget.get_active():
            try:
                ret = subprocess.call(['streamripper'], stdout=-1, stderr=-1)
            except OSError:
                common.error(self.exaile.window, _("Sorry, the 'streamripper'"
                    " executable could not be found in your path"))
                widget.set_active(False)
                return False

    def setup_lastfm(self, widget):
        """
            Connects to last.fm if the password field isn't empty
        """
        if not widget.get_text(): return True
        user = xml.get_widget('prefs_lastfm_user').get_text()
        password = widget.get_text()

        thread.start_new_thread(media.get_scrobbler_session,
            (self.exaile, user, password, True))
        return True

    def __setup_gamin(self, widget):
        """
            Sets up gamin if needs be
        """
        if widget.get_active() and not self.exaile.mon:
            self.exaile.setup_gamin(True)
        return True

    def setup_tabs(self, widget, *p):
        """
            Sets up tab placement for the playlists tab
        """

        text = widget.get_active_text()
        self.exaile.set_tab_placement(text)
        return True

    def ok(self, widget):
        """
            Called when the user clicks 'ok'
        """
        if self.apply(None): 
            self.cancel()
            self.window.hide()
            self.window.destroy()

    def apply(self, widget):
        """
            Applies settings
        """
        for item in self.fields:
            if not item.apply():
                print item.name
                return False

        xlmisc.POPUP = None

        return True

    def setup_tray(self, widget, event=None):
        """
            Sets up the tray icon
        """
        val = widget.get_active()

        if val: self.exaile.setup_tray()
        else: self.exaile.remove_tray()
        return True

    def osd_adjust_size(self, widget, event, name, previous):
        """
            Called when the user requests to adjust the size of the osd
        """

        try:
            val = int(widget.get_text())
        except ValueError:
            widget.set_text(previous)
            return
        
        self.osd_settings[name] = val
        self.display_popup()

    def osd_colorpicker(self, widget, name):
        """
            Shows a colorpicker
        """
        color = widget.get_color()
        string = "#%x%x%x" % (color.red / 257, color.green / 257, 
            color.blue / 257)

        self.osd_settings[name] = string
        self.display_popup()

    def osd_fontpicker(self, widget, name):
        """
            Gets the font from the font picker, and re-sets up the OSD window
        """

        self.osd_settings[name] = widget.get_font_name()
        self.display_popup()

    def cancel(self):
        """
            Closes the preferences dialog, ensuring that the osd popup isn't
            still showing
        """
        if self.popup:
            self.popup.window.hide()
            self.popup.window.destroy()
        self.window.hide()
        self.window.destroy()

    def switch_pane(self, button, event):
        """
            Switches a pane
        """
        (x, y) = event.get_coords()
        x = int(x); y = int(y)
        
        path = self.tree.get_path_at_pos(x, y)
        if not path: return
        iter = self.model.get_iter(path[0])
        if self.model.iter_has_child(iter): return
        index = self.model.get_value(iter, 1)
        self.nb.set_current_page(index)
        page = self.nb.get_nth_page(index)
        title = self.nb.get_tab_label(page)
        self.label.set_markup("<b>%s</b>" % title.get_label())
        if index == 1: 
            self.osd_settings = xlmisc.get_popup_settings(self.exaile.settings)
            self.display_popup()
        else:
            if self.popup:
                self.popup.window.destroy()
                self.popup = None

    def display_popup(self):
        """
            Shows the OSD window
        """
        if self.popup:  
            (x, y) = self.popup.window.get_position()
            self.osd_settings['osd_x'] = x
            self.osd_settings['osd_y'] = y
            self.popup.window.destroy()
        self.popup = xlmisc.PopupWindow(self.exaile, self.osd_settings,
            False, True)
        self.popup.show_popup('On Screen Display', ' ',
            'Drag this window to the desired position', 
            'images%snocover.png' % os.sep)       

    def run(self):
        """
            Runs the dialog
        """
        self.window.show_all()

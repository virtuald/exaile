# -*- coding: utf-8  -*-
from __future__ import with_statement

import os
import shutil
import tempfile
import unittest
import logging
import weakref

import mox
import gio
import gobject
try:
    from nose.plugins.skip import SkipTest
except ImportError:
    SkipTest = None

import xl.trax.track as track
import xl.settings as settings


LOG = logging.getLogger(__name__)
TEST_TRACKS = [os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
    'data', 'music', 'delerium', 'chimera', '05 - Truly') + os.extsep + ext)
    for ext in ('aac', 'aiff', 'au', 'flac', 'mp3', 'mpc', 'ogg', 'spx',
                'wav', 'wma', 'wv')]
def get_file_with_ext(ext):
    return [x for x in TEST_TRACKS if x.endswith(ext)][0]
TEST_TRACKS_SIZE = {
    get_file_with_ext('.mp3'): 4692,
}

def test_mp3_exists():
    assert get_file_with_ext('.mp3')

def test_all_tracks_exist():
    for track in TEST_TRACKS:
        assert os.path.exists(track), "%s does not exist" % track


class Test_MetadataCacher(unittest.TestCase):

    TIMEOUT = 2000
    MAX_ENTRIES = 2048

    def setUp(self):
        self.mox = mox.Mox()
        self.mc = track._MetadataCacher(self.TIMEOUT, self.MAX_ENTRIES)

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_add(self):
        timeout_id = 1
        self.mox.StubOutWithMock(gobject, 'timeout_add')
        self.mox.StubOutWithMock(gobject, 'source_remove')
        gobject.timeout_add(
                self.TIMEOUT,
                self.mc.remove,
                'foo').AndReturn(timeout_id)

        self.mox.ReplayAll()
        self.mc.add('foo', 'bar')
        self.assertEqual(self.mc.get('foo'), ['bar', 1])
        self.mox.VerifyAll()

    def test_double_add(self):
        timeout_id = 1
        self.mox.StubOutWithMock(gobject, 'timeout_add')
        self.mox.StubOutWithMock(gobject, 'source_remove')
        gobject.timeout_add(
                self.TIMEOUT,
                self.mc.remove,
                'foo').AndReturn(timeout_id)
        gobject.timeout_add(
                self.TIMEOUT,
                self.mc.remove,
                'foo').AndReturn(timeout_id + 1)
        gobject.source_remove(timeout_id)

        self.mox.ReplayAll()
        self.mc.add('foo', 'bar')
        self.assertEqual(self.mc.get('foo'), ['bar', 1])
        self.mc.add('foo', 'bar')
        self.assertEqual(self.mc.get('foo'), ['bar', 2])
        self.mox.VerifyAll()

    def test_remove(self):
        timeout_id = 1
        self.mox.StubOutWithMock(gobject, 'timeout_add')
        gobject.timeout_add(
                self.TIMEOUT,
                self.mc.remove,
                'foo').AndReturn(timeout_id)

        self.mox.ReplayAll()
        self.mc.add('foo', 'bar')
        self.mc.remove('foo')
        self.assertEqual(self.mc.get('foo'), None)
        self.mox.VerifyAll()

    def test_remove_not_exist(self):
        self.assertEqual(self.mc.remove('foo'), None)

class TestTrack(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()
        track.Track._Track__the_cuts = ['the', 'a']
        for key in track.Track._Track__tracksdict.keys():
            del track.Track._Track__tracksdict[key]

    def tearDown(self):
        self.mox.UnsetStubs()

    ## Creation
    def test_flyweight(self):
        """There can only be one object based on a url in args"""
        t1 = track.Track('uri')
        t2 = track.Track(uri='uri')
        self.assertTrue(t1 is t2, "%s is not %s" % (repr(t1), repr(t2)))

    def test_different_url_not_flyweighted(self):
        t1 = track.Track('uri')
        t2 = track.Track(uri='uri2')
        self.assertTrue(t1 is not t2, "%s is %s" % (repr(t1), repr(t2)))

    def test_none_url(self):
        self.assertRaises(ValueError, track.Track)

    def test_pickles(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('artist', 'bar')
        self.assertEqual(tr._pickles(), {
            '__loc': u'file:///foo',
            'artist': [u'bar']
            })

    def test_unpickles(self):
        tr1 = track.Track(_unpickles={'artist': [u'my_artist'],
            '__loc': u'uri'})
        self.assertEqual(tr1.get_loc_for_io(), u'uri')

    def test_unpickles_flyweight(self):
        tr1 = track.Track(_unpickles={'artist': [u'my_artist'],
            '__loc': u'uri'})
        tr2 = track.Track(_unpickles={'artist': [u'my_artist'],
            '__loc': u'uri'})
        self.assertTrue(tr1 is tr2)

    def test_takes_nonurl(self):
        for tr in TEST_TRACKS:
            tr = track.Track(tr)
            self.assertTrue(tr.local_file_name())
            self.assertTrue(tr.exists())
    
    ## Information
    def test_local_type(self):
        for tr in TEST_TRACKS:
            tr = track.Track(tr)
            self.assertEqual(tr.get_type(), 'file')

    def test_is_local_local(self):
        """Tests a local filename -> True"""
        tr = track.Track('foo')
        self.assertEqual(tr.is_local(), True)

    def test_is_local_remote(self):
        """Tests a remote filename -> False"""
        tr = track.Track('http://foo')
        self.assertEqual(tr.is_local(), False)

    def test_local_filesize(self):
        for tr_name in TEST_TRACKS_SIZE:
            tr = track.Track(tr_name)
            self.assertEqual(tr.get_size(), TEST_TRACKS_SIZE[tr_name])

    def test_str(self):
        tr = track.Track('foo')
        self.assertEqual(str(tr), "'Unknown' from 'Unknown' by 'Unknown'")

    def test_read_tags_no_perms(self):
        # We test by creating a new file, changing the tags, writing tags
        # and finally reopening a track with the name and seeing if it stuck
        for tr_url in TEST_TRACKS:
            # We run through this process with each filetype we have
            suffix = os.extsep + tr_url.split(os.extsep)[-1]
            # Stuff we can't actually write metadata to
            if suffix in ('.aac', '.aiff', '.au', '.spx', '.wav'):
                LOG.info("Skipping tag write test for " + suffix)
                continue
            # This fails. i don't feel like reading about it's failing for now
            if suffix in ('.wma',):
                LOG.critical("Skipping known failure :" + suffix)
                continue
            LOG.info("Testing writes for filetype: " + suffix)
            with tempfile.NamedTemporaryFile(suffix=suffix) as temp_copy:
                # Copy and write new file
                shutil.copyfileobj(open(tr_url, 'r'), temp_copy)
                tr = track.Track(temp_copy.name)
                del tr
                os.chmod(temp_copy.name, 0o000)
                tr = track.Track(temp_copy.name)
                # Remove the artist tag and reread from file. This is done
                # because of the whole flyweight thing
                tr.set_tag_raw('artist', '')
                tr.read_tags()
                self.assertEqual(tr.get_tag_raw('artist'), None)

    def test_write_tags_no_perms(self):
        # We test by creating a new file, changing the tags, writing tags
        # and finally reopening a track with the name and seeing if it stuck
        for tr_url in TEST_TRACKS:
            # We run through this process with each filetype we have
            suffix = os.extsep + tr_url.split(os.extsep)[-1]
            # Stuff we can't actually write metadata to
            if suffix in ('.aac', '.aiff', '.au', '.spx', '.wav'):
                LOG.info("Skipping tag write test for " + suffix)
                continue
            # This fails. i don't feel like reading about it's failing for now
            if suffix in ('.wma',):
                LOG.critical("Skipping known failure :" + suffix)
                continue
            LOG.info("Testing writes for filetype: " + suffix)
            with tempfile.NamedTemporaryFile(suffix=suffix) as temp_copy:
                # Copy and write new file
                shutil.copyfileobj(open(tr_url, 'r'), temp_copy)
                os.chmod(temp_copy.name, 0o444)
                tr = track.Track(temp_copy.name)
                tr.set_tag_raw('artist', 'Delerium')
                self.assertFalse(tr.write_tags())

    def test_write_tags(self):
        # We test by creating a new file, changing the tags, writing tags
        # and finally reopening a track with the name and seeing if it stuck
        for tr_url in TEST_TRACKS:
            # We run through this process with each filetype we have
            suffix = os.extsep + tr_url.split(os.extsep)[-1]
            # Stuff we can't actually write metadata to
            if suffix in ('.aac', '.aiff', '.au', '.spx', '.wav'):
                LOG.info("Skipping tag write test for " + suffix)
                continue
            # This fails. i don't feel like reading about it's failing for now
            if suffix in ('.wma',):
                LOG.critical("Skipping known failure :" + suffix)
                continue
            LOG.info("Testing writes for filetype: " + suffix)
            with tempfile.NamedTemporaryFile(suffix=suffix) as temp_copy:
                # Copy and write new file
                shutil.copyfileobj(open(tr_url, 'r'), temp_copy)
                tr = track.Track(temp_copy.name)
                tr.set_tag_raw('artist', 'Delerium')
                tr.write_tags()
                del tr
                tr = track.Track(temp_copy.name)
                # Remove the artist tag and reread from file. This is done
                # because of the whole flyweight thing
                tr.set_tag_raw('artist', '')
                tr.read_tags()
                self.assertEqual(tr.get_tag_raw('artist'), [u'Delerium'])
        if SkipTest is not None:
            raise SkipTest("Skipped known failure: .wma")

    def test_write_tag_invalid_format(self):
        tr = track.Track('/tmp/foo.foo')
        self.assertEqual(tr.write_tags(), False)

    def test_join_tag_empty(self):
        """Tests get_tag_raw with join=True and an empty tag"""
        tr = track.Track('foo')
        self.assertEqual(tr.get_tag_raw('artist', join=True), None)

    def test_join_tag_one(self):
        """Tests get_tag_raw with join=True and one element in tag"""
        tr = track.Track('foo')
        tr.set_tag_raw('artist', 'foo')
        self.assertEqual(tr.get_tag_raw('artist', join=True), u'foo')

    def test_join_tag_two(self):
        """Tests get_tag_raw with join=True and one element in tag"""
        tr = track.Track('foo')
        tr.set_tag_raw('artist', [u'foo', u'bar'])
        self.assertEqual(tr.get_tag_raw('artist', join=True), u'foo / bar')

    def test_list_tags(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('artist', 'foo')
        tr.set_tag_raw('album', 'bar')
        self.assertEqual(tr.list_tags(), ['album', '__loc', 'artist'])

    def test_rating_empty(self):
        """Test get_rating when no rating has been set"""
        tr = track.Track('/foo')
        self.assertEqual(tr.get_rating(), 0)

    def test_set_rating(self):
        tr = track.Track('/foo')
        tr.set_rating(2)
        self.assertEqual(tr.get_rating(), 2)

    def test_set_rating_invalid(self):
        tr = track.Track('/bar')
        self.assertRaises(ValueError, tr.set_rating, 'foo')

    ## Tag Getting helper methods
    def test_split_numerical_none(self):
        self.assertEqual(track.Track.split_numerical(None), (0, 0))

    def test_split_numerical_str(self):
        fn = track.Track.split_numerical
        self.assertEqual(fn('12/15'), (12, 15))
        self.assertEqual(fn('foo/15'), (0, 15))
        self.assertEqual(fn('12/foo'), (12, 0))
        self.assertEqual(fn('12/15/2009'), (12, 15))

    def test_split_numerical_list(self):
        fn = track.Track.split_numerical
        self.assertEqual(fn(['12/15']), (12, 15))
        self.assertEqual(fn(['foo/15']), (0, 15))
        self.assertEqual(fn(['12/foo']), (12, 0))
        self.assertEqual(fn(['12/15/2009']), (12, 15))

    def test_strip_leading(self):
        # Strips whitespace if it's an empty string
        value = " `~!@#$%^&*()_+-={}|[]\\\";'<>?,./"
        retvalue = "`~!@#$%^&*()_+-={}|[]\\\";'<>?,./"
        self.assertEqual(track.Track.strip_leading(value), retvalue)
        self.assertEqual(track.Track.strip_leading(value + "foo"), "foo")

    def test_cutter(self):
        value = 'the a foo'
        self.assertEqual(track.Track.the_cutter(value), 'a foo')

    def test_expand_doubles(self):
        value = u'ßæĳŋœƕǆǉǌǳҥҵ'
        self.assertEqual(track.Track.expand_doubles(value),
                u'ssaeijngoehvdzljnjdzngts')

    def test_lower(self):
        value = u'FooBar'
        self.assertEqual(track.Track.lower(value), 'foobar FooBar')

    def test_cuts_cb(self):
        value = []
        settings.set_option('collection/strip_list', value)
        track.Track._the_cuts_cb(None, None, 'collection/strip_list')
        self.assertEqual(track.Track._Track__the_cuts, value)

        value = ['the', 'foo']
        settings.set_option('collection/strip_list', value)
        track.Track._the_cuts_cb(None, None, 'collection/strip_list')
        self.assertEqual(track.Track._Track__the_cuts, value)
    
    def test_strip_marks(self):
        value = u'The Hëllò Wóþλdâ'
        retval = u'The Hello Woþλda The Hëllò Wóþλdâ'
        self.assertEqual(track.Track.strip_marks(value), retval)

    ## Sort tags
    def test_get_sort_tag_no_join(self):
        tr = track.Track('/foo')
        value = u'hello'
        retval = [u'hello hello hello hello']
        tr.set_tag_raw('artist', value)
        self.assertEqual(tr.get_tag_sort('artist', join=False), retval)

    def test_get_sort_tag_discnumber(self):
        tr = track.Track('/foo')
        value = '12/15'
        retval = 12
        tr.set_tag_raw('discnumber', value)
        self.assertEqual(tr.get_tag_sort('discnumber'), retval)

    def test_get_sort_tag_tracknumber(self):
        tr = track.Track('/foo')

        value = '12/15'
        retval = 12
        tr.set_tag_raw('tracknumber', value)
        self.assertEqual(tr.get_tag_sort('tracknumber'), retval)

    def test_get_sort_tag_artist(self):
        tr = track.Track('/foo')
        value = u'The Hëllò Wóþλdâ'
        retval = u'hello woþλda the hëllò wóþλdâ ' \
                 u'The Hello Woþλda The Hëllò Wóþλdâ'
        tr.set_tag_raw('artist', value)
        self.assertEqual(tr.get_tag_sort('artist'), retval)

    def test_get_sort_tag_albumsort(self):
        tr = track.Track('/foo')
        value = u'the hello world'
        val_as = u'Foo Bar'
        retval = u'foo bar Foo Bar'
        tr.set_tag_raw('album', value)
        tr.set_tag_raw('albumsort', val_as)
        self.assertEqual(tr.get_tag_sort('album'), retval)

    def test_get_sort_tag_compilation_unknown(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__compilation', 'foo')
        # Does not actually modify anything
        value = u'hello world'
        retval = u' '.join([u'\uffff\uffff\uffff\ufffe'] * 4)
        tr.set_tag_raw('artist', value)
        self.assertEqual(tr.get_tag_sort('artist'), retval)

    def test_get_sort_tag_compilation_known(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__compilation', 'foo')
        value = u'foo bar'
        retval = u'foo bar foo bar'
        tr.set_tag_raw('artist', u'hello world')
        tr.set_tag_raw('albumartist', u'albumartist')
        tr.set_tag_raw('artistsort', value)
        self.assertEqual(tr.get_tag_sort('artist'), retval)

    def test_get_sort_tag_length(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__length', 36)
        self.assertEqual(tr.get_tag_sort('__length'), 36)

    def test_get_sort_tag_playcount(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__playcount', 36)
        self.assertEqual(tr.get_tag_sort('__playcount'), 36)

    def test_get_sort_tag_other(self):
        tr = track.Track('/foo')
        val = u'foobar'
        ret = u'foobar foobar foobar foobar'
        tr.set_tag_raw('coverart', u'foobar')
        self.assertEqual(tr.get_tag_sort('coverart'), ret)

    ## Display Tags
    def test_get_display_tag_loc(self):
        tr = track.Track('/foo')
        self.assertEqual(tr.get_tag_display('__loc'), '/foo')
        tr = track.Track('http://foo')
        self.assertEqual(tr.get_tag_display('__loc'), 'http://foo')

    def test_get_display_tag_compilation(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__compilation', u'foo')
        self.assertEqual(tr.get_tag_display('artist'),
                track._VARIOUSARTISTSSTR)

    def test_get_display_tag_discnumber(self):
        tr = track.Track('/foo')
        value = '12/15'
        retval = '12'
        tr.set_tag_raw('discnumber', value)
        self.assertEqual(tr.get_tag_display('discnumber'), retval)

    def test_get_display_tag_tracknumber(self):
        tr = track.Track('/foo')
        value = '12/15'
        retval = '12'
        tr.set_tag_raw('tracknumber', value)
        self.assertEqual(tr.get_tag_display('tracknumber'), retval)

    def test_get_display_tag_length(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__length', 360)
        self.assertEqual(tr.get_tag_display('__length'), u'360')

    def test_get_display_tag_bitrate(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__bitrate', 48000)
        self.assertEqual(tr.get_tag_display('__bitrate'), u'48k')

    def test_get_display_tag_bitrate_bitrateless_formate(self):
        tr = track.Track(get_file_with_ext('.flac'))
        self.assertEqual(tr.get_tag_display('__bitrate'), u' ')

    def test_get_display_tag_bitrate_bad(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__bitrate', u'lol')
        self.assertEqual(tr.get_tag_display('__bitrate'), u' ')

    def test_get_display_tag_numeric_zero(self):
        tr = track.Track('/foo')
        self.assertEqual(tr.get_tag_display('tracknumber'), u'0')
        self.assertEqual(tr.get_tag_display('discnumber'), u'0')
        self.assertEqual(tr.get_tag_display('__rating'), u'0')
        self.assertEqual(tr.get_tag_display('__playcount'), u'0')

    def test_get_display_tag_join_true(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('artist', [u'foo', u'bar'])
        self.assertEqual(tr.get_tag_display('artist'), 'foo & bar')

    def test_get_display_tag_join_false(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('artist', [u'foo', u'bar'])
        self.assertEqual(tr.get_tag_display('artist', join=False),
                [u'foo', u'bar'])

    ## Sort tags
    def test_get_search_tag_loc(self):
        tr = track.Track('/foo')
        self.assertEqual(tr.get_tag_search('__loc'), '__loc=="file:///foo"')

    def test_get_search_tag_artist_compilation(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__compilation', 'foo')
        retval = u'albumartist=="albumartist" ! __compilation==__null__'
        tr.set_tag_raw('artist', u'hello world')
        tr.set_tag_raw('albumartist', u'albumartist')
        tr.set_tag_raw('artistsort', u'foo bar')
        self.assertEqual(tr.get_tag_search('artist'), retval)

    def test_get_search_tag_artist(self):
        tr = track.Track('/foo')
        retval = u'artist=="hello world"'
        tr.set_tag_raw('artist', u'hello world')
        self.assertEqual(tr.get_tag_search('artist'), retval)

    def test_get_search_tag_artist_none(self):
        tr = track.Track('/foo')
        retval = u'artist==__null__'
        self.assertEqual(tr.get_tag_search('artist'), retval)

    def test_get_search_tag_discnumber(self):
        tr = track.Track('/foo')
        value = '12/15'
        retval = 'discnumber=="12"'
        tr.set_tag_raw('discnumber', value)
        self.assertEqual(tr.get_tag_search('discnumber'), retval)

    def test_get_search_tag_tracknumber(self):
        tr = track.Track('/foo')
        value = '12/15'
        retval = 'tracknumber=="12"'
        tr.set_tag_raw('tracknumber', value)
        self.assertEqual(tr.get_tag_search('tracknumber'), retval)

    def test_get_search_tag_length(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__length', 36)
        self.assertEqual(tr.get_tag_search('__length'), '__length=="36"')

    def test_get_search_tag_bitrate(self):
        tr = track.Track('/foo')
        tr.set_tag_raw('__bitrate', 48000)
        self.assertEqual(tr.get_tag_search('__bitrate'), '__bitrate=="48k"')

    ## Disk tags
    def test_get_disk_tag_length(self):
        tr_name = get_file_with_ext('.mp3')
        tr = track.Track(tr_name)
        self.assertEqual(tr.get_tag_disk('__length'),
                TEST_TRACKS_SIZE[tr_name])

    def test_get_disk_tag(self):
        tr_name = get_file_with_ext('.mp3')
        tr = track.Track(tr_name)
        self.assertEqual(tr.get_tag_disk('artist'), [u'Delerium'])

    def test_get_disk_tag_invalid_format(self):
        tr = track.Track('/tmp/foo.bah')
        self.assertEqual(tr.get_tag_disk('artist'), None)


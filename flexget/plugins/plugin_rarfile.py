from __future__ import unicode_literals, division, absolute_import
import logging
import os
import rarfile

from flexget import plugin
from flexget.entry import Entry
from flexget.event import event

log = logging.getLogger('rarfile')

def open_rar(rarpath):

    rar = None

    log.debug('Attempting to open RAR: %s' % rarpath)
    try:
        rar = rarfile.RarFile(rarfile=rarpath)
    except Exception as e:
        log.warn("Failed to open RAR: %s" % e)

    return rar


def to_url(path):
    """Convert a local file system to URL format"""

    url = path

    if not url.startswith('/'):
        url = item + '/'

    url = 'file:/' + url

    return url


class RarList(object):
    """
    Uses a local RAR file as an input and creates entries for files that match mask.

    You can specify either the mask key, in shell file matching format, (see python fnmatch module,)
    or regexp key.

    Example:

      rar_list:
        path: /downloads/episode.rar
        mask: *.mkv

    Example:

      rar_list:
        path: /downloads/episode.rar
        regexp: .*\.(avi|mkv)$
    """

    schema = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'format': 'file'},
            'mask': {'type': 'string'},
            'regexp': {'type': 'string', 'format': 'regex'}
        },
        'required': ['path'],
        'additionalProperties': False
    }

    def prepare_config(self, config):
        """Prepare the  mask/regexp provided in config"""

        from fnmatch import translate

        config.setdefault('recursive', False)
        # If mask was specified, turn it in to a regexp
        if config.get('mask'):
            config['regexp'] = translate(config['mask'])
        # If no mask or regexp specified, accept all files
        if not config.get('regexp'):
            config['regexp'] = '.'

    def on_task_input(self, task, config):
        """Creates entries for the contents of a RAR archive that match the provided pattern."""

        import re

        self.prepare_config(config)
        entries = []
        match = re.compile(config['regexp'], re.IGNORECASE).match
        rarpath = config['path']

        rar = open_rar(rarpath)

        if not rar:
            return

        url_prefix = to_url(rarpath)

        for info in rar.infolist():
            path = info.filename

            if not match(path):
                log.debug('File did not match regexp: %s' % path)
                continue

            log.debug('Found matching file: %s' %path)

            title = os.path.basename(path)
            url = url_prefix + '::' + path
            size = info.file_size
            timestamp = '%02i-%02i-%02i %02i:%02i:%02i' % info.date_time

            entry = Entry (
                    title = title,
                    location = path,
                    rar_path = rarpath,
                    url = url,
                    size = size,
                    timestamp = timestamp
                )

            entries.append(entry)

        return entries



class RarVolumes(object):
    """
    Creates entries for the files that compose a RAR archive (e.g. r01, r02, etc). This is useful 
    for deleting an archive once it's been extracted.

    Example:

      rar_volumes:
        path: /downloads/episode.rar
    """

    schema = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'format': 'file'}
        },
        'required': ['path'],
        'additionalProperties': False
    }

    def on_task_input(self, task, config):
        """Creates entries for the ."""

        entries = []
        rarpath = config['path']
        rar = open_rar(rarpath)

        if not rar:
            return

        for volume in rar.volumelist():
            
            url = to_url(volume)
            title = os.path.basename(volume)

            entry = Entry (
                    title = title,
                    location = volume,
                    url = url
                )

            entries.append(entry)

        return entries


class RarExtract(object):
    """
    Extracts files from RAR archives. By default this plugin will extract to the same directory as 
    the source archive, preserving directory structure from the archive.

    This plugin requires the unrar command line utility to extract compressed archives. If its 
    location is not specified in your PATH environment variable, you can specify its path using
    the unrar_tool config value.

    Example:

      rar_extract:
        to: '/Volumes/External/TV/Show/Season 1'

    Example:

      rar_extract:
        to: '/Volumes/External/TV/Show/Season 1'
        keep_dirs: no
        unrar_tool: '/unar/unrar'

    Example:

        rar_extract: yes
    """

    schema = {
        'anyOf': [
            {'type': 'boolean'},
            {
                'type': 'object',
                'properties': {
                    'to': {'type': 'string'},
                    'keep_dirs': {'type': 'boolean'},
                    'unrar_tool': {'type': 'string'}
                },
                'additionalProperties': False
            }
        ]
    }

    def prepare_config(self, config):
        if not isinstance(config, dict):
            config = {}

        config.setdefault('to', '')
        config.setdefault('keep_dirs', True)
        config.setdefault('unrar_tool', 'unrar')
        return config

    def handle_entry(self, entry, config):
        """Extract the file listed in entry"""

        rarpath = entry['rar_path']
        source_path = entry['location']
        source_file = os.path.basename(source_path)

        rar = open_rar(rarpath)


        # Build the destination path
        if config['keep_dirs']:
            path_suffix = source_path
        else:
            path_suffix = source_file

        to = config['to']
        if not to:
            to = os.path.dirname(rarpath)
            
        destination = os.path.join(to, path_suffix)
        dest_dir = os.path.dirname(destination)

        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        if not os.path.exists(destination):
            log.debug('Attempting to extract %s to %s' % (source_file, dest_dir))
            try:
                rar.extract(source_path, dest_dir)
                log.info('Extracted %s' % source_file )
            except Exception as e:
                log.error('Failed to extract file %s (%s)' % (source_file, e) )
        else:
            log.debug('File already exists')

    def on_task_output(self, task, config):
        """Extracts entries for the  contents of a RAR archive that match the provided pattern."""
        config = self.prepare_config(config)

        # Set the path of the unrar tool if it's not specified in PATH
        unrar_tool = config['unrar_tool']
        if unrar_tool != 'unrar':
            rarfile.UNRAR_TOOL = unrar_tool
            log.debug('Set RarFile.unrar_tool to: %s' % unrar_tool)

        for entry in task.accepted:
            if not 'rar_path' in entry:
                self.log.verbose('Cannot handle %s because it does not have the field rar_path.' % entry['title'])
                continue

            self.handle_entry(entry, config)
            


@event('plugin.register')
def register_plugin():
    plugin.register(RarList, 'rar_list', api_ver=2)
    plugin.register(RarVolumes, 'rar_volumes', api_ver=2)
    plugin.register(RarExtract, 'rar_extract', api_ver=2)

from __future__ import unicode_literals, division, absolute_import
import logging
import os
import rarfile
import re

from flexget import plugin
from flexget.entry import Entry
from flexget.event import event
from flexget.utils.template import render_from_entry, RenderError

log = logging.getLogger('rarfile')


class RarExtract(object):
    """
    Extracts files from RAR archives. By default this plugin will extract to the same directory as 
    the source archive, preserving directory structure from the archive.

    This plugin requires the unrar command line utility to extract compressed archives. If its 
    location is not specified in your PATH environment variable, you can specify its path using
    the unrar_tool config value.

    Example:

      rar_extract: yes

    Example:

      rar_extract:
        keep_dirs: no
        mask: *.mkv
        unrar_tool: '/unar/unrar'

    Example:

      rar_extract:
        keep_dirs: yes
        fail_entries: yes
        regexp: '.*s\d{1,2}e\d{1,2}.*.mkv'
    """

    schema = {
        'anyOf': [
            {'type': 'boolean'},
            {
                'type': 'object',
                'properties': {
                    'to': {'type': 'string'},
                    'keep_dirs': {'type': 'boolean'},
                    'mask': {'type': 'string'},
                    'regexp': {'type': 'string', 'format': 'regex'},
                    'fail_entries': {'type': 'boolean'},
                    'unrar_tool': {'type': 'string'},
                    'delete_rar': {'type': 'boolean'}
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
        config.setdefault('fail_entries', False)
        config.setdefault('unrar_tool', '')
        config.setdefault('delete_rar', False)

        # If mask was specified, turn it in to a regexp
        if 'mask' in config:
            config['regexp'] = translate(config['mask'])
        # If no mask or regexp specified, accept all files
        if 'regexp' not in config:
            config['regexp'] = '.'

        return config

    def handle_entry(self, entry, match, config):
        """Extract the file listed in entry"""

        rar_path = entry['location']
        rar_dir = os.path.dirname(rar_path)
        rar_file = os.path.basename(rar_path)

        
        try:
            rar = rarfile.RarFile(rarfile=rar_path)
        except rarfile.RarWarning as e:
            log.warn('Nonfatal error: %s (%s)' % (rar_path, e))
        except rarfile.NeedFirstVolume:
            log.error('Not the first volume: %s' % rar_path)
            return
        except rarfile.NotRarFile:
            log.error('Not a RAR file: %s' % rar_path)
            return
        except rarfile.RarFatalError as e:
            error = 'Failed to open RAR: %s (%s)' (rar_path, e)
            log.error(error)
            if config['fail_entries']:
                entry.fail(error)
            return

        to = config['to']
        if to:
            try:
                to = render_from_entry(to, entry)
            except RenderError as e:
                error = 'Could not render path: %s' % to
                log.error(error)

                if config['fail_entries']:
                    entry.fail(error)
                return
        else:
            to = rar_dir

        for info in rar.infolist():
            path = info.filename
            filename = os.path.basename(path)


            if not match(path):
                log.debug('File did not match regexp: %s' % path)
                continue

            log.debug('Found matching file: %s' %path)

            
            if config['keep_dirs']:
                path_suffix = path
            else:
                path_suffix = filename
            destination = os.path.join(to, path_suffix)
            dest_dir = os.path.dirname(destination)

            if not os.path.exists(dest_dir):
                log.debug('Creating path: %s' % dest_dir)
                os.makedirs(dest_dir)

            if not os.path.exists(destination):
                log.debug('Attempting to extract: %s to %s' % (rar_file, dest_dir))
                try:
                    rar.extract(path, dest_dir)
                    log.verbose('Extracted: %s' % path )
                except Exception as e:
                    error = 'Failed to extract file: %s (%s)' % (path, e)
                    log.error(error)
                    entry.fail(error)
                    return
            else:
                log.verbose('File already exists: %s' % dest_dir)

        if config['delete_rar']:
            volumes = rar.volumelist()
            rar.close()

            for volume in volumes:
                log.debug('Deleting volume: %s' % volume)
                os.remove(volume)

            log.verbose('Deleted RAR: %s' % rar_file)
        else:
            rar.close()

    def on_task_output(self, task, config):
        """Extracts entries for the  contents of a RAR archive that match the provided pattern."""
        if isinstance(config, bool) and not config:
            return

        config = self.prepare_config(config)

        match = re.compile(config['regexp'], re.IGNORECASE).match

        # Set the path of the unrar tool if it's not specified in PATH
        unrar_tool = config['unrar_tool']
        if unrar_tool:
            rarfile.UNRAR_TOOL = unrar_tool
            log.debug('Set RarFile.unrar_tool to: %s' % unrar_tool)

        for entry in task.accepted:
            self.handle_entry(entry, match, config)     


@event('plugin.register')
def register_plugin():
    plugin.register(RarExtract, 'rar_extract', api_ver=2)

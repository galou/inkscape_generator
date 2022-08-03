#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generator - a Inkscape extension to generate end-use files from a model

Initiator:  Aurélio A. Heckert (Bash version, up to Version 0.4)
Contributor: Gaël Ecorchard (Python version)

The MIT License (MIT)

Copyright (c) 2014 Gaël Ecorchard

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Release notes:
    - version 0.6.2, 2022-08: - Create the directory for output files, if
                                required.
                              - Handle special characters (e.g. '/') in
                                variables.
    - version 0.6.1, 2021-12: support for Python 3 added.
    - version 0.6, 2020-11: ported for Inkscape v1+.
    - version 0.5, 2014-11: complete rewrite in Python of the original Bash
                            extension
                 * added support for csv data with commas
                 * added support for csv data with xml special characters
                 * added support for layer visibility change based on variables
                 * temporarily removed jpg support because Inkscape cannot
                   convert to jpg from the command line.
                 * temporarily removed the gui functionalities provided by
                   zenity.
"""

from gettext import gettext as _
from io import StringIO
from xml.sax.saxutils import escape
import copy
import csv
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Dict, List
import xml.etree.ElementTree as et

import inkex
from inkex import errormsg

# Type hints.
CsvRow = List[str]
# One entry from the database as dictionnary
# {column_name: value_for_this_entry}.
Entry = Dict[str, str]

# Deactivate for now (2020-12) because rsvg-convert does not export images
# correctly.
_use_rsvg = False


class Generator(inkex.Effect):
    def __init__(self, *args, **kwargs):
        inkex.Effect.__init__(self, *args, **kwargs)
        self.arg_parser.add_argument('--tab')
        self.arg_parser.add_argument('--preview',
                                     type=str,
                                     dest='preview', default='false',
                                     help='Preview')
        self.arg_parser.add_argument('--extra-vars',
                                     type=str,
                                     dest='extra_vars', default='',
                                     help='Output format')
        self.arg_parser.add_argument('--format',
                                     type=str,
                                     dest='format', default='PDF',
                                     help='Output format')
        self.arg_parser.add_argument('--dpi',
                                     type=float,
                                     dest='dpi', default=96.0,
                                     help='DPI (resolution for png and jpg)')
        self.arg_parser.add_argument('-t', '--var-type',
                                     type=str,
                                     dest='var_type', default='name',
                                     help=('Replace variables by '
                                           'column number '
                                           '(number) or column name (name)'))
        self.arg_parser.add_argument('-d', '--data-file',
                                     type=str,
                                     dest='datafile', default='data.csv',
                                     help='The csv file')
        self.arg_parser.add_argument('-o', '--output-pattern',
                                     type=str,
                                     dest='output_pattern',
                                     default='%VAR_1.pdf',
                                     help='Output pattern')
        self.header = None
        self.data = None
        self.tmpdir = Path(tempfile.mkdtemp(prefix='ink-generator'))
        # svgouts is a dict {row_as_list: tmp_svg_output_file}.
        self.svgouts: Dict[Entry, Path] = {}

    def effect(self):
        """Do the work"""
        self.options.format = self.options.format.lower()
        self.read_csv()
        if self.options.var_type == 'name':
            self.create_svg_name()
        else:
            self.create_svg_number()
        self.export()
        if self.options.preview.lower() == 'true':
            self.show_preview()
        self.clean()

    def read_csv(self):
        """Read data from the csv file and store the rows into self.data."""
        with Path(self.options.datafile).expanduser().open() as data_file:
            try:
                reader = csv.reader(data_file)
            except IOError:
                msg = _('Cannot read "{}"'.format(self.options.datafile))
                errormsg(msg)
                raise Exception(msg)
            # Read the first row as header when using column names as keys.
            if self.options.var_type == 'name':
                try:
                    self.header = next(reader)
                except StopIteration:
                    msg = _('Data file "{}" contains no data'.format(
                        self.options.datafile))
                    errormsg(msg)
                    raise Exception(msg)
            self.data: List[CsvRow] = []
            for row in reader:
                self.data.append(row)

    def create_svg_number(self):
        """Create a header, read each line and fill self.svgouts"""
        self.header = [str(i) for i in range(len(self.data[0]))]
        self.create_svg_name()

    def create_svg_name(self):
        """Read each line in self.data and fill self.svgouts."""
        for line in self.data:
            d = self.get_line_as_dict(line)
            self.svgouts[tuple(line)] = self.create_svg(d)

    def create_svg(self, name_dict: Entry) -> Path:
        """Writes out a modified svg and return the file path."""
        s = StringIO()
        with Path(self.options.input_file).expanduser().open() as svg_file:
            for svg_line in svg_file.readlines():
                # Modify the line to handle extra replacements from the
                # plugin GUI.
                svg_line = self.expand_extra_vars(svg_line, name_dict)
                # Modify the line to handle variables in svg file
                svg_line = self.expand_vars(svg_line, name_dict)
                s.write(svg_line)
        # Modify the svg to include or exclude groups.
        root = et.fromstring(s.getvalue())
        s.close()
        self.filter_layers(root, name_dict)
        svgout = self.get_svgout()
        try:
            with svgout.open('w') as f:
                f.write(et.tostring(root,
                                    encoding='utf-8',
                                    xml_declaration=True).decode('utf-8'))
        except IOError:
            errormsg(_('Cannot open "{}" for writing'.format(svgout)))
        return svgout

    def get_svgout(self) -> Path:
        """Return the path to a temporary svg file."""
        return Path(tempfile.mktemp(dir=self.tmpdir, suffix='.svg'))

    def get_line_as_dict(self, line: CsvRow) -> Entry:
        """Return the current csv line as dict with csv headers as keys."""
        return dict(zip(self.header, line))

    @classmethod
    def sanitize_for_file(cls, name_dict: Entry, output_pattern: str) -> Entry:
        """Remove characters not allowed in file names.

        Remove characters from the values of `name_dict` that are not allowed
        in file names. Only variables mentioned in output_pattern will be
        touched.

        """
        blacklist = '/\\#$:!<>?, '

        def sanitize(s: str) -> str:
            return ''.join(['_' if (c in blacklist) else c for c in s])

        out_name_dict = copy.copy(name_dict)
        # Retrieve mentioned variables.
        matches = re.findall('%VAR_([^%]*)%', output_pattern)
        for match in matches:
            try:
                out_name_dict[match] = sanitize(out_name_dict[match])
            except KeyError:
                errormsg(_('Column "' + match + '" not in the csv file'))
                continue
        return out_name_dict

    def get_output(self, name_dict: Entry) -> Path:
        """Return the path to the output file for a csv entry."""
        sane_name_dict = self.sanitize_for_file(name_dict,
                self.options.output_pattern)
        row = self.expand_vars(self.options.output_pattern, sane_name_dict)
        # Replace characters not allowed in filenames.
        import sys #DEBUG
        print(f'Path: {Path(row).expanduser()}', file=sys.stderr) #DEBUG
        return Path(row).expanduser()

    def expand_extra_vars(self, line: str, name_dict: Entry):
        """Replace extra replacement values with the content from a csv entry."""
        if not self.options.extra_vars:
            return line
        replacement_strings = self.options.extra_vars.split('|')
        for t in replacement_strings:
            try:
                old_txt, column = t.split('=>')
            except ValueError:
                msg = _('Unrecognized replacement string {}'.format(t))
                errormsg(msg)
                raise Exception(msg)
            if line.find(old_txt) < 0:
                # Nothing to be replaced.
                continue
            try:
                new_txt = escape(name_dict[column])
            except KeyError:
                if self.options.var_type == 'name':
                    msg = _('Wrong column name "{}"'.format(column))
                    errormsg(msg)
                    raise Exception(msg)
                else:
                    msg = _('Wrong column number ({})'.format(column))
                    errormsg(msg)
                    raise Exception(msg)
            line = line.replace(old_txt, new_txt)
        return line

    def expand_vars(self, line, name_dict: Entry):
        """Replace %VAR_???% with the content from a csv entry."""
        if '%' not in line:
            return line
        for k, v in name_dict.items():
            line = line.replace('%VAR_' + k + '%', escape(v))
        return line

    def filter_layers(self, root: et.Element, name_dict: Entry):
        """Return the xml root with filtered layers"""
        for g in root.findall(".//svg:g", namespaces=inkex.NSS):
            attr = inkex.addNS('label', ns='inkscape')
            if attr not in g.attrib:
                # Not a layer, skip.
                continue
            label = g.attrib[attr]
            if '%' not in label:
                # Nothing to be done, skip.
                continue

            # Treat %IF_???% layers
            match = re.match('.*%IF_([^%]*)%', label)
            if match is not None:
                lookup = match.groups()[0]
                try:
                    var = name_dict[lookup]
                except KeyError:
                    errormsg(_('Column "' + lookup + '" not in the csv file'))
                    continue
                if var and (var.lower() not in ('0', 'false', 'no')):
                    # Set group visibility to true.
                    if 'style' in g.attrib:
                        del g.attrib['style']
                    # Include the group.
                    continue
                else:
                    # Remove the group's content.
                    g.clear()

            # Treat %UNLESS_???% layers
            match = re.match('.*%UNLESS_([^%]*)%', label)
            if match is not None:
                lookup = match.groups()[0]
                try:
                    var = name_dict[lookup]
                except KeyError:
                    errormsg(_('Column "' + lookup + '" not in the csv file'))
                    continue
                if not(var) or (var.lower() in ('0', 'false', 'no')):
                    # Set group visibility to true.
                    if 'style' in g.attrib:
                        del g.attrib['style']
                    # Include the group.
                    continue
                else:
                    # Remove the group's content.
                    g.clear()

    def export(self):
        """Writes out all output files."""
        def get_export_cmd(svgfile: str, fmt: str, dpi: float, outfile: Path):
            if _use_rsvg and (os.name == 'posix'):
                # A DPI of 72 must be set to convert from files generated with
                # Inkscape v1+ to get the correct page size.
                ret = os.system('rsvg-convert --version 1>/dev/null')
                if ret == 0:
                    return ('rsvg-convert' +
                            ' --dpi-x=' + str(dpi * 72.0 / 96.0) +
                            ' --dpi-y=' + str(dpi * 72.0 / 96.0) +
                            ' --format=' + fmt +
                            ' --output="' + str(outfile) + '"' +
                            ' "' + svgfile + '"')
            else:
                # Slowlier but more portable.
                return ('inkscape '
                        + '--export-dpi=' + str(dpi) + ' '
                        + '--export-type=' + fmt + ' '
                        + '--export-filename="' + str(outfile) + '" '
                        '"' + svgfile + '"')

        for line, svgfile in self.svgouts.items():
            d = self.get_line_as_dict(line)
            outfile = self.get_output(d)
            if not outfile.parent.exists():
                outfile.parent.mkdir(parents=True, exist_ok=True)
            if self.options.format == 'jpg':
                # TODO: output a jpg file
                self.options.format = 'png'
                outfile = Path(str(outfile).replace('jpg', 'png'))
            if self.options.format == 'svg':
                try:
                    shutil.move(svgfile, outfile)
                except OSError:
                    errormsg(_('Cannot create "' + outfile + '"'))
            else:
                cmd = get_export_cmd(svgfile,
                                     self.options.format,
                                     self.options.dpi, outfile)
                os.system(cmd)

    def show_preview(self):
        systems = {
            'nt': os.startfile if hasattr(os, 'startfile') else None,
            'posix': lambda path: os.system(f'gio open "{path}"'),
            'os2': lambda path: os.system(f'open "{path}"'),
        }
        try:
            line = self.svgouts.keys()[0]
            d = self.get_line_as_dict(line)
            outfile = self.get_output(d)
            systems[os.name](outfile)
        except:
            errormsg(_('Error open preview file'))

    def clean(self):
        """Delete temporary svg files and directory."""
        if self.options.format != 'svg':
            for svgfile in self.svgouts.values():
                os.remove(svgfile)
        os.rmdir(self.tmpdir)


if __name__ == '__main__':
    e = Generator()
    e.run()

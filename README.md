inkscape_generator
==================

Generate output files from a template SVG file.

Dependencies
------------

Only Inkscape is needed because it comes with all needed dependencies.

Installation
------------

Copy generator.py and generator.inx to the extensions directory in you Inkscape profile. On Linux, it is $HOME/.config/inkscape/extensions.
Possibly, on Linux, make generator.py executable.

Use
---

The entry point is in menu "Extensions/Export/Generator...".

The idea and implementation inspiration is taken from Aurélio A. Heckert. The behavior was detailled on his web site: ht<span>tp</span>://wiki.colivre.net/Aurium/InkscapeGenerator but the site is down. The CSV file must be comma-separated and the text fields must be double-quoted.

How vars are replaced?

There are three places were replacement occur.

1. Replacement in the drawing

The replacer will walk through each data column, line-by-line, and will try to replace the `%VAR_#%` in the current drawing by the column value.
If you select "column position", # is the column number.
If you select "column name", # is the column name, defined in the first line.

2. Replacement in "Configuration" tab, "extra textual values to be replaced"

You can replace other text patterns, like element values with this configuration. On the second field, add all extra text to be replaced in a line separated by "|", pointing to the replacer column with "=>" (name or number depending on the configuration choice). Do not use spaces if that is not part of the blocks!
For example, we can make the red and green colors as variables to be replaced by some other colors from the database at the columns `"secure color"` and `"sector color"`:
`#ff0000=>secure_color|#00ff00=>sector_color`
All pure red and pure green elements will have new colors for each data line.

3. Inclusion or deletion of special layers

Layers can be given two special names `%IF_#%` or `%UNLESS_#%` (cf. above for the signification of #). A layer with name `%IF_#%` will be included in the output document if the entry corresponding to column # is not empty and if it is neither "0", nor "false", nor "no". A layer with name `%UNLESS_#%` will be included if the entry is empty or if it is "0", "false", or "no". In both cases, the layer visibility will be set to true. Extra text after the second "%" in the layer name will be ignored, so that you can use the same condition for two layers with different labels, what is compulsory.

If you are not sure about the usable variables, run it on preview mode and the replaceable texts of the first item in the CSV file will be shown to you.

Alternatives
------------

- [NextGenerator](https://inkscape.org/gallery/item/16745/)/ Does not support replacement by column number. Does not support "extra textual values to be replaced". Does not support inclusion or deletion of special layers. It is also a rewrite of the generator from Aurélio A. Heckert.
- [ink-generator-python](https://github.com/butesa/ink-generator-python). It is a also a rewrite of the generator from Aurélio A. Heckert. The behavior is probably similar to NextGenerator.

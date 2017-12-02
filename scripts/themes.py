import re
import os
import json
from glob import glob

COPYRIGHT = """
#------------------------------------------------------------------------------
# Copyright (c) 2017, Nucleic Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#------------------------------------------------------------------------------
""".strip()


def generate_themes(path):
    """ Generate the Scintilla code for the *.css themes within the given path.
    
    """
    themes = []
    for f in sorted(glob("{}/*.css".format(path))):
        try:
            themes.append(scintilla_theme_from_pygment(f))
        except KeyError as e:
            print("Error generating {}: {}".format(f, e))

    names = []
    if not os.path.exists('themes'):
        os.makedirs('themes')

    #: Create a file with each
    for t in themes:
        name = t['settings']['name']
        names.append(name)
        with open('themes/{}.py'.format(name), 'w') as f:
            f.write(COPYRIGHT+"\n")
            f.write("\n{}_THEME = {}".format(name.upper(),
                                             json.dumps(t, indent=4)))
            f.write("\n\n")
            f.write("{}_THEME['enaml'] = {}_THEME['python']\n".format(
                    name.upper(), name.upper()))

    #: Add idle
    names.append('idle')

    #: Generate the themes api
    names.sort()
    with open('themes/__init__.py', 'w') as f:
        f.write(COPYRIGHT+"\n")
        for n in names:
            f.write("from .{} import {}_THEME\n".format(n, n.upper()))
        f.write("\n\n")
        f.write("THEMES = {\n")
        for n in names:
            f.write("    '{}': {}_THEME,\n".format(n, n.upper()))
        f.write("}\n")
    return themes


def scintilla_theme_from_pygment(path):
    """ Create a scintialla theme from the pygment theme
    
    """
    data = parse_pygments_css_theme(path)
    fg = data["General"]["styles"].get('color', '#000000')
    bg = data["General"]["styles"].get('paper', '#FFFFFF')

    if "Generic" in data:
        fg = data["Generic"]["styles"]['color']

    #: Decorator style
    decorator = data.get("Name.Decorator", data['General'])

    #: Operator style
    operator = data.get("Operator", data['General'])

    return {
        "settings": {
            "caret": fg,
            "color": fg,
            "paper": bg,
            "name": os.path.splitext(os.path.split(path)[-1])[0],
        },
        "python": {
            "class_name": data["Name.Class"]["styles"],
            "comment": data["Comment"]["styles"],
            "comment_block": data["Comment.Multiline"]["styles"],
            "decorator": decorator["styles"],
            "double_quoted_string": data["Literal.String.Double"]["styles"],
            "function_method_name": data["Name.Function"]["styles"],
            "highlighted_identifier": data["HighlightedLine"]["styles"],
            "keyword": data["Keyword"]["styles"],
            "operator": operator["styles"],
            "unclosed_string": data["Error"]["styles"],
            "single_quoted_string": data["Literal.String.Single"]["styles"],
            "triple_double_quoted_string": data["Literal.String.Double"]["styles"],
            "triple_single_quoted_string": data["Literal.String.Single"]["styles"],
        }
    }


def parse_pygments_css_theme(path):
    """ Parse a css theme from pygments.
    
    """
    with open(path) as f:
        data = [l for l in f.read().split("\n") if l]
    #: Extract
    matches = [(l, re.search(r'\.highlight (.*) {(.+)} /\* (.+) \*/', l))
               for l in data]

    #: Pull the groups
    groups = [(l, m.groups()) for l, m in matches if m]

    #: Add any without comments
    bg = [l for l in data if l.startswith(".highlight  {")][0]
    groups.append((bg, ('', bg.split("{")[1].split("}")[0].strip(),
                        'General')))
    hll = [l for l in data if l.startswith(".highlight .hll {")][0]
    groups.append((hll, ('', hll.split("{")[1].split("}")[0].strip() ,
                         'HighlightedLine')))

    def parse_styles(source):
        styles = {}
        for style in source.split(";"):
            if not style:
                continue

            #: Strip
            k, v = [it.strip() for it in style.split(":")]

            #: Replace it
            if k in ['background', 'background-color']:
                k = 'paper'

            styles[k] = v
        return styles

    theme = {g[-1]: {
        'name': g[0],
        'source': l,
        'styles': parse_styles(g[1]),
    } for l, g in groups}
    return theme

if __name__ == '__main__':
    generate_themes('.')
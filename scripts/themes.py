import re
import os
import json
from glob import glob


def generate_themes(path):
    """ Generate the code for the *.css themes within the given path.
    """
    themes = []
    for f in sorted(glob("{}/*.css".format(path))):
        try:
            themes.append(scintilla_theme_from_pygment(f))
        except KeyError as e:
            print("Error generating {}: {}".format(f, e))

    names = []
    for t in themes:
        name = t['settings']['name']
        names.append(name)
        print("\n{}_THEME = {}".format(name.upper(), json.dumps(t, indent=4)))
        print("{}_THEME['enaml'] = {}_THEME['python']".format(
            name.upper(), name.upper()))

    print("THEMES = {")
    for n in sorted(names):
        print("    '{}': {}_THEME,".format(n, n.upper()))
    print("}")
    return themes



def scintilla_theme_from_pygment(path):
    """ Create a scintialla theme from the pygment theme
    
    """
    data = parse_pygments_css_theme(path)
    fg = data["General"]["styles"].get('color', '#000000')
    bg = data["General"]["styles"].get('background', '#FFFFFF')

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
            "class_name": {
                "color": data["Name.Class"]["styles"].get('color', fg),
            },
            "comment": {
                "color": data["Comment"]["styles"].get('color', fg),
            },
            "comment_block": {
                "color": data["Comment.Multiline"]["styles"].get('color', fg),
            },
            "decorator": {
                "color": decorator["styles"].get('color', fg)
            },
            "double_quoted_string": {
                "color": data["Literal.String.Double"]["styles"].get('color',
                                                                     fg)
            },
            "function_method_name": {
                "color": data["Name.Function"]["styles"].get('color', fg)
            },
            "highlighted_identifier": {
                "paper": data["HighlightedLine"]["styles"]['background-color']
            },
            "keyword": {
                "color": data["Keyword"]["styles"].get('color', fg)
            },
            "operator": {
                "color": operator["styles"].get('color', fg)
            },
            "unclosed_string": {
                "color": data["Error"]["styles"].get('color', fg),
                "paper": data["Error"]["styles"].get('background-color', bg),
            },
            "single_quoted_string": {
                "color": data["Literal.String.Single"]["styles"].get('color',
                                                                     fg)
            },
            "triple_double_quoted_string": {
                "color": data["Literal.String.Double"]["styles"].get('color',
                                                                     fg)
            },
            "triple_single_quoted_string": {
                "color": data["Literal.String.Single"]["styles"].get('color',
                                                                     fg)
            }
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

    theme = {g[-1]: {
        'name': g[0],
        'source': l,
        'styles': {
            k.split(":")[0].strip(): k.split(":")[1].strip()
            for k in g[1].split(";") if k
        }
    } for l, g in groups}
    return theme

if __name__ == '__main__':
    generate_themes('.')
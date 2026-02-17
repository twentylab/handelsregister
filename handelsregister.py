#!/usr/bin/env python3
"""
bundesAPI/handelsregister is the command-line interface for the shared register of companies portal for the German federal states.
You can query, download, automate and much more, without using a web browser.
"""

import argparse
import tempfile
import mechanize
import re
import pathlib
import sys
from bs4 import BeautifulSoup
import urllib.parse

# Dictionaries to map arguments to values
schlagwortOptionen = {
    "all": 1,
    "min": 2,
    "exact": 3
}

# German states (Bundesländer) mapping
bundeslaender = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BR": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen"
}

# Mapping of district names (German and English) to bundesland codes
bundesland_name_to_code = {
    # German names
    "baden-württemberg": "BW",
    "baden-wuerttemberg": "BW",
    "baden württemberg": "BW",
    "baden wuerttemberg": "BW",
    "bayern": "BY",
    "bavaria": "BY",
    "berlin": "BE",
    "brandenburg": "BR",
    "bremen": "HB",
    "hamburg": "HH",
    "hessen": "HE",
    "hesse": "HE",
    "mecklenburg-vorpommern": "MV",
    "mecklenburg vorpommern": "MV",
    "mecklenburg-western pomerania": "MV",
    "mecklenburg western pomerania": "MV",
    "niedersachsen": "NI",
    "lower saxony": "NI",
    "nordrhein-westfalen": "NW",
    "nordrhein westfalen": "NW",
    "north rhine-westphalia": "NW",
    "north rhine westphalia": "NW",
    "rheinland-pfalz": "RP",
    "rheinland pfalz": "RP",
    "rhineland-palatinate": "RP",
    "rhineland palatinate": "RP",
    "saarland": "SL",
    "sachsen": "SN",
    "saxony": "SN",
    "sachsen-anhalt": "ST",
    "sachsen anhalt": "ST",
    "saxony-anhalt": "ST",
    "saxony anhalt": "ST",
    "schleswig-holstein": "SH",
    "schleswig holstein": "SH",
    "thüringen": "TH",
    "thueringen": "TH",
    "thuringia": "TH"
}

def get_bundesland_code(name):
    """
    Get bundesland code from district name (German or English).
    Returns the code or None if not found.
    """
    if not name:
        return None
    
    # Normalize the input
    normalized = name.strip().lower()
    
    # Check if it's already a code
    if normalized.upper() in bundeslaender:
        return normalized.upper()
    
    # Look up in the name mapping
    return bundesland_name_to_code.get(normalized)

class HandelsRegister:
    def __init__(self, args):
        self.args = args
        self.browser = mechanize.Browser()

        self.browser.set_debug_http(args.debug)
        self.browser.set_debug_responses(args.debug)
        # self.browser.set_debug_redirects(True)

        self.browser.set_handle_robots(False)
        self.browser.set_handle_equiv(True)
        self.browser.set_handle_gzip(True)
        self.browser.set_handle_refresh(False)
        self.browser.set_handle_redirect(True)
        self.browser.set_handle_referer(True)

        self.browser.addheaders = [
            (
                "User-Agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15",
            ),
            (   "Accept-Language", "en-GB,en;q=0.9"   ),
            (   "Accept-Encoding", "gzip, deflate, br"    ),
            (
                "Accept",
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            ),
            (   "Connection", "keep-alive"    ),
        ]
        
        self.cachedir = pathlib.Path(tempfile.gettempdir()) / "handelsregister_cache"
        self.cachedir.mkdir(parents=True, exist_ok=True)

    def open_startpage(self):
        self.browser.open("https://www.handelsregister.de", timeout=10)

    def companyname2cachename(self, companyname):
        return self.cachedir / companyname

    def search_company(self):
        cachename = self.companyname2cachename(self.args.schlagwoerter)
        if self.args.force==False and cachename.exists():
            with open(cachename, "r") as f:
                html = f.read()
                if not self.args.json:
                    print("return cached content for %s" % self.args.schlagwoerter)
        else:
            # TODO implement token bucket to abide by rate limit
            # Use an atomic counter: https://gist.github.com/benhoyt/8c8a8d62debe8e5aa5340373f9c509c7
            self.browser.select_form(name="naviForm")
            self.browser.form.new_control('hidden', 'naviForm:erweiterteSucheLink', {'value': 'naviForm:erweiterteSucheLink'})
            self.browser.form.new_control('hidden', 'target', {'value': 'erweiterteSucheLink'})
            response_search = self.browser.submit()

            if self.args.debug == True:
                print(self.browser.title())

            self.browser.select_form(name="form")

            self.browser["form:schlagwoerter"] = self.args.schlagwoerter
            so_id = schlagwortOptionen.get(self.args.schlagwortOptionen)

            self.browser["form:schlagwortOptionen"] = [str(so_id)]
            
            # Set bundesland filters if provided
            if hasattr(self.args, 'bundesland') and self.args.bundesland:
                bundesland_codes = self.args.bundesland if isinstance(self.args.bundesland, list) else [self.args.bundesland]
                for code in bundesland_codes:
                    code_upper = code.upper()
                    if code_upper in bundeslaender:
                        form_field = f"form:bundesland{code_upper}"
                        try:
                            self.browser[form_field] = ["on"]
                        except Exception as e:
                            if self.args.debug:
                                print(f"Warning: Could not set bundesland {code_upper}: {e}")

            response_result = self.browser.submit()

            if self.args.debug == True:
                print(self.browser.title())

            html = response_result.read().decode("utf-8")
            with open(cachename, "w") as f:
                f.write(html)

            # TODO catch the situation if there's more than one company?
            # TODO get all documents attached to the exact company
            # TODO parse useful information out of the PDFs
        return get_companies_in_searchresults(html)



def parse_result(result):
    cells = []
    for cellnum, cell in enumerate(result.find_all('td')):
        cells.append(cell.text.strip())
    d = {}
    d['court'] = cells[1]
    
    # Extract register number: HRB, HRA, VR, GnR followed by numbers (e.g. HRB 12345, VR 6789)
    # Also capture suffix letter if present (e.g. HRB 12345 B), but avoid matching start of words (e.g. " Formerly")
    reg_match = re.search(r'(HRA|HRB|GnR|VR|PR)\s*\d+(\s+[A-Z])?(?!\w)', d['court'])
    d['register_num'] = reg_match.group(0) if reg_match else None

    d['name'] = cells[2]
    d['state'] = cells[3]
    d['status'] = cells[4].strip()  # Original value for backward compatibility
    d['statusCurrent'] = cells[4].strip().upper().replace(' ', '_')  # Transformed value

    # Ensure consistent register number suffixes (e.g. ' B' for Berlin HRB, ' HB' for Bremen) which might be implicit
    if d['register_num']:
        suffix_map = {
            'Berlin': {'HRB': ' B'},
            'Bremen': {'HRA': ' HB', 'HRB': ' HB', 'GnR': ' HB', 'VR': ' HB', 'PR': ' HB'}
        }
        reg_type = d['register_num'].split()[0]
        suffix = suffix_map.get(d['state'], {}).get(reg_type)
        if suffix and not d['register_num'].endswith(suffix):
            d['register_num'] += suffix
    d['documents'] = cells[5] # todo: get the document links
    d['history'] = []
    hist_start = 8

    for i in range(hist_start, len(cells), 3):
        if i + 1 >= len(cells):
            break
        if "Branches" in cells[i] or "Niederlassungen" in cells[i]:
            break
        d['history'].append((cells[i], cells[i+1])) # (name, location)

    return d

def pr_company_info(c):
    for tag in ('name', 'court', 'register_num', 'district', 'state', 'statusCurrent'):
        print('%s: %s' % (tag, c.get(tag, '-')))
    print('history:')
    for name, loc in c.get('history'):
        print(name, loc)

def get_companies_in_searchresults(html):
    soup = BeautifulSoup(html, 'html.parser')
    grid = soup.find('table', role='grid')
  
    results = []
    for result in grid.find_all('tr'):
        a = result.get('data-ri')
        if a is not None:
            index = int(a)

            d = parse_result(result)
            results.append(d)
    return results

def parse_args():
    parser = argparse.ArgumentParser(description='A handelsregister CLI')
    parser.add_argument(
                          "-d",
                          "--debug",
                          help="Enable debug mode and activate logging",
                          action="store_true"
                        )
    parser.add_argument(
                          "-f",
                          "--force",
                          help="Force a fresh pull and skip the cache",
                          action="store_true"
                        )
    parser.add_argument(
                          "-s",
                          "--schlagwoerter",
                          help="Search for the provided keywords",
                          required=True,
                          default="Gasag AG" # TODO replace default with a generic search term
                        )
    parser.add_argument(
                          "-so",
                          "--schlagwortOptionen",
                          help="Keyword options: all=contain all keywords; min=contain at least one keyword; exact=contain the exact company name.",
                          choices=["all", "min", "exact"],
                          default="all"
                        )
    parser.add_argument(
                          "-j",
                          "--json",
                          help="Return response as JSON",
                          action="store_true"
                        )
    parser.add_argument(
                          "-b",
                          "--bundesland",
                          help="Filter by German state(s). Use state codes: BW, BY, BE, BR, HB, HH, HE, MV, NI, NW, RP, SL, SN, ST, SH, TH. Can be specified multiple times.",
                          action="append",
                          choices=list(bundeslaender.keys())
                        )
    args = parser.parse_args()


    # Enable debugging if wanted
    if args.debug == True:
        import logging
        logger = logging.getLogger("mechanize")
        logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.setLevel(logging.DEBUG)

    return args

if __name__ == "__main__":
    import json
    args = parse_args()
    h = HandelsRegister(args)
    h.open_startpage()
    companies = h.search_company()
    if companies is not None:
        if args.json:
            print(json.dumps(companies))
        else:
            for c in companies:
                pr_company_info(c)

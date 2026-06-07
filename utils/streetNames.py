import argparse
import re
from html.parser import HTMLParser
from pathlib import Path
import pandas as pd

class HtmlToMarkdownConverter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_p = False
        self.in_ignored_p = False
        self.p_content = []  # List of tuples: ('bold', 'text') or ('text', 'text')
        self.current_text = ""
        self.is_bold = False
        
    def handle_starttag(self, tag, attrs):
        if tag == 'p':
            self.in_p = True
            self.in_ignored_p = False
            self.p_content = []
            self.current_text = ""
            self.is_bold = False
            
        elif self.in_p:
            if tag == 'b':
                # If we have pending text before this bold tag, save it as normal
                if self.current_text.strip():
                    self.p_content.append(('text', self.current_text))
                self.current_text = ""
                self.is_bold = True
                
    def handle_endtag(self, tag):
        if tag == 'b' and self.in_p:
            # Close bold tag
            if self.current_text.strip():
                self.p_content.append(('bold', self.current_text))
                # print(f"Added bold text: '{self.current_text.strip()}'")
            self.current_text = ""
            self.is_bold = False
            
        elif tag == 'p' and self.in_p:
            # Flush any remaining text before closing paragraph
            if self.current_text.strip():
                tag_type = 'bold' if self.is_bold else 'text'
                self.p_content.append((tag_type, self.current_text))
                # print(f"Added text at end of paragraph: '{self.current_text.strip()[:20]}' (bold={self.is_bold})")
                self.current_text = ""
            self.in_p = False
            self._process_current_paragraph()

    def handle_data(self, data):
        if self.in_p:
            # Check for ignore conditions on the very first chunk of data in the paragraph
            if not self.in_ignored_p and self.current_text == "" and len(self.p_content) == 0:
                # Decode common entities for checking logic
                temp_text = data.replace('&#160;', ' ').replace('&nbsp;', ' ')
                
                # Condition 1a: Starts with "Liegensch" (case insensitive check usually, but prompt says specific string)
                if temp_text.strip().startswith('Liegensch'):
                    self.in_ignored_p = True
                    return

                # Condition 1b: Starts with "Straßennamen in Karlsruhe" (case insensitive check usually, but prompt says specific string)
                if temp_text.strip().startswith('Straßennamen in'):
                    self.in_ignored_p = True
                    return

                # Condition 2: Single character (A-Z) followed by optional space/entity
                # Regex: Start, one alpha char, end or space
                cleaned = re.sub(r'[\s&\#]+', '', temp_text.strip()) # Remove spaces/entities temporarily to check length
                if len(cleaned) == 1 and cleaned.isalpha():
                     # Verify it was just the char and maybe spaces/entities in original
                     if re.match(r'^[a-zA-Z]\s*(?:&nbsp;|&#160;|\s)*$', temp_text.strip(), re.IGNORECASE):
                         self.in_ignored_p = True
                         return

            self.current_text += data

def extract_infos(content,json_path, txt_path):
    lines = content.split("## ")
    print(f"Extracting info from {len(lines)} lines")
    items = [(l.split("\n")[0],l.split("\n")[1]) if "\n" in l else (l,"") for l in lines]
    # now have tuples of (name, rest) where name is the first line after ## and rest is the rest of the text in that section. We want to extract the year from the name if it exists, and also clean up the name by removing any trailing year and any ", vor", ", nach", or ", um" parts.

    df = pd.DataFrame(items,columns=["text","description"])
    # find the date part from the headings and split it off into a separate column. The date part can be either at the end of the name (e.g. "Amalienstraße 1907") or at the beginning (e.g. "1907 Amalienstraße"). We also want to remove any ", vor", ", nach", or ", um" parts from the name, as they are not part of the actual name but rather indicate the time period of the naming.
    
    # most lines have a trailing year, but some have aleading year and some don't have a year at all. We want to split the year off into a separate column, but we can't just split on the last space because some names have multiple words. So we need to check if the last part is a number, and if so, split it off. If not, then we just keep the whole thing as the name and set the year to -1.
    def getYr(x):
        parts = x.strip().split(" ")
        first = parts[0]
        last = parts[-1]
        if last.isdigit():
            return int(last)
        elif first.isdigit():
            return int(first)
        else:
            return -1
    def getTxt(x):
        parts = x.strip().split(" ")
        last = parts[-1]
        first = parts[0]
        if last.isdigit():
            txt = " ".join(parts[:-1])
            if ", vor" in txt:
                return txt.split(", vor")[0].strip()
            elif ", nach" in txt:
                return txt.split(", nach")[0].strip()
            elif ", um" in txt:
                return txt.split(", um")[0].strip()
            if " vor" in txt:
                return txt.split(" vor")[0].strip()
            elif " nach" in txt:
                return txt.split(" nach")[0].strip()
            elif " um" in txt:
                return txt.split(" um")[0].strip()
            else:
                return txt
        elif "jahr" in last.lower(): # like 18.Jahrhundert of 17.jahrhdt
            txt = " ".join(parts[:-2]).strip()
            return txt
        elif first.isdigit():
            return " ".join(parts[1:])
        else:
            return x.strip()

    df["year"] = df.text.apply(getYr)
    df["name"] = df.text.apply(getTxt)
    df = df.drop(df[df.name == ""].index) # drop empty names
    df.to_json(json_path,orient="records",indent=2)
    df.name.to_csv(txt_path,index=False,header=False)
    

def convert_file(input_path_str):
    input_path = Path(input_path_str)
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    output_path = input_path.with_suffix('.md')

    with open(input_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # We need to capture the output internally instead of printing directly to file write later
    # Let's adjust the parser to collect lines
    class CollectingParser(HtmlToMarkdownConverter):
        def __init__(self):
            super().__init__()
            self.output_lines = []
        
        def _process_current_paragraph(self):
            if self.in_ignored_p:
                return
            # Parent logic
            if self.current_text.strip():
                tag_type = 'bold' if self.is_bold else 'text'
                self.p_content.append((tag_type, self.current_text))

            if not self.p_content:
                return

            parts = []
            for tag_type, text in self.p_content:
                clean_text = text.replace('&#160;', ' ').replace('&nbsp;', ' ')
                clean_text = ' '.join(clean_text.split())
                if not clean_text:
                    continue
                if tag_type == 'bold':
                    # parts.append(f"## {clean_text}")
                    self.output_lines.append(f"## {clean_text}")
                else:
                    parts.append(clean_text)
            
            if parts:
                self.output_lines.append(" ".join(parts))

    parser = CollectingParser()
    parser.feed(html_content)

    for i, line in enumerate(parser.output_lines):
        if line.strip().endswith("-"):
            parser.output_lines[i] = line[:-1].strip() + parser.output_lines[i+1]
            parser.output_lines[i+1] = ""
        if line.strip().endswith(";"):
            parser.output_lines[i] = line[:-1].strip()

    content = "\n".join([l for l in parser.output_lines if len(l) > 0])
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Converted '{input_path}' to '{output_path}' ({len(parser.output_lines)} lines)")

    extract_infos(content,output_path.with_name(output_path.stem + "_info.json"),output_path.with_name(output_path.stem + "_info.txt"))

def main():
    # pdftohtml -s  -i ../strassen-ka-orig.pdf
    parser = argparse.ArgumentParser(description='Convert HTML street names to Markdown')
    parser.add_argument("-i", "--input_file", help='Path to the input HTML file')
    
    args = parser.parse_args()
    
    try:
        convert_file(args.input_file)
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
    
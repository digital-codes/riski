""" Read mandate information from karlsruhe website and return a pandas dataframe """
import pandas as pd 
import bs4 as bs4
import requests

baseUrl = "https://sitzungskalender.karlsruhe.de/db/ratsinformation/mandate"
personBase = "https://sitzungskalender.karlsruhe.de/db/ratsinformation/"

# baseurl has a div with class=container and a h2 heading "Mandatsträger. inside a number of divs with class=row. 
# we need those rows. inside rows are one or more divs with class=col--<something>. check only for the leading col.
# each col has like:
#        <a href="people-449" class="text-link">Mentrup, Dr. Frank
#             (SPD, Oberbürgermeister) </a><br>
# the href must be resolved to point to personBase + href. the text inside the a tag is the name and 
# additonal information in brackets, with a comma separated list of attributes. 
# we expect either 2 attributes in which case the first is the party and the second is the role, 
# or 1 attribute in which case it is the role.
# we need to extract all attributes and return a pandas dataframe with columns: name, role, party (or none), person link


def getMandates():
    """
    Fetch mandate information from karlsruhe website and return a pandas dataframe.
    
    Returns:
        pd.DataFrame: DataFrame with columns: name, role, party, person_link
    """
    response = requests.get(baseUrl)
    response.raise_for_status()
    
    #print(f"Fetched {response.content} bytes from {baseUrl}")
    
    soup = bs4.BeautifulSoup(response.content, 'html.parser')
    
    # Find all rows which have a div with classes text-inline and at least one more starting with col
    rows = soup.find_all('div', class_='row')
    print(f"Found {len(rows)} rows in the page.")
    
    mandates = []
    
    expected = 0
    extracted = 0
    
    for row in rows:
        # Find all col divs with class text-inline and class starting with col-
        cols = row.find_all('div', class_=lambda x: x and 'text-inline' in x and any(c.startswith('col-') for c in x.split()))
        if not cols:
            continue

        #print(f"Processing {len(cols)} cols in row")
        expected += len(cols)
        for col in cols:
            # Find the link
            link = col.find('a', class_='text-link')
            if not link:
                print("No link found in col, skipping")
                continue
            
            href = link.get('href', '')
            person_link = personBase + href if href else ''
            
            # Extract name and attributes from link text
            text = link.get_text()
            
            # Split by parentheses to separate name from attributes
            if '(' in text and ')' in text:
                name = text[:text.index('(')].strip()
                attributes_str = text[text.index('(') + 1:text.index(')')].strip()
                attributes = [attr.strip() for attr in attributes_str.split(',')]
            else:
                name = text.strip()
                attributes = []
            
            # Parse attributes
            party = None
            role = None
            
            if len(attributes) == 2:
                party = attributes[0]
                role = attributes[1]
            elif len(attributes) == 1:
                role = attributes[0]
       
            #print(f"Extracted mandate: name={name}, role={role}, party={party}, person_link={person_link}")     
            mandates.append({
                'name': name,
                'role': role,
                'party': party,
                'person_link': person_link
            })
            extracted += 1
    print(f"Expected {expected} mandates, extracted {extracted}")
    df = pd.DataFrame(mandates)
    return df

if __name__ == "__main__":
    df = getMandates()
    print(len(df))
    df.to_json('mandates.json', orient='records', lines=True, indent=4)
    gr = df[df.party.notnull() & ((df.role.str.lower().str.contains("stadtr", case=False, na=False)) | (df.role.str.lower().str.contains("bürgermeister", case=False, na=False)))]
    # gr = df[((df.role.str.lower().str.contains("stadtr", case=False, na=False)) | (df.role.str.lower().str.contains("bürgermeister", case=False, na=False)))]
    gr = gr.drop_duplicates(subset=['name'], keep='first')
    print("Stadträte:", len(gr))
    gr = gr.sort_values('party')
    gr.to_json('mandates_with_party.json', orient='records', lines=True, indent=4)
    
    # Export by party
    for party in gr['party'].unique():
        party_df = gr[gr['party'] == party]
        import re
        clean_party = re.sub(r'[^a-z0-9]', '_', party.lower())
        filename = f"mandates_{clean_party}.json"
        party_df.to_json(filename, orient='records', lines=True, indent=4)
        print(f"Exported {len(party_df)} mandates for party '{party}' to {filename}")
    
    


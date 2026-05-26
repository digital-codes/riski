import pandas as pd
import matplotlib.pyplot as plt
import os
import json
import requests

srcDir = "./ko_extracted"
dstDir = "./ko_sums"

mdFiles = os.listdir(srcDir)
mdFiles = sorted([f for f in mdFiles if f.endswith(".md")])
print(len(mdFiles),mdFiles[:10])


mdContents = {f:open(os.path.join(srcDir, f)).read() for f in mdFiles}
mdLengths = [len(mdContents[c]) for c in mdFiles]
mdLines = [len(mdContents[c].split("\n")) for c in mdFiles]

df = pd.DataFrame({"file": mdFiles, "length": mdLengths, "lines":mdLines})

# drop empty and very small files
df = df.drop(df[df["length"] < 20].index)

# drop all files which contain only a single line, most likely an image link
df = df.drop(df[df["lines"] < 5].index)

df["ratio"] = df.length / df.lines
# drop all files whith bad ration, probably OCR issue
df = df.drop(df[df["ratio"] < 10].index)

print(df.describe())

#plt.hist(df["length"], bins=5)
#plt.xscale("log")
#plt.xlabel("Length of Markdown Files")
#plt.ylabel("Frequency")
#plt.title("Distribution of Markdown File Lengths")
#plt.show()  

q98 = df["length"].quantile(0.98)
print("98th percentile:", q98)

df_q98 = df[df.length <= q98]
print("DF Q98:", df_q98.describe())


df_large = df_q98[df_q98.length > 10000]
print("DF large:", df_large.describe())

df_small = df_q98[df_q98.length <= 10000]
print("DF small:", df_small.describe())



prompt = """
Du bist ein Kommentator. Deine Aufgabe ist es, eine Zusammenfassung eines Bericht einer
Verwaltungssitzung oder einer Verwaltungsvorlage zu schreiben.
Wenn dir der Bericht vorgelegt wird, beantworte folgende Fragen dazu, sofern möglich:

 1) welche person legt den bericht vor
 2) was ist das datum des berichts
 3) bei welchem gremium war die sitzung oder bei welchem gremium wurde die vorlage behandelt
 4) was ist das thema des berichts
 5) was ist der titel des bericht. Leite einen passenden title vom thema ab, wenn keiner explizit angegeben wird
 6) Welches sind die wichtigstens Argumente im bericht
 7) Gibt es ein Ergebnis oder einen Beschluss? Wenn ja, welches.

Anschließend kombiniere alle Informationen und verfasse einen Zusammenfassung  im Markdown‑Format. Verwende keine
```markdown ... ``` code fence, sondern schreibe die Zusammenfassung direkt als Fließtext.

Antworte nur auf Deutsch, auch wenn der Bericht englishcen Text enthält. 
Verwende die Informationen im Bericht, um die Fragen zu beantworten, 
und füge keine Informationen hinzu, die nicht im Bericht enthalten sind. 
Wenn eine Information nicht im Bericht enthalten ist, lasse sie einfach weg.

Stelle sicher, dass Dein Bericht insgesamt nicht länger ist als 8000 Zeichen.

{report}


"""

import time

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_CHAT_MODEL = "mistral-large-2512"
#MISTRAL_CHAT_MODEL = "mistral-small-2506"
    
def requestSummary(report: str) -> str:
    payload = {
        "model": MISTRAL_CHAT_MODEL,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": report}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }
    response = requests.post(MISTRAL_CHAT_URL, headers=headers, data=json.dumps(payload))
    if response.status_code == 429:
        max_retries = 10
        base_delay = 1.0  # seconds

        for attempt in range(1, max_retries + 1):
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = float(retry_after)
            else:
                delay = base_delay * (2 ** (attempt - 1))

            time.sleep(delay)
            response = requests.post(MISTRAL_CHAT_URL, headers=headers, data=json.dumps(payload))

            if response.status_code != 429:
                break
    response.raise_for_status()
    return response.json().get("choices", [{}])[0].get("message", {}).get("content", "")



os.makedirs(dstDir, exist_ok=True)

# write small files directly, no need to summarize
smallNames = df_small.file.values
print("Small files:", len(smallNames))
for d in smallNames:
    content = mdContents[d].strip()
    print("Processing file:", d)
    out_path = os.path.join(dstDir, d)
    if os.path.exists(out_path):
        print("Skipping existing file:", d)
        continue
    with open(os.path.join(dstDir, d), "w") as f:
        f.write(content)

# summarize large files with mistral
validNames = df_large.file.values
print("Large files:", len(validNames))
for d in validNames:
    content = mdContents[d]
    print("Processing file:", d)
    out_path = os.path.join(dstDir, d)
    if os.path.exists(out_path):
        print("Skipping existing file:", d)
        continue
    try:
        sum = requestSummary(content)
        #print(f"Summary for {d}:\n{sum}\n\n")
        # Remove surrounding Markdown code fence like ```markdown ... ```
        cleaned = sum.strip()
        print(f"Cleaned summary for {d}:\n{cleaned}\n\n")
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        sum = cleaned
        with open(os.path.join(dstDir, d), "w") as f:
            f.write(sum)
    except Exception as e:
        print(f"Error processing {d}: {e}")

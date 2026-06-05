#
import pandas as pd
with open("./references/geo/strassen-ka-orig.md") as f:
    s = f.read()
s = s.strip().split("\n")
s1 = [x.strip() for x in s if len(x)>0]
print("Lines:",len(s1))
s2 = [x for x in s1 if x != "## Liegenschaftsamt Straßennamen in Karlsruhe"]
print("Text:",len(s2))
n = [x.split("## ")[1] for x in s2 if x.startswith("## ")]
print("Names:",len(n))
df = pd.DataFrame(n,columns=["text"])
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
        else:
            return txt
    elif first.isdigit():
        return " ".join(parts[1:])
    else:
        return x.strip()
df["year"] = df.text.apply(getYr)
df["name"] = df.text.apply(getTxt)
df.to_json("streetNames.json",orient="records",indent=2)
df.to_csv("streetNames.csv",index=False)

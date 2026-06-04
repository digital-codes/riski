""" Separate the city districts into separate files. """
import geopandas as gp
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="Separate city districts into separate files.")
    parser.add_argument("-i","--input_file", help="Path to the input GeoJSON file containing city districts.")
    parser.add_argument("-o","--output_dir", help="Directory to save the separated GeoJSON files.")
    args = parser.parse_args()

    if not args.input_file or not args.output_dir:
        print("Please provide both the input file and output directory.")
        return

    os.makedirs(args.output_dir, exist_ok=True)

    df = gp.read_file(args.input_file)

    for n in list(df.NAME.values):
        g = df[df.NAME == n]
        out = f"{args.output_dir}/{n}.geojson"
        g.to_file(out)

if __name__ == "__main__":
    main()


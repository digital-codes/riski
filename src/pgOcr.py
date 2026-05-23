"""
curl https://api.mistral.ai/v1/ocr\
    -H "Content-Type: application/json"\
    -H "Authorization: Bearer ${MISTRAL_API_KEY}"\
    -d '{
        "document": {
            "type": "document_url",
            "document_url": "data:application/pdf;base64,<base64_file>"
        },
        "model": "mistral-ocr-latest",
		"include_image_base64": true
    }' -o ocr_output.json
    """
import base64
import json
import os
import requests
from typing import Dict, Any

import argparse
import re
import time

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_API_URL = "https://api.mistral.ai/v1/ocr"

def perform_ocr(document_path: str) -> Dict[str, Any]:
    print(f"Performing OCR on document: {document_path}")
    with open(document_path, "rb") as f:
        file_data = f.read()
    base64_file = base64.b64encode(file_data).decode("utf-8")
    payload = {
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64_file}"
        },
        "model": "mistral-ocr-latest",
        "include_image_base64": True
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }
    response = requests.post(MISTRAL_API_URL, headers=headers, data=json.dumps(payload))
    if response.status_code == 429:

        max_retries = 8
        base_delay = 1.0  # seconds

        for attempt in range(1, max_retries + 1):
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = float(retry_after)
            else:
                delay = base_delay * (2 ** (attempt - 1))

            time.sleep(delay)
            response = requests.post(MISTRAL_API_URL, headers=headers, data=json.dumps(payload))

            if response.status_code != 429:
                break
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perform OCR on a document using Mistral API")
    parser.add_argument("-d", "--docpath", required=True,type=str, help="Path to the document file")
    parser.add_argument("-o", "--outdir", required=True, type=str, default=".", help="Path to save the OCR output JSON to that directory")
    args = parser.parse_args()

    outName = os.path.splitext(os.path.basename(args.docpath))[0]
    output_path = os.path.join(args.outdir, f"{outName}.json")
    output_img_base = os.path.join(args.outdir, f"{outName}_img")
    md_output_path = os.path.splitext(output_path)[0] + ".md"

    print(f"Output JSON path: {output_path}")
    print(f"Output Markdown path: {md_output_path}")
    print(f"Document path: {args.docpath}")

    os.makedirs(args.outdir, exist_ok=True)

    if args.docpath.endswith(".json"):
        with open(args.docpath, "r") as f:
            ocr_result = json.load(f)
    else:
        if os.path.exists(md_output_path):
            print(f"Markdown output {md_output_path} already exists, skipping OCR and markdown generation.")
            exit(0)
        ocr_result = perform_ocr(args.docpath)
        with open(output_path, "w") as f:
            json.dump(ocr_result, f, indent=2)



    pages = ocr_result.get("pages", []) or []
    markdown_snippets = []

    for page_number, page in enumerate(pages, start=1):
        markdown = page.get("markdown", "") or ""
        page_images = page.get("images", []) or []
        replacement_map = {}
        saved_names_in_order = []

        for image_number, image_obj in enumerate(page_images, start=1):
            image_path = f"{output_img_base}_{page_number}_{image_number}.jpg"
            image_name = os.path.basename(image_path)
            saved_names_in_order.append(image_name)

            b64_value = None
            if isinstance(image_obj, dict):
                for key in ("image_base64", "base64", "data", "content"):
                    if isinstance(image_obj.get(key), str) and image_obj[key]:
                        b64_value = image_obj[key]
                        break

                for key in ("id", "name", "file_name", "filename", "url", "image_url", "path", "image_path"):
                    val = image_obj.get(key)
                    if isinstance(val, str) and val:
                        replacement_map[val] = image_name
                        replacement_map[os.path.basename(val)] = image_name
            elif isinstance(image_obj, str):
                b64_value = image_obj

            if b64_value:
                if b64_value.startswith("data:"):
                    b64_value = b64_value.split(",", 1)[-1]
                try:
                    with open(image_path, "wb") as img_f:
                        img_f.write(base64.b64decode(b64_value))
                except Exception:
                    pass

        for old_ref, new_ref in replacement_map.items():
            markdown = markdown.replace(old_ref, new_ref)

        if saved_names_in_order:
            img_idx = {"i": 0}
            pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

            def _replace_img_tag(m):
                if img_idx["i"] < len(saved_names_in_order):
                    new_ref = saved_names_in_order[img_idx["i"]]
                    img_idx["i"] += 1
                    return f"![{m.group(1)}]({new_ref})"
                return m.group(0)

            markdown = pattern.sub(_replace_img_tag, markdown)

        markdown_snippets.append(markdown)

    with open(md_output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(markdown_snippets))


    print(f"OCR result saved to {output_path}")
    
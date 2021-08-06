import elasticsearch
import requests
from bs4 import BeautifulSoup
from bs4 import Comment
from elasticsearch import Elasticsearch
import re
import pandas as pd
import unidecode
from google.cloud import storage
from tqdm import tqdm


def download_blob(bucket_name, source_blob_name, destination_file_name):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)

    print("Blob {} downloaded to {}.".format(source_blob_name, destination_file_name))


download_blob(
    "360-datasets", "corpus/fr/medics-tools/medics-tools.csv", "medics-tools.csv"
)

csv = pd.read_csv("medics-tools.csv")
csv = csv[csv["route"].notnull()]
csv = csv[csv.route.str.contains("pdf") == False]

config = {"host": "localhost"}
es = elasticsearch.Elasticsearch(
    [
        config,
    ],
)

request_body = {
    "settings": {
        "number_of_shards": 1,
        "analysis": {
            "analyzer": {"url_analyzer": {"tokenizer": "letter"}},
        },
    },
    "mappings": {
        "properties": {
            "route.url": {"type": "text", "analyzer": "url_analyzer"},
            "route.french": {"type": "text", "analyzer": "french"},
            "content.french": {"type": "text", "analyzer": "french"},
        }
    },
}

es.indices.delete(index="tools", ignore=[400, 404])
es.indices.create(index="tools", body=request_body)

with tqdm(total=len(csv)) as pbar:
    for index, row in csv.iterrows():
        plain_text = ""
        r = requests.get(row.route)
        soup = BeautifulSoup(r.text, "html.parser")
        other_elements = soup.find_all(["script", "style"])
        for c in other_elements:
            c.decompose()
        plain_text += soup.get_text()

        for meta in soup.find_all("meta"):
            if isinstance(meta, str):
                plain_text += meta.get("content") + "\n"
        plain_text = re.sub(r"<!--.*?", "", plain_text)
        plain_text = re.sub(r"-->", "", plain_text)
        plain_text = re.sub(r"-->", "", plain_text)
        plain_text = unidecode.unidecode(plain_text)
        plain_text = "\n".join([l.strip() for l in plain_text.splitlines() if len(l) > 2])
        res = es.index(
            index="tools",
            body={
                "route.url": row["route"],
                "route.french": row["route"],
                "content.french": plain_text,
            },
            id=row["tool_id"],
        )
        pbar.update(1)

# uv run python annotation/label_studio/setup_ner_projects.py \
#   --ls-url http://localhost:8083 \
#   --ls-token $LS_TOKEN
set -a; source .env; set +a
uv run python annotation/label_studio/setup_ner_projects.py \
    --ls-url http://localhost:8081 \
    --ls-token $LS_ACCESS_TOKEN \
    --dictionaries Circassian-English-Turkish \
    --overwrite
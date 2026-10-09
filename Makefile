all: data model detect

data:
	uv run python generate_data.py

model:
	uv run dbt build --profiles-dir .

detect:
	uv run python detect.py

docs:
	uv run dbt docs generate --profiles-dir . && uv run dbt docs serve --profiles-dir .
